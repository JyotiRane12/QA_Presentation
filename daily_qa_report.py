#!/usr/bin/env python3
"""
QA Daily Report – generates report in required format and posts to Slack.

Format:
- QA Update - Today's date
- JIRA ID, JIRA Title
- Ready for QA Date, QA start Date, One Round Of testing completion date, Targetted Release Date
- Total Bugs, With DEV Bug Counts, With QA
- Challenges (Slack today's conversation summary)
- Environment Issue (LED count + any LED in Open status)

Usage: python daily_qa_report.py --issues SMT-51974 [--no-post] [--dry-run]
"""

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_VERIFY_SSL = os.getenv("JIRA_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
if not JIRA_VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")  # same channel for reading messages and posting QA daily report
SLACK_REVIEW_CHANNEL_ID = (os.getenv("SLACK_REVIEW_CHANNEL_ID") or "").strip()  # optional: post to this channel when "Post Report to Review"
SLACK_REVIEW_USER_ID = (os.getenv("SLACK_REVIEW_USER_ID") or "").strip()  # optional: send report as DM to this user (review)
SLACK_VERIFY_SSL = os.getenv("SLACK_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ----- JIRA -----

def _jira_get(path: str, params: dict | None = None) -> dict:
    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_TOKEN:
        raise SystemExit("JIRA credentials missing. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env")
    url = f"{JIRA_BASE}/rest/api/2/{path}"
    r = requests.get(
        url, params=params or {}, auth=(JIRA_EMAIL, JIRA_TOKEN),
        headers={"Accept": "application/json"}, timeout=30, verify=JIRA_VERIFY_SSL,
    )
    r.raise_for_status()
    return r.json()


def jira_issue(issue_key: str, expand: str = "renderedFields,changelog") -> dict:
    return _jira_get("issue/" + issue_key, params={"expand": expand})


def extract_linked_from_issue(issue: dict) -> list[dict]:
    """Linked issues with key, summary, status, issuetype, project, resolution."""
    links = (issue.get("fields") or {}).get("issuelinks") or []
    linked = []
    for link in links:
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        fields = other.get("fields") or {}
        status = (fields.get("status") or {}).get("name", "")
        issuetype = (fields.get("issuetype") or {}).get("name", "Unknown")
        project_key = (fields.get("project") or {}).get("key", "")
        resolution = (fields.get("resolution") or {}).get("name", "")
        linked.append({
            "key": other.get("key", ""),
            "summary": fields.get("summary", ""),
            "status": status,
            "issuetype": issuetype,
            "project": project_key,
            "resolution": resolution,
        })
    return linked


def dates_from_changelog(issue: dict) -> dict:
    """Return dict with ready_for_qa, qa_start (QA IP), bug_fixing_ip, target_release (duedate)."""
    ready_qa = ""
    qa_start = ""   # when status changed to QA IP
    bug_fixing_ip = ""
    histories = (issue.get("changelog") or {}).get("histories") or []
    for h in sorted(histories, key=lambda x: x.get("created", "")):
        created = (h.get("created") or "")[:10]
        for item in h.get("items") or []:
            if (item.get("field") or "").lower() != "status":
                continue
            to_status = (item.get("toString") or "").strip()
            to_lower = to_status.lower()
            if not ready_qa and "ready for qa" in to_lower:
                ready_qa = created
            if not qa_start and ("qa ip" in to_lower or "qa in progress" in to_lower):
                qa_start = created
            if not bug_fixing_ip and ("bug-fixing ip" in to_lower or "bug fixing ip" in to_lower):
                bug_fixing_ip = created
    fields = issue.get("fields") or {}
    target_release = ""
    duedate = fields.get("duedate")
    if duedate:
        target_release = duedate[:10] if isinstance(duedate, str) else ""
    return {
        "ready_for_qa": ready_qa,
        "qa_start": qa_start,
        "bug_fixing_ip": bug_fixing_ip,
        "target_release": target_release,
    }


# Status groups for bug counts (case-insensitive match)
DEV_STATUSES = ("dev ip", "dev review", "open", "analysis ip")
QA_STATUSES = ("qa ip", "qa review", "ready for release", "ready for sit")
CLOSED_BUG_EXCLUDE_RESOLUTIONS = ("not a bug", "duplicate")


def _is_led_linked(l: dict) -> bool:
    """True if linked issue is from LEDS project (key starts with LED/LEDS- or project LEDS)."""
    key = (l.get("key") or "").strip().upper()
    proj = (l.get("project") or "").strip().upper()
    if proj == "LEDS":
        return True
    if key and (key.startswith("LED-") or key.startswith("LEDS-")):
        return True
    return False


def bug_counts(linked: list[dict]) -> tuple[int, int, int, int]:
    """Return (total_bugs, with_dev_count, with_qa_count, closed_bugs_count). Excludes LED/LEDS-prefix. Closed Bugs: status Closed, resolution not Not a bug/Duplicate."""
    bugs = [l for l in linked if (l.get("issuetype") or "").strip() == "Bug" and not _is_led_linked(l)]
    total = len(bugs)
    status_lower = lambda l: (l.get("status") or "").strip().lower()
    resolution_lower = lambda l: (l.get("resolution") or "").strip().lower()
    with_dev = sum(1 for l in bugs if status_lower(l) in DEV_STATUSES)
    with_qa = sum(1 for l in bugs if status_lower(l) in QA_STATUSES)
    closed_bugs = sum(
        1 for l in bugs
        if status_lower(l) == "closed" and resolution_lower(l) not in CLOSED_BUG_EXCLUDE_RESOLUTIONS
    )
    return (total, with_dev, with_qa, closed_bugs)


def bug_keys(linked: list[dict]) -> list[str]:
    """Return JIRA keys of linked issues that are Bug type, excluding LED/LEDS-prefix."""
    return [
        l.get("key", "") for l in linked
        if (l.get("issuetype") or "").strip() == "Bug" and l.get("key") and not _is_led_linked(l)
    ]


def leds_info(linked: list[dict]) -> tuple[int, list[str]]:
    """Return (led_count, list of LED keys that are Open)."""
    def is_led(l):
        proj = (l.get("project") or "").strip().upper()
        key = (l.get("key") or "").strip().upper()
        if proj == "LEDS":
            return True
        if key and (key.startswith("LED-") or key.startswith("LEDS-")):
            return True
        return False
    leds = [l for l in linked if is_led(l)]
    open_leds = [l.get("key", "") for l in leds if (l.get("status") or "").strip().lower() == "open"]
    return (len(leds), open_leds)


# ----- Slack -----

def fetch_slack_messages(channel_id: str, limit: int = 500) -> list[dict]:
    if not SLACK_BOT_TOKEN or not channel_id:
        return []
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    messages = []
    cursor = None
    try:
        while len(messages) < limit:
            params = {"channel": channel_id, "limit": min(200, limit - len(messages))}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(url, params=params, headers=headers, timeout=30, verify=SLACK_VERIFY_SSL)
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                break
            for msg in data.get("messages") or []:
                if msg.get("type") != "message" or msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                messages.append({"ts": msg.get("ts", ""), "user": msg.get("user", ""), "text": text})
            if not data.get("has_more"):
                break
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return messages
    except requests.RequestException:
        return []


def filter_messages_today(messages: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    out = []
    for m in messages:
        try:
            ts = m.get("ts", "")
            if not ts:
                continue
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            if dt.date() == today:
                out.append(m)
        except (ValueError, TypeError):
            continue
    return out


def summarize_challenges(slack_messages_today: list[dict]) -> str:
    """Summarize today's Slack messages for Challenges. Use AI if OPENAI_API_KEY set, else bullets."""
    if not slack_messages_today:
        return "No conversation from today in the channel."
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            import httpx
            lines = []
            for m in slack_messages_today[-50:]:
                text = (m.get("text") or "").strip().replace("\n", " ")[:400]
                if text:
                    lines.append(text)
            if not lines:
                return "No conversation from today in the channel."
            context = "\n".join(lines)
            verify = os.getenv("OPENAI_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
            proxy = os.getenv("OPENAI_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            if proxy or not verify:
                client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client(verify=verify, proxy=proxy or None, timeout=60.0))
            else:
                client = OpenAI(api_key=OPENAI_API_KEY)
            r = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "Summarize QA/testing challenges and blockers from Slack messages. Be concise, 3-8 bullets or short paragraph."},
                    {"role": "user", "content": "Summarize today's channel conversation for a QA Daily Report 'Challenges' section:\n\n" + context},
                ],
                max_tokens=400,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"AI summary failed: {e}")
    lines = []
    for m in slack_messages_today[:15]:
        text = (m.get("text") or "").strip().replace("\n", " ")[:200]
        if text:
            lines.append(f"• {text}")
    return "\n".join(lines) if lines else "No conversation from today in the channel."


def post_to_slack(channel_id: str, text: str) -> bool:
    if not SLACK_BOT_TOKEN or not channel_id:
        return False
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, json={"channel": channel_id, "text": text}, headers=headers, timeout=30, verify=SLACK_VERIFY_SSL)
        data = r.json()
        if not data.get("ok"):
            err = data.get("error", "unknown")
            print(f"Slack post error: {err}")
            if err == "channel_not_found":
                print(f"  Channel ID used: {channel_id}")
                print("  Fix: 1) Check .env: SLACK_CHANNEL_ID.")
                print("       2) Get channel ID: Slack → right-click channel → View channel details → copy ID (e.g. C0AFTQD06MP1).")
                print("       3) Invite the bot to the channel: in that channel type /invite @YourBotName")
                print("       4) For private channels the ID often starts with G; ensure the bot is a member.")
            return False
        return True
    except requests.RequestException as e:
        print(f"Slack post failed: {e}")
        return False


