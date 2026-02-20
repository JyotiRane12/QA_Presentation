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

from core.jira_client import get_issue, extract_linked_from_issue, enrich_linked_resolutions, dates_from_changelog
from core.slack_client import post_message, post_ephemeral_with_buttons, open_dm_channel, fetch_channel_messages
from core.report_formatter import (
    bug_count_jql_queries,
    bug_counts,
    bug_keys,
    internal_peds_count,
    leds_info,
    build_report,
    format_date as _format_date,
    OPTIONAL_SECTION_KEYS,
)
from core.report_formatter import _is_led_linked  # noqa: F401 - used in summarize_challenges

load_dotenv(Path(__file__).resolve().parent / ".env")

SLACK_CHANNEL_ID = (os.getenv("SLACK_CHANNEL_ID") or "").strip()
SLACK_REVIEW_CHANNEL_ID = (os.getenv("SLACK_REVIEW_CHANNEL_ID") or "").strip()
SLACK_REVIEW_USER_ID = (os.getenv("SLACK_REVIEW_USER_ID") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()

PENDING_REPORTS_DIR = Path(__file__).resolve().parent / "data" / "pending_reports"


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


def summarize_challenges(jira_id: str, issue: dict, linked: list[dict], slack_messages_today: list[dict], open_leds: list[dict] | None = None) -> str:
    """Summarize challenges for the given JIRA issue: linked issues + related Slack communication. Use AI if OPENAI_API_KEY set."""
    linked_keys = [l.get("key", "") for l in linked if l.get("key")]
    linked_summary = "\n".join(
        f"- {l.get('key', '')}: {l.get('issuetype', '')} | {l.get('status', '')} | Assignee: {l.get('assignee', '') or 'Unassigned'} | {(l.get('summary') or '')[:120]}"
        for l in linked[:30]
    ) or "(none)"
    issue_summary = ((issue.get("fields") or {}).get("summary") or "").strip()[:200]
    slack_lines = []
    for m in slack_messages_today[-50:]:
        text = (m.get("text") or "").strip().replace("\n", " ")[:400]
        if text:
            slack_lines.append(text)
    has_slack = bool(slack_lines)
    # Open, Analysis IP, Dev IP, Development IP, Development Review, Design Review. Bug must be mentioned as blocker/blocking in communication.
    BLOCKER_STATUSES = ("open", "analysis ip", "dev ip", "development ip", "development review", "design review")
    BLOCKER_KEYWORDS = ("blocker", "blocking", "not able to continue testing", "cannot continue testing")
    # First: messages that mention blocker/blocking and a bug key or JIRA
    blocker_messages = []
    bugs_mentioned_as_blocker = set()
    for m in slack_messages_today:
        text = (m.get("text") or "").strip()
        text_upper = text.upper()
        if not any(kw.upper() in text_upper for kw in BLOCKER_KEYWORDS):
            continue
        mentions_jira_or_bug = jira_id.upper() in text_upper
        for l in linked:
            key = (l.get("key") or "").strip().upper()
            if key and key in text_upper:
                bugs_mentioned_as_blocker.add(key)
                mentions_jira_or_bug = True
        if mentions_jira_or_bug:
            blocker_messages.append(text.replace("\n", " ")[:400])
    # Active blockers: status Open/Analysis IP/Dev IP/Development IP/Development Review/Design Review AND mentioned as blocker in communication
    active_blockers = [
        l for l in linked
        if (l.get("issuetype") or "").strip() == "Bug"
        and not _is_led_linked(l)
        and (l.get("status") or "").strip().lower() in BLOCKER_STATUSES
        and (l.get("key") or "").strip().upper() in bugs_mentioned_as_blocker
    ]
    active_blocker_keys = {b.get("key", "").upper() for b in active_blockers if b.get("key")}
    mention_keys = {jira_id.upper()} | active_blocker_keys
    # Deduplicate blocker messages
    seen_normalized = set()
    filtered_slack = []
    for raw in blocker_messages:
        norm = raw.upper().strip()
        if norm and norm not in seen_normalized:
            seen_normalized.add(norm)
            filtered_slack.append(raw)
    slack_context = "\n".join(filtered_slack) if filtered_slack else "(no messages mentioning blocker/blocking for JIRA or linked bugs)"
    active_blocker_summary = "\n".join(
        f"- {b.get('key', '')}: {b.get('status', '')} | Assignee: {b.get('assignee', '') or 'Unassigned'} | {(b.get('summary') or '')[:100]}"
        for b in active_blockers[:20]
    ) or "(none)"

    _open_leds = open_leds or []
    led_env_summary = "\n".join(
        f"- {o.get('key', '')}: Open | Assignee: {o.get('assignee', 'Unassigned')} | {(o.get('summary', '') or '')[:100]}"
        for o in _open_leds
    ) if _open_leds else "(none)"

    CHALLENGES_RULES = """DAILY QA REPORT – CHALLENGES FIELD RULES (STRICT)

GENERAL: Represent real, active blockers only. No minor bugs, resolved/closed tickets, or vague statements.
NEVER EMPTY: If no active blockers exist, output exactly: "No major challenges observed today."

INCLUDE ONLY: Blocked JIRA tickets, Environment issues (LED/Environmental open issues), Dependency delays, Release risks, Cross-team blockers, Pending approvals.
MANDATORY: Always include LED/Environment open issues in Challenges – these are environment blockers affecting testing.
PRIORITY: If conversation mentions "blocker" and implies "not able to continue testing", highlight the ticket when status is Open, Analysis IP, Development IP, Development Review, or Design Review.
EXCLUDE: Minor bugs, tickets in progress but not blocked, informational comments, tasks without delivery impact, duplicates. Do NOT include bugs in Released or Closed status - they are resolved, not active blockers.

FORMAT (MANDATORY – use for each challenge):
• JIRA-XXXX – Short description of blocker (Assignee: <Dev/QA/Infra/Other Team or Person>)
  Impact: <Testing Delay/Release Risk/Waiting on Dependency/SIT Blocked>

Each challenge must answer: What is blocked? Why? Who owns it? What is the impact? Max 2–3 lines per challenge.
If total challenges > 5, add at end: "⚠ High number of active blockers – escalation may be required."
Output must be Slack markdown compatible. Never fabricate data."""

    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            import httpx
            context = f"""JIRA ID: {jira_id}
JIRA Title: {issue_summary}

Active blockers (status Open, Analysis IP, Dev IP, Development IP, Development Review, Design Review; mentioned as blocker/blocking in Slack):
{active_blocker_summary}

LED/Environment open issues (must include in Challenges):
{led_env_summary}

Slack messages mentioning blocker/blocking:
{slack_context}"""
            prompt = f"""Generate the Challenges section for JIRA {jira_id} using the rules below and the data provided.

{CHALLENGES_RULES}

Data:
"""
            verify = os.getenv("OPENAI_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
            proxy = os.getenv("OPENAI_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
            if proxy or not verify:
                client = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client(verify=verify, proxy=proxy or None, timeout=60.0))
            else:
                client = OpenAI(api_key=OPENAI_API_KEY)
            r = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": CHALLENGES_RULES},
                    {"role": "user", "content": prompt + "\n\n---\n\n" + context},
                ],
                max_tokens=400,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"AI summary failed: {e}")

    # Non-AI fallback: align with Challenges.cursorrules format; include LED/Environment open issues
    parts = []
    if _open_leds:
        for o in _open_leds[:5]:
            owner = o.get("assignee") or "Infra"
            parts.append(f"• {o.get('key', '')} – {(o.get('summary', '') or 'Environment/LED open')[:80]} (Assignee: {owner})\n  Impact: Environment Issue / Testing Blocked")
    if active_blockers:
        for b in active_blockers[:5]:
            owner = b.get("assignee") or "Dev"
            parts.append(f"• {b.get('key', '')} – {(b.get('summary') or '')[:80]} (Assignee: {owner})\n  Impact: Testing Delay")
    if filtered_slack and not active_blockers and not _open_leds:
        for t in filtered_slack[:5]:
            parts.append(f"• {t[:200]}")
    if not parts:
        return "No major challenges observed today."
    if len(parts) > 5:
        parts.append("⚠ High number of active blockers – escalation may be required.")
    return "\n".join(parts)


