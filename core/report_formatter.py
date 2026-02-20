"""Report formatting logic. Pure functions for bug counts, dates, report building.

Bug count logic MUST follow Rules/BugCount.cursorrules:
- Total Bugs, P0, P1, Bugs With Dev, Bugs With QA, Closed Bugs
"""

from datetime import datetime
from pathlib import Path

# Source of truth: Rules/BugCount.cursorrules – always align bug count logic with this file
BUG_COUNT_RULES_FILE = Path(__file__).resolve().parent.parent / "Rules" / "BugCount.cursorrules"

# Global filter (BugCount.cursorrules): Resolution must NOT be Not a Bug, Duplicate
RESOLUTION_EXCLUDE = ("not a bug", "duplicate")
# Exclude cancelled or rejected tickets
STATUS_EXCLUDE = ("cancelled", "rejected")

# Section 4: Bugs With Dev – status must be one of these (BugCount.cursorrules)
# Includes common JIRA aliases: dev ip, analysis ip, dev review
DEV_STATUSES = (
    "open",
    "tech feasibility",
    "ready for development",
    "development ip",
    "dev ip",
    "analysis ip",
    "development review",
    "dev review",
    "bug fixing ip",
)
# Section 5: Bugs With QA – status must be one of these (BugCount.cursorrules)
# Includes common aliases: qa ip
QA_STATUSES = (
    "ready for qa",
    "qa in progress",
    "qa ip",
    "qa review",
    "ready for sit",
    "sit in progress",
    "ready to release",
    "ready for release",
)
# Section 6: Closed Bugs – Status = Released (or Closed for JIRA workflows that use it)
CLOSED_STATUSES = ("released", "closed")
# Section 7: Preprod Status – include only these statuses (BugCount.cursorrules)
PREPROD_STATUSES = ("ready for sit", "sit in progress", "ready for release", "ready to release")
# Deployed/Released – UAT and Preprod both = Completed
DEPLOYED_STATUSES = ("released", "closed", "beta deployed", "deployment completed")
# Section 8: UAT Status – include only these statuses (BugCount.cursorrules)
UAT_STATUSES = ("ready for uat", "uat in progress", "product uat ip")
# Bugs with Product (Approval/Discussion) – status in Ready for UAT, Product UAT IP
BUGS_WITH_PRODUCT_STATUSES = ("ready for uat", "product uat ip")
# Internal PEDS – linked issue type (PEDS Internal or Internal PEDS)
INTERNAL_PEDS_ISSUE_TYPES = ("peds internal", "internal peds")

OPTIONAL_SECTION_KEYS = frozenset({
    "ready_for_qa_date", "qa_start_date", "one_round_of_testing_completion",
    "total_bugs", "bugs_with_dev", "bugs_with_qa", "bugs_with_product", "closed_bugs",
    "challenges", "environment_issue", "internal_peds", "targetted_release_date", "uat_status", "preprod_status",
})


def _is_led_linked(linked: dict) -> bool:
    """True if linked issue is from LEDS project."""
    key = (linked.get("key") or "").strip().upper()
    proj = (linked.get("project") or "").strip().upper()
    if proj == "LEDS":
        return True
    if key and (key.startswith("LED-") or key.startswith("LEDS-")):
        return True
    return False


def bug_counts(linked: list[dict]) -> tuple[int, int, int, int, int, int, int]:
    """Return (total, with_dev, with_qa, with_product, closed, p0, p1). Follows Rules/BugCount.cursorrules."""
    resolution_lower = lambda l: (l.get("resolution") or "").strip().lower()
    status_lower = lambda l: (l.get("status") or "").strip().lower()
    bugs = [
        l for l in linked
        if (l.get("issuetype") or "").strip() == "Bug"
        and not _is_led_linked(l)
        and resolution_lower(l) not in RESOLUTION_EXCLUDE
        and status_lower(l) not in STATUS_EXCLUDE
    ]
    total = len(bugs)
    priority_upper = lambda l: (l.get("priority") or "").strip().upper()
    with_dev = sum(1 for l in bugs if status_lower(l) in DEV_STATUSES)
    with_qa = sum(1 for l in bugs if status_lower(l) in QA_STATUSES)
    with_product = sum(1 for l in bugs if status_lower(l) in BUGS_WITH_PRODUCT_STATUSES)
    # Closed Bugs: Status=Released only; excludes Not a Bug, Duplicate (filtered in bugs via RESOLUTION_EXCLUDE)
    closed_bugs = sum(1 for l in bugs if status_lower(l) in CLOSED_STATUSES)
    p0 = sum(1 for l in bugs if priority_upper(l) == "P0")
    p1 = sum(1 for l in bugs if priority_upper(l) == "P1")
    return (total, with_dev, with_qa, with_product, closed_bugs, p0, p1)