def open_dm_channel(user_id: str) -> str:
    """Open or get DM channel with user. Returns channel ID or empty string."""
    print(f"[LOG] open_dm_channel: user_id={user_id!r}, SLACK_BOT_TOKEN={'set' if SLACK_BOT_TOKEN else 'NOT SET'}")
    if not SLACK_BOT_TOKEN or not user_id:
        print("[LOG] open_dm_channel: skipping (missing token or user_id)")
        return ""
    url = "https://slack.com/api/conversations.open"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    try:
        print(f"[LOG] Calling Slack conversations.open for user {user_id}...")
        r = requests.post(url, json={"users": user_id}, headers=headers, timeout=30, verify=SLACK_VERIFY_SSL)
        data = r.json()
        print(f"[LOG] conversations.open response: ok={data.get('ok')}, error={data.get('error', 'none')}")
        if not data.get("ok"):
            print(f"[LOG] Slack conversations.open full response: {data}")
            return ""
        ch = data.get("channel") or {}
        dm_id = (ch.get("id") or "").strip()
        print(f"[LOG] DM channel id={dm_id!r}")
        return dm_id
    except requests.RequestException as e:
        print(f"[LOG] Slack open DM failed: {e}")
        return ""


# ----- Report build -----

def _format_date(ymd: str) -> str:
    """Format YYYY-MM-DD to '18th Feb 2026'. Returns original string or 'N/A' if empty/invalid."""
    if not ymd or len(ymd) < 10:
        return ymd.strip() if ymd else "N/A"
    try:
        d = datetime.strptime(ymd[:10], "%Y-%m-%d")
        day = d.day
        if 11 <= day <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} {d.strftime('%b %Y')}"
    except ValueError:
        return ymd[:10]