def run(issue_keys: list[str], post: bool = True, dry_run: bool = False) -> str:
    keys_to_process = [k.strip() for k in issue_keys if k and k.strip()]
    if not keys_to_process:
        raise SystemExit("No valid JIRA issue key(s) provided.")

    invalid_keys = []
    for jira_id in keys_to_process:
        try:
            get_issue(jira_id)
        except requests.HTTPError:
            invalid_keys.append(jira_id)
            print(f"JIRA ID not found or incorrect: {jira_id}")
        except Exception as e:
            invalid_keys.append(jira_id)
            print(f"JIRA ID not found or incorrect: {jira_id} – {e}")
    if invalid_keys:
        raise SystemExit(f"JIRA ID not found or incorrect: {', '.join(invalid_keys)}. Report was not posted.")

    channel_id = (os.getenv("SLACK_CHANNEL_ID") or "").strip()
    if not channel_id:
        raise SystemExit("Slack Channel ID is required to read conversations and create Challenges.")
    if not re.match(r"^[CGD][A-Z0-9]{8,}$", channel_id, re.IGNORECASE):
        raise SystemExit("Slack Channel ID is incorrect or empty. Report was not posted.")

    report_keys_env = (os.getenv("REPORT_OUTPUT_KEYS") or "").strip()
    include_optional = set()
    if report_keys_env:
        for k in report_keys_env.split(","):
            k = k.strip()
            if k and k in OPTIONAL_SECTION_KEYS:
                include_optional.add(k)

    today_str = _format_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    reports = []
    for jira_id in keys_to_process:
        issue = get_issue(jira_id)
        linked = extract_linked_from_issue(issue)
        enrich_linked_resolutions(linked)
        total, with_dev, with_qa, with_product, closed, p0, p1 = bug_counts(linked)
        internal_peds = internal_peds_count(linked)
        print(f"Total Bugs JIRA IDs for {jira_id}: {', '.join(bug_keys(linked)) or '(none)'}")
        print(f"Counts: Total={total}, With Dev={with_dev}, With QA={with_qa}, With Product={with_product}, Closed={closed}, Internal PEDS={internal_peds}, P0={p0}, P1={p1}")
        jql = bug_count_jql_queries(jira_id)
        print(f"JQL – Total Bugs: {jql['total_bugs']}")
        print(f"JQL – Closed Bugs: {jql['closed_bugs']}")
        print(f"JQL – Bugs With Product: {jql['bugs_with_product']}")
        print(f"JQL – Internal PEDS: {jql['internal_peds']}")
        print(f"JQL – P0: {jql['p0']}")
        print(f"JQL – P1: {jql['p1']}")
        dates = dates_from_changelog(issue)
        led_count, open_leds = leds_info(linked)
        slack_messages = fetch_channel_messages(SLACK_CHANNEL_ID) if SLACK_CHANNEL_ID else []
        slack_today = filter_messages_today(slack_messages)
        challenges = summarize_challenges(jira_id, issue, linked, slack_today, open_leds=open_leds)
        report = build_report(jira_id, issue, linked, dates, challenges, led_count, open_leds, today_str, include_optional=include_optional)
        reports.append(report)
    full_report = "\n\n---\n\n".join(reports)

    if dry_run:
        print("--- DRY RUN (not posted) ---\n")
    if post:
        posted = False
        review_user_id = (os.getenv("SLACK_REVIEW_USER_ID") or "").strip()
        channel_id = (os.getenv("SLACK_CHANNEL_ID") or "").strip()
        if review_user_id and re.match(r"^U[A-Z0-9]{8,}$", review_user_id, re.IGNORECASE):
            dm_channel = open_dm_channel(review_user_id)
            if dm_channel and post_message(dm_channel, full_report):
                print("Report sent to user (1:1 DM).")
                posted = True
            if channel_id and post_ephemeral_with_buttons(channel_id, review_user_id, full_report, PENDING_REPORTS_DIR):
                print("Report sent as ephemeral with Post button (visible only to reviewer until they click Post).")
                posted = True
            if not posted:
                raise SystemExit("Slack User ID not found or incorrect. Report was not sent.")
        else:
            post_channel = SLACK_REVIEW_CHANNEL_ID if SLACK_REVIEW_CHANNEL_ID else channel_id or SLACK_CHANNEL_ID
            if post_channel:
                if post_message(post_channel, full_report):
                    print("Report posted to Slack.")
                    posted = True
                else:
                    raise SystemExit("Slack Channel ID not found or incorrect. Report was not posted.")
            else:
                raise SystemExit("Slack Channel ID is required to read conversations and create Challenges.")
    print(full_report)
    return full_report


def main():
    ap = argparse.ArgumentParser(description="QA Daily Report – format and post to Slack")
    ap.add_argument("--issues", "-i", required=True, help="JIRA issue key(s), comma-separated (e.g. SMT-51974)")
    ap.add_argument("--no-post", action="store_true", help="Build report but do not post to Slack")
    ap.add_argument("--dry-run", action="store_true", help="Print report to stdout only")
    args = ap.parse_args()
    keys = [k.strip() for k in args.issues.split(",") if k.strip()]
    if not keys:
        raise SystemExit("Provide at least one JIRA issue key with --issues")
    run(keys, post=not args.no_post and not args.dry_run, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