def bug_count_jql_queries(jira_id: str) -> dict[str, str]:
    """Return JQL queries for Total Bugs, Closed Bugs, P0, P1. Use in JIRA to verify counts.
    Follows Rules/BugCount.cursorrules."""
    base = (
        f'issue in linkedIssues("{jira_id}") '
        'AND issuetype = Bug '
        'AND project != LEDS '
        'AND resolution NOT IN ("Not a Bug", "Duplicate") '
        "AND status NOT IN (Cancelled, Rejected)"
    )
    internal_peds_base = f'issue in linkedIssues("{jira_id}") AND issuetype IN ("PEDS Internal", "Internal PEDS")'
    return {
        "total_bugs": base,
        "closed_bugs": base + ' AND status IN (Released, Closed)',
        "bugs_with_product": base + ' AND status IN ("Ready for UAT", "Product UAT IP")',
        "internal_peds": internal_peds_base,
        "p0": base + ' AND priority = P0',
        "p1": base + ' AND priority = P1',
    }


def bug_keys(linked: list[dict]) -> list[str]:
    """Return JIRA keys of bugs. Follows Rules/BugCount.cursorrules (excludes LED, Not a Bug, Duplicate, cancelled, rejected)."""
    res = lambda l: (l.get("resolution") or "").strip().lower()
    status_lower = lambda l: (l.get("status") or "").strip().lower()
    return [
        l.get("key", "") for l in linked
        if (l.get("issuetype") or "").strip() == "Bug"
        and l.get("key")
        and not _is_led_linked(l)
        and res(l) not in RESOLUTION_EXCLUDE
        and status_lower(l) not in STATUS_EXCLUDE
    ]


def leds_info(linked: list[dict]) -> tuple[int, list[dict]]:
    """Return (led_count, list of open LED objects with key, summary, assignee). Follows Rules/BugCount.cursorrules Section 9."""
    def is_led(l):
        proj = (l.get("project") or "").strip().upper()
        key = (l.get("key") or "").strip().upper()
        if proj == "LEDS":
            return True
        if key and (key.startswith("LED-") or key.startswith("LEDS-")):
            return True
        return False
    leds = [l for l in linked if is_led(l)]
    open_leds = [
        {"key": l.get("key", ""), "summary": (l.get("summary") or "")[:80], "assignee": l.get("assignee") or "Unassigned"}
        for l in leds if (l.get("status") or "").strip().lower() == "open"
    ]
    return (len(leds), open_leds)


def internal_peds_count(linked: list[dict]) -> int:
    """Count linked issues with issuetype PEDS Internal or Internal PEDS. Follows Rules/BugCount.cursorrules Section 10."""
    itype_lower = lambda l: (l.get("issuetype") or "").strip().lower()
    return sum(1 for l in linked if itype_lower(l) in INTERNAL_PEDS_ISSUE_TYPES)


def format_date(ymd: str) -> str:
    """Format YYYY-MM-DD to '18th Feb 2026'. Returns 'N/A' if empty/invalid."""
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


def uat_status(issue: dict) -> str:
    """UAT Status from issue fields. Follows Rules/BugCount.cursorrules Section 8.
    Released/Beta Deployed/Deployment Completed → Completed. Preprod In-progress → Completed. UAT statuses → In-UAT. Else Pending."""
    status = (issue.get("fields") or {}).get("status") or {}
    name = (status.get("name") or "").strip().lower()
    if name in DEPLOYED_STATUSES:
        return "Completed"
    if name in PREPROD_STATUSES:
        return "Completed"
    if name in UAT_STATUSES:
        return "In-UAT"
    return "Pending"