def _uat_status(issue: dict) -> str:
    """UAT Status: Pending until 'Ready for UAT'; In-UAT when status is Ready for UAT or beyond."""
    status = (issue.get("fields") or {}).get("status") or {}
    name = (status.get("name") or "").strip().lower()
    if "ready for uat" in name:
        return "In-UAT"
    return "Pending"


def _preprod_status(issue: dict) -> str:
    """Preprod Status: Pending until Ready for SIT; In-progress when Ready for SIT or beyond."""
    status = (issue.get("fields") or {}).get("status") or {}
    name = (status.get("name") or "").strip().lower()
    if "ready for sit" in name:
        return "In-progress"
    return "Pending"


def build_report(jira_id: str, issue: dict, linked: list[dict], dates: dict, challenges: str, led_count: int, open_led_keys: list[str], today_str: str) -> str:
    fields = issue.get("fields") or {}
    title = (fields.get("summary") or "").strip()
    total_bugs, with_dev, with_qa, closed_bugs = bug_counts(linked)
    uat_status = _uat_status(issue)
    preprod_status = _preprod_status(issue)

    env_line = f"LED count: {led_count}."
    if open_led_keys:
        env_line += f" LED(s) in Open status: {', '.join(open_led_keys)}."
    else:
        env_line += " No LED in Open status."

    block = [
        f"*QA Update* – {today_str}",
        "",
        f"*JIRA ID* – {jira_id}",
        f"*JIRA Title* – {title}",
        "",
        f"*Ready For QA Date* – {_format_date(dates['ready_for_qa'])}",
        f"*QA Start Date* – {_format_date(dates['qa_start'])}",
        f"*One Round Of Testing Completion* – {_format_date(dates['bug_fixing_ip']) if dates['bug_fixing_ip'] else 'Pending'}",
        "",
        f"*Total Bugs* – {total_bugs}",
        f"*Bugs With Dev* – {with_dev}",
        f"*Bugs With QA* – {with_qa}",
        f"*Closed Bugs* – {closed_bugs}",
        "",
        f"*Challenges* – {challenges}",
        "",
        f"*Environment Issue* – {env_line}",
        "",
        f"*Targetted Release Date* – {_format_date(dates['target_release'])}",
        f"*UAT Status* – {uat_status}",
        f"*Preprod Status* – {preprod_status}",
    ]
    return "\n".join(block)


