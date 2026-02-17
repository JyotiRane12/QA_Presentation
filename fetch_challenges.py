#!/usr/bin/env python3
"""
Fetch project-specific challenges for QA presentation from:
- JIRA: issues, comments, linked issues
- Slack: project channel messages (export or JSON file)
"""

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from project directory (so it works when run from any cwd)
load_dotenv(Path(__file__).resolve().parent / ".env")

JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_API_TOKEN", "")
SLACK_EXPORT_PATH = os.getenv("SLACK_EXPORT_PATH", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")  # xoxb-... for API fetch
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")  # Channel ID (e.g. C01234ABC) to fetch QA conversations
SLACK_VERIFY_SSL = os.getenv("SLACK_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GAMMA_API_KEY = os.getenv("GAMMA_API_KEY", "")
GAMMA_VERIFY_SSL = os.getenv("GAMMA_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
# Set to false only if behind corporate proxy/firewall with custom SSL (e.g. self-signed in chain)
JIRA_VERIFY_SSL = os.getenv("JIRA_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
if not JIRA_VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _jira_request(path: str, params: dict | None = None, *, api_version: int = 2) -> dict:
    """Internal: perform GET to Jira REST API (default api/2; use api_version=3 for search)."""
    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_TOKEN:
        env_path = Path(__file__).resolve().parent / ".env"
        raise SystemExit(
            "JIRA credentials missing. Create a .env file in the project folder (copy config.example.env)\n"
            f"  and set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.\n"
            f"  Expected .env at: {env_path}"
        )
    url = f"{JIRA_BASE}/rest/api/{api_version}/{path}"
    r = requests.get(
        url,
        params=params or {},
        auth=(JIRA_EMAIL, JIRA_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
        verify=JIRA_VERIFY_SSL,
    )
    r.raise_for_status()
    return r.json()


def _jira_post(path: str, json_body: dict, *, api_version: int = 3) -> dict:
    """Internal: perform POST to Jira REST API (e.g. for search/approximate-count)."""
    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_TOKEN:
        env_path = Path(__file__).resolve().parent / ".env"
        raise SystemExit(
            "JIRA credentials missing. Create a .env file in the project folder (copy config.example.env)\n"
            f"  and set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.\n"
            f"  Expected .env at: {env_path}"
        )
    url = f"{JIRA_BASE}/rest/api/{api_version}/{path}"
    r = requests.post(
        url,
        json=json_body,
        auth=(JIRA_EMAIL, JIRA_TOKEN),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=30,
        verify=JIRA_VERIFY_SSL,
    )
    r.raise_for_status()
    return r.json()


def jira_get(path: str, params: dict | None = None) -> dict:
    return _jira_request(path, params, api_version=2)


def jira_search(jql: str, fields: str, limit: int = 50, start_at: int = 0) -> list[dict]:
    data = jira_get(
        "search",
        params={"jql": jql, "fields": fields, "maxResults": limit, "startAt": start_at},
    )
    return data.get("issues", [])


def jira_leds_count_linked_to(parent_issue_key: str) -> int:
    """Return count of LEDS project issues (any type) linked to the given parent issue.
    JQL: issue in linkedIssues(parent) AND project = LEDS
    Uses POST /rest/api/3/search/approximate-count so we get the full count (search/jql does not return total).
    """
    jql = f'issue in linkedIssues("{parent_issue_key}") AND project = LEDS'
    print(f"LEDs query: {jql}")
    try:
        data = _jira_post("search/approximate-count", {"jql": jql}, api_version=3)
        # Response: {"count": N} or similar
        count = int(data.get("count", data.get("total", data.get("approximateCount", 0))))
        print(f"LEDs value (JQL): {count}")
        return count
    except Exception as e:
        print(f"LEDs value (JQL error): 0 - {e}")
        return 0


def jira_issue(issue_key: str, expand: str = "renderedFields,changelog") -> dict:
    return jira_get(
        f"issue/{issue_key}",
        params={"expand": expand},
    )


def extract_linked_from_issue(issue: dict) -> list[dict]:
    """Extract linked issues from a JIRA issue payload (outward + inward), with issuetype, priority, project, resolution."""
    links = (issue.get("fields") or {}).get("issuelinks") or []
    linked = []
    for link in links:
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        fields = other.get("fields") or {}
        issuetype = (fields.get("issuetype") or {}).get("name", "Unknown")
        priority = (fields.get("priority") or {}).get("name", "None")
        project_key = (fields.get("project") or {}).get("key", "")
        resolution = (fields.get("resolution") or {}).get("name", "")
        linked.append({
            "key": other.get("key", ""),
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "link_type": (link.get("type") or {}).get("name", ""),
            "issuetype": issuetype,
            "priority": priority,
            "project": project_key,
            "resolution": resolution,
        })
    return linked


# Linked issues with these types are excluded from the report (list and summary counts)
EXCLUDED_LINKED_ISSUE_TYPES = ("Task", "DevOps_Ticket", "RP_Feature")

# Excluded from Total Bug count (do not count these as bugs)
BUG_COUNT_EXCLUDE_ISSUE_TYPES = ("Internal PEDS", "PEDS Internal")
# Resolutions that exclude a linked issue from Total Bug count (matched case-insensitively)
BUG_COUNT_EXCLUDE_RESOLUTIONS = ("not a bug", "duplicate")


def _enrich_linked_resolutions(linked_by_key: dict[str, list[dict]]) -> None:
    """Fetch resolution for linked Bug issues when missing (API often omits it in issuelinks)."""
    keys_to_fetch: set[str] = set()
    for linked_list in linked_by_key.values():
        for l in linked_list:
            if (l.get("issuetype") or "").strip() == "Bug":
                res = (l.get("resolution") or "").strip()
                if not res and l.get("key"):
                    keys_to_fetch.add(l["key"])
    if not keys_to_fetch:
        return
    for issue_key in keys_to_fetch:
        try:
            data = jira_get(f"issue/{issue_key}", params={"fields": "resolution"})
            res_obj = (data.get("fields") or {}).get("resolution")
            resolution_name = (res_obj.get("name", "") if res_obj else "") or ""
            for linked_list in linked_by_key.values():
                for l in linked_list:
                    if l.get("key") == issue_key:
                        l["resolution"] = resolution_name
        except Exception:
            pass


def _is_leds_issue(linked: dict) -> bool:
    """True if linked issue belongs to project LEDS (by project key or issue key prefix).
    Project name is LEDS but Jira generates issue keys with prefix LED (e.g. LED-123).
    """
    project = (linked.get("project") or "").strip().upper()
    key = (linked.get("key") or "").strip().upper()
    if project == "LEDS":
        return True
    # Issue key prefix is LED for LEDS project (e.g. LED-123, LED-456)
    if key and (key.startswith("LED-") or key.startswith("LEDS-")):
        return True
    return False


def _is_bug_for_count(linked: dict) -> bool:
    """True if linked issue is Bug, not excluded (type/resolution/LEDS). Excludes issuetype PEDS Internal."""
    itype = (linked.get("issuetype") or "").strip()
    if itype != "Bug":
        return False
    # Exclude PEDS Internal and Internal PEDS (case-insensitive)
    if itype.upper() in (t.upper() for t in BUG_COUNT_EXCLUDE_ISSUE_TYPES):
        return False
    resolution = (linked.get("resolution") or "").strip().lower()
    if resolution and resolution in BUG_COUNT_EXCLUDE_RESOLUTIONS:
        return False
    if _is_leds_issue(linked):
        return False
    return True


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def linked_issue_included(linked: dict) -> bool:
    """True if linked issue should be included (not in excluded types)."""
    itype = (linked.get("issuetype") or "Unknown").strip()
    return itype not in EXCLUDED_LINKED_ISSUE_TYPES


def _dates_from_changelog(issue: dict) -> tuple[str, str, str, str]:
    """Return (ready_for_qa_date, deployment_completed_date, qa_ip_date, ready_for_deployment_date) as YYYY-MM-DD or ''."""
    ready_qa = ""
    deployment_done = ""
    qa_ip = ""
    ready_for_deployment = ""
    histories = (issue.get("changelog") or {}).get("histories") or []
    for h in sorted(histories, key=lambda x: x.get("created", "")):
        created = (h.get("created") or "")[:10]
        for item in h.get("items") or []:
            if (item.get("field") or "").lower() != "status":
                continue
            to_status = (item.get("toString") or "").strip().lower()
            if to_status and not ready_qa and "ready for qa" in to_status:
                ready_qa = created
            if to_status and not deployment_done and "deployment completed" in to_status:
                deployment_done = created
            if to_status and not qa_ip and ("qa ip" in to_status or "qa in progress" in to_status):
                qa_ip = created
            if to_status and not ready_for_deployment and "ready for deployment" in to_status:
                ready_for_deployment = created
    return (ready_qa, deployment_done, qa_ip, ready_for_deployment)


def _challenges_qa_ip_to_ready_for_deployment(qa_ip_date: str, ready_for_deployment_date: str) -> str:
    """Return challenges description from QA IP state to Ready for deployment status."""
    if not qa_ip_date and not ready_for_deployment_date:
        return "Challenges from QA IP state to Ready for deployment status: N/A"
    if qa_ip_date and ready_for_deployment_date:
        try:
            from datetime import datetime
            d1 = datetime.strptime(qa_ip_date, "%Y-%m-%d")
            d2 = datetime.strptime(ready_for_deployment_date, "%Y-%m-%d")
            days = (d2 - d1).days
            return f"Challenges from QA IP state to Ready for deployment status: {days} days ({qa_ip_date} to {ready_for_deployment_date})"
        except Exception:
            pass
    parts = []
    if qa_ip_date:
        parts.append(f"QA IP: {qa_ip_date}")
    if ready_for_deployment_date:
        parts.append(f"Ready for deployment: {ready_for_deployment_date}")
    return "Challenges from QA IP state to Ready for deployment status: " + ("; ".join(parts) if parts else "N/A")


def _get_ai_qa_summary(
    issue: dict,
    linked: list[dict],
    ready_qa: str,
    deployment_done: str,
    qa_ip: str,
    ready_for_deployment: str,
) -> str:
    """Call OpenAI to generate a short QA challenges summary. Returns empty string if not configured or on error."""
    if not OPENAI_API_KEY:
        return ""
    fields = issue.get("fields") or {}
    summary = (fields.get("summary") or "").strip()[:500]
    desc = strip_html((fields.get("description") or "")[:800])
    comments = (fields.get("comment") or {}).get("comments") or []
    comment_texts = [strip_html((c.get("body") or "")[:200]) for c in comments[-5:]]
    total_bugs = sum(1 for l in linked if _is_bug_for_count(l))
    p0 = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P0")
    p1 = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P1")
    internal_peds = sum(1 for l in linked if (l.get("issuetype") or "").strip() == "PEDS Internal")
    context = f"""JIRA issue summary: {summary}
Description (excerpt): {desc}
Key dates: Ready for QA {ready_qa}; Deployment completed {deployment_done}; QA IP {qa_ip}; Ready for deployment {ready_for_deployment}
Linked issues: {len(linked)} total; Bugs: {total_bugs} (P0: {p0}, P1: {p1}); Internal PEDS: {internal_peds}
Recent comments:
""" + "\n".join(f"- {t}" for t in comment_texts if t)
    prompt = """You are a QA manager. Based on the following JIRA issue context, write a brief QA challenges summary (2-4 sentences). Focus on: main QA challenges, impact of bug volume/priority, and timeline from QA to deployment. Be concise and professional. Output only the summary, no preamble."""
    try:
        from openai import OpenAI
        import httpx
        openai_verify = os.getenv("OPENAI_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
        openai_proxy = os.getenv("OPENAI_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if openai_proxy or not openai_verify:
            http_client = httpx.Client(verify=openai_verify, proxy=openai_proxy or None, timeout=60.0)
            client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You write concise QA challenge summaries for project reports."},
                {"role": "user", "content": prompt + "\n\n" + context},
            ],
            max_tokens=300,
        )
        text = (r.choices[0].message.content or "").strip()
        return text
    except Exception as e:
        print(f"  AI API failed for {issue.get('key', '?')}: {e}")
        return ""


def _get_ai_slack_channel_summary(slack_messages: list[dict], max_messages: int = 80) -> str:
    """Use OpenAI to summarize Slack channel messages for QA report. Focus: QA challenges, bugs/patterns, escalations, blockers, fix duration, dev-ops/env challenges. Returns empty if no key or no messages."""
    if not OPENAI_API_KEY or not slack_messages:
        return ""
    lines = []
    for m in slack_messages[-max_messages:]:
        ts = m.get("ts", "")[:10] if isinstance(m.get("ts"), str) else str(m.get("ts", ""))
        user = (m.get("user") or "?").strip()
        text = (m.get("text") or "").strip().replace("\n", " ").replace("\r", "")[:500]
        if text:
            lines.append(f"[{ts}] {user}: {text}")
    if not lines:
        return ""
    context = "\n".join(lines)
    prompt = """You are a QA manager. Below are recent messages from a Slack channel. Write a summary for a QA report. The summary MUST be at least 100 words. Cover ONLY what appears in the messages:

- QA challenges and testing blockers
- Bugs and any pattern of bugs (e.g. recurring areas, types)
- Escalations and blockers for testing
- Time or duration mentioned to fix bugs / resolve issues
- Dev-ops and environment-related challenges (e.g. deployment, config, env/LEDs issues)

If the messages do not mention a topic, omit it. Be factual. Use one or two paragraphs or 4–8 bullets so the total length is at least 100 words. Output only the summary, no preamble or headings."""

    try:
        from openai import OpenAI
        import httpx
        openai_verify = os.getenv("OPENAI_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
        openai_proxy = os.getenv("OPENAI_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if openai_proxy or not openai_verify:
            http_client = httpx.Client(verify=openai_verify, proxy=openai_proxy or None, timeout=60.0)
            client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You write concise QA and Slack channel summaries for project reports."},
                {"role": "user", "content": prompt + "\n\n---\n\n" + context},
            ],
            max_tokens=600,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"  AI Slack summary failed: {e}")
        return ""


def _format_slack_channel_summary(slack_messages: list[dict], max_messages: int = 25, max_text_len: int = 150) -> str:
    """Format Slack messages into a single summary string for CSV (one line per message)."""
    if not slack_messages:
        return ""
    lines = []
    for m in slack_messages[-max_messages:]:
        ts = m.get("ts", "")[:10] if isinstance(m.get("ts"), str) else str(m.get("ts", ""))
        user = (m.get("user") or "?").strip()
        text = (m.get("text") or "").strip().replace("\n", " ").replace("\r", "")
        if len(text) > max_text_len:
            text = text[:max_text_len] + "..."
        if text:
            lines.append(f"{ts} | {user}: {text}")
    return " ; ".join(lines) if lines else ""


def _generate_slides_with_ai(
    issue_keys: list[str],
    issues_detail: list[dict],
    linked_by_key: dict[str, list[dict]],
    slack_messages: list[dict],
    output_path: str,
    use_ai_summary: bool,
    publish_to_gamma: bool = False,
) -> None:
    """Use OpenAI to generate 2 slides from report data; optionally publish 5-slide deck to Gamma and return URL."""
    if not OPENAI_API_KEY:
        print("Slides not generated: OPENAI_API_KEY not set.")
        return
    key_to_issue = {i.get("key"): i for i in issues_detail if i.get("key")}
    parts = []
    total_bugs_all = 0
    p0_all = 0
    p1_all = 0
    internal_peds_all = 0
    leds_all = 0
    for key in issue_keys:
        if key not in key_to_issue:
            continue
        issue = key_to_issue[key]
        summary = (issue.get("fields") or {}).get("summary") or ""
        summary = (summary or "").strip().replace("\n", " ")[:300]
        linked = [l for l in linked_by_key.get(key, []) if linked_issue_included(l)]
        total_bugs = sum(1 for l in linked if _is_bug_for_count(l))
        p0_bugs = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P0")
        p1_bugs = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P1")
        internal_peds = sum(1 for l in linked if (l.get("issuetype") or "").strip() == "PEDS Internal")
        leds = sum(1 for l in linked if (l.get("issuetype") or "").strip() == "LEDs")
        ready_qa, deployment_done, qa_ip, ready_for_deployment = _dates_from_changelog(issue)
        challenges_text = _challenges_qa_ip_to_ready_for_deployment(qa_ip, ready_for_deployment)
        ai_summary = _get_ai_qa_summary(issue, linked, ready_qa, deployment_done, qa_ip, ready_for_deployment)
        total_bugs_all += total_bugs
        p0_all += p0_bugs
        p1_all += p1_bugs
        internal_peds_all += internal_peds
        leds_all += leds
        parts.append(f"""Issue: {key}
Summary: {summary}
Total Bug count: {total_bugs} | P0: {p0_bugs} | P1: {p1_bugs} | Internal PEDS: {internal_peds} | LEDs: {leds}
Challenges (QA IP to Ready for deployment): {challenges_text}
AI generated summary: {ai_summary or '(none)'}""")
    # Use AI-generated Slack summary when available (same focus as CSV)
    slack_summary = _get_ai_slack_channel_summary(slack_messages or [], max_messages=50) if (slack_messages and OPENAI_API_KEY) else ""
    if not slack_summary:
        slack_summary = _format_slack_channel_summary(slack_messages or [], max_messages=15)
    context = "\n\n---\n\n".join(parts)
    context += f"\n\nSlack channel summary: {slack_summary or '(none)'}"
    if len(issue_keys) > 1:
        context = f"Aggregate: Total Bugs {total_bugs_all}, P0 {p0_all}, P1 {p1_all}, Internal PEDS {internal_peds_all}, LEDs {leds_all}\n\n" + context
    prompt = """You are a QA manager creating a short presentation. Using ONLY the data below, generate exactly 2 slides. Focus on QA CHALLENGES by cause: Developer, Dev-ops, Environment (LEDs), and Resource issues.

Output format (use this exactly):
## Slide 1: QA Challenges – Overview by Cause
- Bullet 1
- Bullet 2
- Bullet 3
(3-5 bullets: summarize QA challenges due to developers, dev-ops, environment/LEDs, and resource issues if any)

## Slide 2: QA Challenges – Details (Developer, Dev-ops, Environment, Resource)
- Bullet 1
- Bullet 2
- Bullet 3
(3-5 bullets: call out specific challenges from the data – e.g. developer: bug volume/code quality; dev-ops: deployment/config; environment: LEDs, flakiness; resource: capacity/tools. Use "None" or "N/A" if no data for a category.)

Use: JIRA issue summary, Total Bug count, P0/P1 count, LEDs, Internal PEDS, Challenges text, and AI summary. Be concise; each bullet one line. No preamble."""

    try:
        from openai import OpenAI
        import httpx
        openai_verify = os.getenv("OPENAI_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
        openai_proxy = os.getenv("OPENAI_HTTP_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if openai_proxy or not openai_verify:
            http_client = httpx.Client(verify=openai_verify, proxy=openai_proxy or None, timeout=60.0)
            client = OpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You generate concise QA presentation slides in markdown."},
                {"role": "user", "content": prompt + "\n\n---\n\nData:\n" + context},
            ],
            max_tokens=600,
        )
        text = (r.choices[0].message.content or "").strip()
        if not text:
            return
        slides_path = Path(output_path).parent / (Path(output_path).stem + "_slides.md")
        Path(slides_path).write_text(text, encoding="utf-8")
        print(f"2 slides written to {slides_path}")

        # Gamma app: 5-slide presentation (use --- between slides for Gamma)
        gamma_prompt = """You are a QA manager creating a presentation for Gamma app. Using ONLY the data below, generate exactly 5 slides. Focus on QA CHALLENGES by cause: Developer, Dev-ops, Environment (LEDs), and Resource issues.

Output format: each slide is a section. Separate each slide with a line containing only: ---

Slide 1: Title slide – QA Project Challenges Presentation
Slide 2: Executive summary & key metrics – Scope (issues covered), Total Bug count, P0/P1, LEDs, Internal PEDS. 3-5 bullets.
Slide 3: QA challenges – Developer & Dev-ops – Bug volume/code quality, deployment pipeline, config, release timing. Use data. 3-6 bullets.
Slide 4: QA challenges – Environment (LEDs) & Resource – Environment flakiness, LEDs, test env; capacity/tooling if any. 3-6 bullets.
Slide 5: Timeline, risks & next steps – Ready for QA, Deployment completed, QA IP to Ready for deployment; risks/recommendations; conclusion. 3-6 bullets.

Use the provided data. Each slide: title line then 3-6 bullet points. Call out Developer, Dev-ops, Environment (LEDs), Resource where relevant. No preamble. Start with Slide 1."""

        try:
            r2 = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You generate QA presentation outlines focused on challenges due to Developer, Dev-ops, Environment (LEDs), and Resource. Use --- on its own line between slides."},
                    {"role": "user", "content": gamma_prompt + "\n\n---\n\nData:\n" + context},
                ],
                max_tokens=1200,
            )
            gamma_text = (r2.choices[0].message.content or "").strip()
            if gamma_text:
                gamma_path = Path(output_path).parent / (Path(output_path).stem + "_slides_gamma.md")
                Path(gamma_path).write_text(gamma_text, encoding="utf-8")
                print(f"5-slide Gamma outline written to {gamma_path}")
                if publish_to_gamma:
                    gamma_url = _publish_to_gamma(gamma_path)
                    if gamma_url:
                        print(f"\n  Gamma PPT URL (share this): {gamma_url}\n")
        except Exception as e2:
            print(f"Gamma outline not generated: {e2}")
    except Exception as e:
        print(f"Slides not generated: {e}")


def _publish_to_gamma(gamma_md_path: Path) -> str | None:
    """Create a 5-slide presentation on Gamma from the outline file; return the shareable gamma URL."""
    if not GAMMA_API_KEY:
        print("Gamma publish skipped: GAMMA_API_KEY not set in .env")
        return None
    if not gamma_md_path.exists():
        print(f"Gamma publish skipped: {gamma_md_path} not found. Run with --slides first.")
        return None
    outline_text = gamma_md_path.read_text(encoding="utf-8")
    if not outline_text.strip():
        return None
    url = "https://public-api.gamma.app/v1.0/generations"
    headers = {"X-API-KEY": GAMMA_API_KEY, "Content-Type": "application/json"}
    payload = {
        "inputText": outline_text,
        "textMode": "preserve",
        "format": "presentation",
        "numCards": 5,
        "cardSplit": "inputTextBreaks",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60, verify=GAMMA_VERIFY_SSL)
        r.raise_for_status()
        data = r.json()
        gen_id = data.get("generationId")
        if not gen_id:
            print("Gamma API did not return generationId:", data)
            return None
        print("Gamma creating presentation (polling every 5s)...")
        for _ in range(60):
            time.sleep(5)
            r2 = requests.get(f"https://public-api.gamma.app/v1.0/generations/{gen_id}", headers=headers, timeout=30, verify=GAMMA_VERIFY_SSL)
            r2.raise_for_status()
            info = r2.json()
            status = info.get("status", "")
            if status == "completed":
                gamma_url = info.get("gammaUrl", "")
                if gamma_url:
                    return gamma_url
                print("Gamma completed but no gammaUrl in response:", info)
                return None
            if status == "failed":
                print("Gamma generation failed:", info.get("error", info))
                return None
        print("Gamma timed out waiting for completion.")
        return None
    except requests.RequestException as e:
        print(f"Gamma API error: {e}")
        return None


def _write_csv_report(
    issue_keys: list[str],
    linked_by_key: dict[str, list[dict]],
    issues_detail: list[dict],
    csv_path: Path,
    use_ai_summary: bool = False,
    slack_messages: list[dict] | None = None,
) -> None:
    """Write CSV with header including Summary, Challenges, AI summary, and Slack channel summary."""
    key_to_issue = {i.get("key"): i for i in issues_detail if i.get("key")}
    use_ai = use_ai_summary and bool(OPENAI_API_KEY)
    if use_ai:
        print("Using AI to generate QA challenges summary for CSV...")
    # Slack channel summary: AI-generated from channel messages when OpenAI key and messages exist
    if OPENAI_API_KEY and (slack_messages or []):
        print("Using AI to generate Slack channel summary for CSV...")
        slack_summary = _get_ai_slack_channel_summary(slack_messages or [])
        if slack_summary:
            print("AI generated Slack summary:\n" + slack_summary)
        if not slack_summary:
            slack_summary = _format_slack_channel_summary(slack_messages or [])
    else:
        slack_summary = _format_slack_channel_summary(slack_messages or [])
    headers = [
        "JIRA Issue id",
        "Summary",
        "Total Number of bugs",
        "P0 bug count",
        "P1 Bug Count",
        "Internal PEDS",
        "LEDs",
        "Ready for QA date",
        "Deployment completed date",
        "Challenges (QA IP to Ready for deployment)",
        "AI generated summary",
        "Slack channel summary",
    ]
    rows = []
    for key in issue_keys:
        if key not in key_to_issue:
            continue
        issue = key_to_issue[key]
        summary = (issue.get("fields") or {}).get("summary") or ""
        summary = (summary or "").strip().replace("\n", " ").replace("\r", "")
        linked = [l for l in linked_by_key.get(key, []) if linked_issue_included(l)]
        total_bug_count_jql = f'issue in linkedIssues("{key}") AND issuetype = Bug AND project != LEDS AND resolution not in ("Not a Bug", "Duplicate")'
        print(f"Total Bug count query: {total_bug_count_jql}")
        # Exclude LEDS from Total Bugs (by project or issue key prefix)
        bugs_list = [l for l in linked if _is_bug_for_count(l) and not _is_leds_issue(l)]
        total_bugs = len(bugs_list)
        print(f"Total Bug count for {key}: {total_bugs}")
        if bugs_list:
            # Bifurcate count by issuetype
            by_type: dict[str, list[str]] = {}
            for l in bugs_list:
                itype = (l.get("issuetype") or "Unknown").strip()
                by_type.setdefault(itype, []).append(l.get("key", ""))
            type_counts = ", ".join(f"{t}: {len(keys)}" for t, keys in sorted(by_type.items()))
            print(f"Total Bugs by issuetype for {key}: {type_counts}")
            print(f"Total Bugs list for {key}: {', '.join(l.get('key', '') for l in bugs_list)}")
        else:
            print(f"Total Bugs list for {key}: (none)")
        p0_bugs = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P0")
        p1_bugs = sum(1 for l in linked if _is_bug_for_count(l) and (l.get("priority") or "").strip() == "P1")
        peds_internal_list = [l for l in linked if (l.get("issuetype") or "").strip() == "PEDS Internal"]
        internal_peds = len(peds_internal_list)
        if peds_internal_list:
            print(f"PEDS Internal ticket IDs for {key}: {', '.join(l.get('key', '') for l in peds_internal_list)}")
        else:
            print(f"PEDS Internal ticket IDs for {key}: (none)")
        # LEDs column: total count where project = LEDS and linked to this JIRA issue (from command)
        # Try JQL first; fallback to counting from issue's issuelinks when JQL fails
        leds_count = jira_leds_count_linked_to(key)
        if leds_count == 0:
            all_linked = linked_by_key.get(key, [])
            leds_count = sum(1 for l in all_linked if (l.get("project") or "").strip().upper() == "LEDS")
            print(f"LEDs value for {key} (fallback from issuelinks): {leds_count}")
        else:
            print(f"LEDs value for {key}: {leds_count}")
        leds_value = str(leds_count)
        ready_qa, deployment_done, qa_ip, ready_for_deployment = _dates_from_changelog(issue)
        challenges_text = _challenges_qa_ip_to_ready_for_deployment(qa_ip, ready_for_deployment)
        ai_summary = _get_ai_qa_summary(issue, linked, ready_qa, deployment_done, qa_ip, ready_for_deployment) if use_ai else ""
        rows.append([
            key, summary, total_bugs, p0_bugs, p1_bugs, internal_peds, leds_value,
            ready_qa, deployment_done, challenges_text, ai_summary, slack_summary,
        ])
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return None


def fetch_slack_channel_via_api(channel_id: str, limit: int = 500) -> list[dict]:
    """Fetch recent messages from a Slack channel via Slack Web API. Returns same format as collect_slack_messages."""
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
                print(f"  Slack API error: {data.get('error', 'unknown')}")
                break
            for msg in data.get("messages") or []:
                if msg.get("type") != "message" or msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                messages.append({
                    "ts": msg.get("ts", ""),
                    "user": msg.get("user", ""),
                    "text": text,
                    "channel": channel_id,
                })
            if not data.get("has_more"):
                break
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return messages
    except requests.RequestException as e:
        print(f"  Slack API request failed: {e}")
        return []


def collect_slack_messages(slack_path: str) -> list[dict]:
    """Load Slack messages from export folder or slack_channel_messages.json."""
    path = Path(slack_path)
    if not path.exists():
        return []

    # Prefer explicit channel messages file
    json_file = path / "slack_channel_messages.json" if path.is_dir() else path
    if path.is_file() and path.suffix.lower() == ".json":
        json_file = path
    if json_file.exists():
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else data.get("messages", [])
        except (json.JSONDecodeError, TypeError):
            pass

    # Slack export: look for channel folders and messages
    messages = []
    for channel_dir in path.iterdir() if path.is_dir() else []:
        if not channel_dir.is_dir():
            continue
        for day_file in channel_dir.glob("*.json"):
            try:
                with open(day_file, encoding="utf-8") as f:
                    day_data = json.load(f)
                for msg in day_data if isinstance(day_data, list) else []:
                    if isinstance(msg, dict) and msg.get("type") == "message" and msg.get("text"):
                        messages.append({
                            "ts": msg.get("ts", ""),
                            "user": msg.get("user", ""),
                            "text": msg.get("text", ""),
                            "channel": channel_dir.name,
                        })
            except (json.JSONDecodeError, TypeError, OSError):
                continue
    return messages


def build_report(
    project_key: str | None,
    issue_keys: list[str],
    issues_detail: list[dict],
    linked_by_key: dict[str, list[dict]],
    slack_messages: list[dict],
    output_path: str,
    use_ai_summary: bool = False,
    generate_slides: bool = False,
    publish_to_gamma: bool = False,
) -> None:
    lines = [
        "# QA Project Challenges",
        "",
        "## Scope",
        "",
    ]
    if project_key:
        lines.append(f"- **Project:** {project_key}")
    if issue_keys:
        lines.append(f"- **Issues:** {', '.join(issue_keys)}")
    lines.extend(["", "---", ""])

    # JIRA challenges
    lines.append("## Challenges from JIRA")
    lines.append("")
    for issue in issues_detail:
        key = issue.get("key", "?")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = (fields.get("status") or {}).get("name", "")
        desc = strip_html((fields.get("description") or "")[:500])
        lines.append(f"### {key}: {summary}")
        lines.append("")
        lines.append(f"- **Status:** {status}")
        if desc:
            lines.append(f"- **Description (excerpt):** {desc}...")
        lines.append("")

        comments = (fields.get("comment") or {}).get("comments") or []
        if comments:
            lines.append("**Comments:**")
            for c in comments[-10:]:  # last 10
                author = (c.get("author") or {}).get("displayName", "?")
                body = strip_html((c.get("body") or "")[:300])
                lines.append(f"- *{author}:* {body}")
            lines.append("")

        linked = [l for l in linked_by_key.get(key, []) if linked_issue_included(l)]
        if linked:
            lines.append("**Linked issues:**")
            for l in linked:
                lines.append(f"- {l.get('link_type', '')}: **{l.get('key')}** — {l.get('summary', '')} ({l.get('status', '')})")
            lines.append("")
        lines.append("")

    # Linked issues summary: total, by type (Bugs, Internal PEDS, etc.), by priority (excluded types omitted)
    all_linked = []
    for lst in linked_by_key.values():
        all_linked.extend(l for l in lst if linked_issue_included(l))
    # Deduplicate by key (same issue may be linked from multiple parents)
    seen_keys: set[str] = set()
    unique_linked: list[dict] = []
    for li in all_linked:
        k = li.get("key", "")
        if k and k not in seen_keys:
            seen_keys.add(k)
            unique_linked.append(li)
    type_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    for li in unique_linked:
        t = li.get("issuetype", "Unknown") or "Unknown"
        type_counts[t] = type_counts.get(t, 0) + 1
        p = li.get("priority", "None") or "None"
        priority_counts[p] = priority_counts.get(p, 0) + 1
    lines.extend(["---", "", "## Linked issues summary", ""])
    lines.append(f"- **Total linked issues (unique):** {len(unique_linked)}")
    lines.append("")
    lines.append("### By issue type")
    lines.append("")
    for itype in sorted(type_counts.keys(), key=lambda x: (-type_counts[x], x)):
        lines.append(f"- **{itype}:** {type_counts[itype]}")
    lines.append("")
    lines.append("### By priority")
    lines.append("")
    priority_order = ("Highest", "High", "Medium", "Low", "Lowest", "None")
    for p in priority_order:
        if p in priority_counts:
            lines.append(f"- **{p}:** {priority_counts[p]}")
    for p in sorted(priority_counts.keys()):
        if p not in priority_order:
            lines.append(f"- **{p}:** {priority_counts[p]}")
    lines.append("")

    # Slack
    if slack_messages:
        lines.extend(["---", "", "## Challenges from Slack (project channel)", ""])
        for m in slack_messages[-30:]:
            ts = m.get("ts", "")[:10] if isinstance(m.get("ts"), str) else str(m.get("ts", ""))
            user = m.get("user", "?")
            text = (m.get("text") or "").strip()
            if text:
                lines.append(f"- **{ts}** | {user}: {text[:200]}")
        lines.append("")

    # Summary
    lines.extend(["---", "", "## Summary for presentation", ""])
    lines.append(f"- Total issues reviewed: {len(issues_detail)}")
    lines.append(f"- Total linked issues (unique): {len(unique_linked)}")
    if slack_messages:
        lines.append(f"- Slack messages included: {len(slack_messages)}")
    lines.append("")
    lines.append("Use the sections above as talking points: JIRA comments and linked issues often surface blockers, env issues, and scope changes.")
    lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {output_path}")

    # CSV export: one row per JIRA issue with bug/PEDS/LEDs counts and status dates
    csv_path = Path(output_path).with_suffix(".csv")
    _write_csv_report(issue_keys, linked_by_key, issues_detail, csv_path, use_ai_summary=use_ai_summary, slack_messages=slack_messages)
    print(f"CSV written to {csv_path}")

    # AI-generated 2 slides from report data (AI summary, bug counts, challenges, etc.)
    if generate_slides:
        _generate_slides_with_ai(issue_keys, issues_detail, linked_by_key, slack_messages, output_path, use_ai_summary, publish_to_gamma=publish_to_gamma)


def main():
    ap = argparse.ArgumentParser(description="Fetch QA project challenges from JIRA and Slack")
    ap.add_argument("--project", "-p", help="JIRA project key (e.g. PROJ)")
    ap.add_argument("--issues", "-i", help="Comma-separated JIRA issue keys (e.g. PROJ-101,PROJ-102)")
    ap.add_argument("--slack", "-s", default=SLACK_EXPORT_PATH, help="Slack export path or JSON file")
    ap.add_argument("--output", "-o", default="qa_challenges_report.md", help="Output Markdown file")
    ap.add_argument("--limit", "-n", type=int, default=50, help="Max issues when using --project")
    ap.add_argument("--ai", action="store_true", help="Use OpenAI to generate QA challenges summary in CSV (requires OPENAI_API_KEY in .env)")
    ap.add_argument("--slides", action="store_true", help="Use AI to generate 2 slides + 5-slide Gamma outline")
    ap.add_argument("--gamma-publish", action="store_true", help="Publish 5-slide deck to Gamma and print shareable PPT URL (requires GAMMA_API_KEY, run with --slides)")
    args = ap.parse_args()
    use_ai_summary = args.ai or os.getenv("OPENAI_QA_SUMMARY", "").lower() in ("1", "true", "yes")
    generate_slides = args.slides or args.gamma_publish
    publish_to_gamma = args.gamma_publish

    issue_keys: list[str] = []
    if args.issues:
        issue_keys = [k.strip() for k in args.issues.split(",") if k.strip()]
    if args.project and not issue_keys:
        jql = f"project = {args.project} ORDER BY updated DESC"
        issues = jira_search(jql, "summary,status,description,comment,issuelinks", limit=args.limit)
        issue_keys = [i.get("key") for i in issues if i.get("key")]

    if not issue_keys:
        print("No issues to fetch. Use --project PROJ or --issues KEY1,KEY2")
        return

    print(f"Fetching {len(issue_keys)} issues (with comments and linked issues)...")
    issues_detail = []
    linked_by_key = {}
    for key in issue_keys:
        try:
            raw = jira_issue(key)
            issues_detail.append(raw)
            linked_by_key[key] = extract_linked_from_issue(raw)
        except requests.HTTPError as e:
            print(f"  Skip {key}: {e}")

    # Fetch resolution for linked Bugs when missing (so we can exclude "Not a Bug" / "Duplicate")
    _enrich_linked_resolutions(linked_by_key)

    # Slack: prefer API if token + channel ID set, else load from file/export path
    if SLACK_BOT_TOKEN and SLACK_CHANNEL_ID:
        print("Fetching Slack channel via API...")
        slack_messages = fetch_slack_channel_via_api(SLACK_CHANNEL_ID)
        if slack_messages:
            print(f"Loaded {len(slack_messages)} Slack messages from channel {SLACK_CHANNEL_ID}.")
    else:
        slack_messages = collect_slack_messages(args.slack) if args.slack else []
        if slack_messages:
            print(f"Loaded {len(slack_messages)} Slack messages (from file/export).")

    build_report(
        project_key=args.project,
        issue_keys=issue_keys,
        issues_detail=issues_detail,
        linked_by_key=linked_by_key,
        slack_messages=slack_messages,
        output_path=args.output,
        use_ai_summary=use_ai_summary,
        generate_slides=generate_slides,
        publish_to_gamma=publish_to_gamma,
    )


if __name__ == "__main__":
    main()