def preprod_status(issue: dict) -> str:
    """Preprod Status from issue fields. Follows Rules/BugCount.cursorrules Section 7.
    Released/Beta Deployed/Deployment Completed → Completed. Preprod statuses → In-progress. Else Pending."""
    status = (issue.get("fields") or {}).get("status") or {}
    name = (status.get("name") or "").strip().lower()
    if name in DEPLOYED_STATUSES:
        return "Completed"
    if name in PREPROD_STATUSES:
        return "In-progress"
    return "Pending"


def build_report(
    jira_id: str,
    issue: dict,
    linked: list[dict],
    dates: dict,
    challenges: str,
    led_count: int,
    open_leds: list[dict],
    today_str: str,
    include_optional: set[str] | None = None,
) -> str:
    """Build report text. Mandatory: QA Update, JIRA ID, JIRA Title. Environment Issue follows Rules/BugCount.cursorrules Section 9."""
    include_optional = include_optional or set()
    fields = issue.get("fields") or {}
    title = (fields.get("summary") or "").strip()
    total_bugs, with_dev, with_qa, with_product, closed_bugs, p0, p1 = bug_counts(linked)
    internal_peds = internal_peds_count(linked)
    uat = uat_status(issue)
    preprod = preprod_status(issue)

    # Environment Issue per BugCount.cursorrules Section 9
    if led_count == 0:
        env_line = "0\nNo LED tickets linked to JIRA"
    elif open_leds:
        env_line = f"{led_count}\n{len(open_leds)} LED(s) in Open status:\n"
        env_line += "\n".join(
            f"• {o.get('key', '')} – {o.get('summary', '')} (Assignee: {o.get('assignee', 'Unassigned')})"
            for o in open_leds
        )
    else:
        env_line = f"{led_count}\nNo LED tickets are currently in Open status"

    block = [
        f"*QA Update* – {today_str}",
        "",
        f"*JIRA ID* – {jira_id}",
        f"*JIRA Title* – {title}",
    ]
    if "ready_for_qa_date" in include_optional or "qa_start_date" in include_optional or "one_round_of_testing_completion" in include_optional:
        block.append("")
    if "ready_for_qa_date" in include_optional:
        block.append(f"*Ready For QA Date* – {format_date(dates['ready_for_qa'])}")
    if "qa_start_date" in include_optional:
        block.append(f"*QA Start Date* – {format_date(dates['qa_start'])}")
    if "one_round_of_testing_completion" in include_optional:
        block.append(f"*One Round Of Testing Completion* – {format_date(dates['bug_fixing_ip']) if dates.get('bug_fixing_ip') else 'Pending'}")
    if "total_bugs" in include_optional or "bugs_with_dev" in include_optional or "bugs_with_qa" in include_optional or "bugs_with_product" in include_optional or "closed_bugs" in include_optional:
        block.append("")
    if "total_bugs" in include_optional:
        block.append(f"*Total Bugs* – {total_bugs} (P0: {p0}, P1: {p1})")
    if "bugs_with_dev" in include_optional:
        block.append(f"*Bugs With Dev* – {with_dev}")
    if "bugs_with_qa" in include_optional:
        block.append(f"*Bugs With QA* – {with_qa}")
    if "bugs_with_product" in include_optional:
        block.append(f"*Bugs With Product (Approval/Discussion)* – {with_product}")
    if "closed_bugs" in include_optional:
        block.append(f"*Closed Bugs* – {closed_bugs}")
    if "challenges" in include_optional:
        block.append("")
        block.append(f"*Challenges* – {challenges}")
    if "environment_issue" in include_optional:
        block.append("")
        block.append(f"*Environment Issue* – {env_line}")
    if "internal_peds" in include_optional:
        block.append("")
        block.append(f"*Internal PEDS* – {internal_peds}")
    if "targetted_release_date" in include_optional or "uat_status" in include_optional or "preprod_status" in include_optional:
        block.append("")
    if "targetted_release_date" in include_optional:
        block.append(f"*Targetted Release Date* – {format_date(dates.get('target_release', ''))}")
    if "uat_status" in include_optional:
        block.append(f"*UAT Status* – {uat}")
    if "preprod_status" in include_optional:
        block.append(f"*Preprod Status* – {preprod}")
    return "\n".join(block)
