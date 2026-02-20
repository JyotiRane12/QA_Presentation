"""JIRA API client and validation. All credentials from environment variables."""

import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

# Config from env only - never hardcode tokens
JIRA_BASE = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
JIRA_EMAIL = (os.getenv("JIRA_EMAIL") or "").strip()
JIRA_TOKEN = (os.getenv("JIRA_API_TOKEN") or "").strip()
JIRA_VERIFY_SSL = (os.getenv("JIRA_VERIFY_SSL", "true").lower() not in ("0", "false", "no"))

if not JIRA_VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Valid JIRA status field structure
REQUIRED_ISSUE_FIELDS = ("fields", "key")
REQUIRED_LINKED_FIELDS = ("key", "fields")
VALID_STATUS_STRUCTURE = ("name",)


def _validate_credentials() -> None:
    """Raise if JIRA credentials are missing."""
    if not JIRA_BASE or not JIRA_EMAIL or not JIRA_TOKEN:
        raise ValueError(
            "JIRA credentials missing. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env"
        )


def _validate_issue_structure(issue: dict) -> None:
    """Validate JIRA issue has required fields before processing."""
    if not isinstance(issue, dict):
        raise ValueError("Issue must be a dict")
    for field in REQUIRED_ISSUE_FIELDS:
        if field not in issue:
            raise ValueError(f"Issue missing required field: {field}")
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError("Issue fields must be a dict")
    status = fields.get("status")
    if status is not None and not isinstance(status, dict):
        logger.warning("JIRA status field has unexpected structure: %s", type(status))


def _validate_linked_issue(linked: dict) -> None:
    """Validate linked issue structure."""
    if not isinstance(linked, dict):
        return
    status = linked.get("status")
    if status and not isinstance(status, str):
        logger.warning("Linked issue status expected string, got %s", type(status))


def get_issue(issue_key: str, expand: str = "renderedFields,changelog") -> dict:
    """Fetch JIRA issue. Handles API failures gracefully."""
    _validate_credentials()
    url = f"{JIRA_BASE}/rest/api/2/issue/{issue_key}"
    try:
        r = requests.get(
            url,
            params={"expand": expand},
            auth=(JIRA_EMAIL, JIRA_TOKEN),
            headers={"Accept": "application/json"},
            timeout=30,
            verify=JIRA_VERIFY_SSL,
        )
        r.raise_for_status()
        data = r.json()
        _validate_issue_structure(data)
        return data
    except requests.RequestException as e:
        logger.exception("JIRA API request failed for %s: %s", issue_key, e)
        raise


def extract_linked_from_issue(issue: dict) -> list[dict]:
    """Extract linked issues with validated structure."""
    _validate_issue_structure(issue)
    links = (issue.get("fields") or {}).get("issuelinks") or []
    linked = []
    for link in links:
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        fields = other.get("fields") or {}
        status_obj = fields.get("status")
        status = (status_obj.get("name", "") if isinstance(status_obj, dict) else "") or ""
        issuetype_obj = fields.get("issuetype")
        issuetype = (issuetype_obj.get("name", "Unknown") if isinstance(issuetype_obj, dict) else "Unknown") or "Unknown"
        project_obj = fields.get("project")
        project_key = (project_obj.get("key", "") if isinstance(project_obj, dict) else "") or ""
        resolution_obj = fields.get("resolution")
        resolution = (resolution_obj.get("name", "") if isinstance(resolution_obj, dict) else "") or ""
        priority_obj = fields.get("priority")
        priority = (priority_obj.get("name", "") if isinstance(priority_obj, dict) else "") or ""
        assignee_obj = fields.get("assignee")
        assignee = ""
        if isinstance(assignee_obj, dict):
            assignee = (assignee_obj.get("displayName") or assignee_obj.get("emailAddress") or "") or ""
        elif isinstance(assignee_obj, str):
            assignee = assignee_obj
        item = {
            "key": other.get("key", ""),
            "summary": fields.get("summary", ""),
            "status": str(status),
            "issuetype": str(issuetype),
            "project": str(project_key),
            "resolution": str(resolution),
            "priority": str(priority),
            "assignee": str(assignee),
        }
        _validate_linked_issue(item)
        linked.append(item)
    return linked


def enrich_linked_resolutions(linked: list[dict]) -> None:
    """Fetch resolution for linked Bugs when missing. JIRA API often omits it in issuelinks."""
    to_fetch = [
        l.get("key") for l in linked
        if (l.get("issuetype") or "").strip() == "Bug"
        and not (l.get("resolution") or "").strip()
        and l.get("key")
    ]
    for key in to_fetch:
        try:
            _validate_credentials()
            url = f"{JIRA_BASE}/rest/api/2/issue/{key}"
            r = requests.get(
                url,
                params={"fields": "resolution"},
                auth=(JIRA_EMAIL, JIRA_TOKEN),
                headers={"Accept": "application/json"},
                timeout=15,
                verify=JIRA_VERIFY_SSL,
            )
            r.raise_for_status()
            res = (r.json().get("fields") or {}).get("resolution")
            name = (res.get("name", "") if isinstance(res, dict) else "") or ""
            for l in linked:
                if l.get("key") == key:
                    l["resolution"] = name
                    break
        except Exception:
            pass


def dates_from_changelog(issue: dict) -> dict:
    """Extract dates from issue changelog."""
    _validate_issue_structure(issue)
    ready_qa = ""
    qa_start = ""
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
    duedate = fields.get("duedate")
    target_release = duedate[:10] if isinstance(duedate, str) and duedate else ""
    return {
        "ready_for_qa": ready_qa,
        "qa_start": qa_start,
        "bug_fixing_ip": bug_fixing_ip,
        "target_release": target_release,
    }