def run(issue_keys: list[str], post: bool = True, dry_run: bool = False) -> str:
    keys_to_process = [k.strip() for k in issue_keys if k and k.strip()]
    if not keys_to_process:
        raise SystemExit("No valid JIRA issue key(s) provided.")

    # 1. Validate all JIRA keys exist before building or posting
    invalid_keys = []
    for jira_id in keys_to_process:
        try:
            jira_issue(jira_id)
        except requests.HTTPError as e:
            invalid_keys.append(jira_id)
            print(f"JIRA ID not found or incorrect: {jira_id}")
        except Exception as e:
            invalid_keys.append(jira_id)
            print(f"JIRA ID not found or incorrect: {jira_id} – {e}")
    if invalid_keys:
        keys_str = ", ".join(invalid_keys)
        msg = f"JIRA ID not found or incorrect: {keys_str}. Report was not posted."
        raise SystemExit(msg)

    channel_id = (os.getenv("SLACK_CHANNEL_ID") or "").strip()
    if not channel_id:
        raise SystemExit("Slack Channel ID is required to read conversations and create Challenges.")
    # Slack channel IDs start with C (public), G (private), or D (DM) and are 9+ chars alphanumeric
    if not re.match(r"^[CGD][A-Z0-9]{8,}$", channel_id, re.IGNORECASE):
        print("Slack Channel ID not found or incorrect: invalid format")
        raise SystemExit("Slack Channel ID is incorrect or empty. Report was not posted.")

    today_str = _format_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    reports = []
    for jira_id in keys_to_process:
        issue = jira_issue(jira_id)
        linked = extract_linked_from_issue(issue)
        total_bug_keys = bug_keys(linked)
        print(f"Total Bugs JIRA IDs for {jira_id}: {', '.join(total_bug_keys) or '(none)'}")
        dates = dates_from_changelog(issue)
        led_count, open_led_keys = leds_info(linked)
        slack_messages = fetch_slack_messages(SLACK_CHANNEL_ID) if SLACK_CHANNEL_ID else []
        slack_today = filter_messages_today(slack_messages)
        challenges = summarize_challenges(slack_today)
        report = build_report(jira_id, issue, linked, dates, challenges, led_count, open_led_keys, today_str)
        reports.append(report)
    full_report = "\n\n---\n\n".join(reports)

    if dry_run:
        print("--- DRY RUN (not posted) ---\n")
    if post:
        posted = False
        # Re-read from env so CLI (--post-to-review-user) and UI overrides take effect
        review_user_id = (os.getenv("SLACK_REVIEW_USER_ID") or "").strip()
        channel_id = (os.getenv("SLACK_CHANNEL_ID") or "").strip()
        print(f"[LOG] post=True | SLACK_REVIEW_USER_ID={review_user_id!r} | SLACK_CHANNEL_ID={channel_id!r}")
        if review_user_id:
            # Slack user IDs start with U and are 9+ chars alphanumeric
            if not re.match(r"^U[A-Z0-9]{8,}$", review_user_id, re.IGNORECASE):
                print("Slack User ID not found or incorrect: invalid format")
                raise SystemExit("Slack User ID is incorrect or empty. Report was not sent.")
            dm_channel = open_dm_channel(review_user_id)
            if dm_channel and post_to_slack(dm_channel, full_report):
                print("Report sent to user (DM).")
                posted = True
            elif not dm_channel:
                print("Slack User ID not found or incorrect. Report was not sent.")
                raise SystemExit("Slack User ID not found or incorrect. Report was not sent.")
            if not posted:
                print("Report was not sent.")
                raise SystemExit("Slack User ID not found or incorrect. Report was not sent.")
        else:
            post_channel = SLACK_REVIEW_CHANNEL_ID if SLACK_REVIEW_CHANNEL_ID else channel_id or SLACK_CHANNEL_ID
            if post_channel:
                if post_to_slack(post_channel, full_report):
                    print("Report posted to Slack.")
                    posted = True
                else:
                    print("Slack Channel ID not found or incorrect. Report was not posted.")
                    raise SystemExit("Slack Channel ID not found or incorrect. Report was not posted.")
            else:
                print("Slack channel not set (SLACK_CHANNEL_ID or SLACK_REVIEW_CHANNEL_ID). Report not posted.")
                raise SystemExit("Slack Channel ID is required to read conversations and create Challenges.")
    print(full_report)
    return full_report


def main():
    ap = argparse.ArgumentParser(description="QA Daily Report – format and post to Slack")
    ap.add_argument("--issues", "-i", required=True, help="JIRA issue key(s), comma-separated (e.g. SMT-51974)")
    ap.add_argument("--no-post", action="store_true", help="Build report but do not post to Slack")
    ap.add_argument("--dry-run", action="store_true", help="Print report to stdout only")
    ap.add_argument("--post-to-review-user", metavar="USER_ID", help="Send report as DM to this Slack user ID (e.g. U01234ABCD)")
    args = ap.parse_args()
    keys = [k.strip() for k in args.issues.split(",") if k.strip()]
    if not keys:
        raise SystemExit("Provide at least one JIRA issue key with --issues")
    if args.post_to_review_user and args.post_to_review_user.strip():
        os.environ["SLACK_REVIEW_USER_ID"] = args.post_to_review_user.strip()
        os.environ.pop("SLACK_CHANNEL_ID", None)
        print(f"[LOG] Review mode: post to user {args.post_to_review_user!r}")
    run(keys, post=not args.no_post and not args.dry_run, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
