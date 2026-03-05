"""Unit tests for report generation logic. Mocks external dependencies."""

import pytest
from core.report_formatter import (
    bug_count_jql_queries,
    bug_counts,
    bug_keys,
    internal_peds_count,
    leds_info,
    format_date,
    uat_status,
    preprod_status,
    build_report,
    OPTIONAL_SECTION_KEYS,
)


# ----- bug_counts -----

def test_bug_counts_empty_linked():
    assert bug_counts([]) == (0, 0, 0, 0, 0, 0, 0)


def test_bug_counts_excludes_led():
    linked = [
        {"key": "LED-1", "issuetype": "Bug", "status": "Open", "project": "LEDS", "resolution": ""},
        {"key": "BUG-1", "issuetype": "Bug", "status": "Open", "project": "PROJ", "resolution": ""},
    ]
    total, with_dev, with_qa, with_product, closed, p0, p1 = bug_counts(linked)
    assert total == 1
    assert with_dev == 1


def test_bug_counts_excludes_cancelled_rejected():
    linked = [
        {"key": "BUG-1", "issuetype": "Bug", "status": "Cancelled", "project": "P", "resolution": ""},
        {"key": "BUG-2", "issuetype": "Bug", "status": "Rejected", "project": "P", "resolution": ""},
        {"key": "BUG-3", "issuetype": "Bug", "status": "Open", "project": "P", "resolution": ""},
    ]
    total, with_dev, with_qa, with_product, closed, p0, p1 = bug_counts(linked)
    assert total == 1
    assert with_dev == 1


def test_bug_counts_excludes_duplicate_not_a_bug():
    linked = [
        {"key": "BUG-1", "issuetype": "Bug", "status": "Closed", "project": "P", "resolution": "Duplicate", "priority": "P0"},
        {"key": "BUG-2", "issuetype": "Bug", "status": "Closed", "project": "P", "resolution": "Not a Bug", "priority": "P1"},
        {"key": "BUG-3", "issuetype": "Bug", "status": "Closed", "project": "P", "resolution": "Fixed", "priority": "P0"},
    ]
    total, _, _, _, closed, p0, p1 = bug_counts(linked)
    assert total == 1
    assert closed == 1
    assert p0 == 1
    assert p1 == 0


def test_bug_counts_with_dev_qa_closed():
    linked = [
        {"key": "B1", "issuetype": "Bug", "status": "Dev IP", "project": "P", "resolution": "", "priority": "P0"},
        {"key": "B2", "issuetype": "Bug", "status": "QA IP", "project": "P", "resolution": "", "priority": "P1"},
        {"key": "B3", "issuetype": "Bug", "status": "Released", "project": "P", "resolution": "Fixed", "priority": ""},
    ]
    total, with_dev, with_qa, with_product, closed, p0, p1 = bug_counts(linked)
    assert total == 3
    assert with_dev == 1
    assert with_qa == 1
    assert with_product == 0
    assert closed == 1
    assert p0 == 1
    assert p1 == 1


def test_bug_counts_with_product():
    linked = [
        {"key": "B1", "issuetype": "Bug", "status": "Ready for UAT", "project": "P", "resolution": ""},
        {"key": "B2", "issuetype": "Bug", "status": "Product UAT IP", "project": "P", "resolution": ""},
        {"key": "B3", "issuetype": "Bug", "status": "QA IP", "project": "P", "resolution": ""},
    ]
    total, with_dev, with_qa, with_product, closed, p0, p1 = bug_counts(linked)
    assert total == 3
    assert with_product == 2


# ----- bug_count_jql_queries -----

def test_bug_count_jql_queries():
    q = bug_count_jql_queries("SMT-51974")
    assert "linkedIssues(\"SMT-51974\")" in q["total_bugs"]
    assert "issuetype = Bug" in q["total_bugs"]
    assert "Not a Bug" in q["total_bugs"] and "Duplicate" in q["total_bugs"]
    assert "Released" in q["closed_bugs"] or "Closed" in q["closed_bugs"]
    assert "P0" in q["p0"]
    assert "P1" in q["p1"]


# ----- bug_keys -----

def test_bug_keys_returns_keys_only():
    linked = [
        {"key": "BUG-1", "issuetype": "Bug", "resolution": ""},
        {"key": "BUG-2", "issuetype": "Bug", "resolution": "Duplicate"},
    ]
    assert bug_keys(linked) == ["BUG-1"]


# ----- internal_peds_count -----

def test_internal_peds_count():
    linked = [
        {"key": "P1", "issuetype": "PEDS Internal"},
        {"key": "P2", "issuetype": "Internal PEDS"},
        {"key": "B1", "issuetype": "Bug"},
    ]
    assert internal_peds_count(linked) == 2


# ----- leds_info -----

def test_leds_info_counts_open():
    linked = [
        {"key": "LED-1", "project": "LEDS", "status": "Open", "summary": "LED summary"},
        {"key": "LED-2", "project": "LEDS", "status": "Closed"},
    ]
    count, open_leds = leds_info(linked)
    assert count == 2
    assert len(open_leds) == 1
    assert open_leds[0]["key"] == "LED-1"
    assert open_leds[0]["summary"] == "LED summary"


# ----- format_date -----

def test_format_date_valid():
    assert format_date("2026-02-18") == "18th Feb 2026"
    assert format_date("2026-02-01") == "1st Feb 2026"
    assert format_date("2026-02-02") == "2nd Feb 2026"
    assert format_date("2026-02-03") == "3rd Feb 2026"


def test_format_date_empty():
    assert format_date("") == "N/A"


def test_format_date_invalid():
    assert format_date("invalid") == "invalid"[:10] or "N/A"


# ----- uat_status, preprod_status -----

def test_uat_status_pending():
    for status_name in ("Open", "QA IP"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert uat_status(issue) == "Pending", f"Expected Pending for {status_name}"


def test_uat_status_in_uat():
    for status_name in ("Ready for UAT", "UAT In Progress", "Product UAT IP"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert uat_status(issue) == "In-UAT", f"Expected In-UAT for {status_name}"


def test_preprod_status_pending():
    for status_name in ("Open", "QA IP", "Development IP"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert preprod_status(issue) == "Pending", f"Expected Pending for {status_name}"


def test_preprod_status_in_progress():
    for status_name in ("Ready for SIT", "SIT In Progress", "Ready For Release", "Ready for RP"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert preprod_status(issue) == "In-progress", f"Expected In-progress for {status_name}"


def test_uat_status_completed_when_preprod_in_progress():
    """When Preprod is In-progress (incl. Ready for RP), UAT status should be Completed (BugCount.cursorrules Section 8)."""
    for status_name in ("Ready for SIT", "SIT In Progress", "Ready For Release", "Ready for RP"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert uat_status(issue) == "Completed", f"Expected Completed for {status_name}"


def test_uat_preprod_completed_when_deployed():
    """When status is Released, Beta Deployed, or Deployment Completed, both UAT and Preprod = Completed."""
    for status_name in ("Released", "Beta Deployed", "Deployment Completed", "Closed"):
        issue = {"fields": {"status": {"name": status_name}}}
        assert uat_status(issue) == "Completed", f"UAT Expected Completed for {status_name}"
        assert preprod_status(issue) == "Completed", f"Preprod Expected Completed for {status_name}"


# ----- build_report -----

def test_build_report_mandatory_only():
    issue = {"fields": {"summary": "Test Title"}}
    linked = []
    dates = {"ready_for_qa": "", "qa_start": "", "bug_fixing_ip": "", "target_release": ""}
    report = build_report(
        "PROJ-1", issue, linked, dates,
        challenges="", led_count=0, open_leds=[],
        today_str="18th Feb 2026", include_optional=set()
    )
    assert "*QA Update*" in report
    assert "*JIRA ID* – PROJ-1" in report
    assert "*JIRA Title* – Test Title" in report


def test_build_report_with_optional():
    issue = {"fields": {"summary": "Test", "status": {"name": "Open"}}}
    linked = [
        {"key": "B1", "issuetype": "Bug", "status": "Dev IP", "project": "P", "resolution": "", "priority": "P0"},
    ]
    dates = {"ready_for_qa": "2026-02-01", "qa_start": "", "bug_fixing_ip": "", "target_release": ""}
    report = build_report(
        "PROJ-1", issue, linked, dates,
        challenges="No blockers", led_count=0, open_leds=[],
        today_str="18th Feb 2026",
        include_optional={"total_bugs", "challenges"}
    )
    assert "*Total Bugs* – 1 (P0: 1, P1: 0)" in report
    assert "*Challenges* – No blockers" in report


def test_optional_section_keys():
    assert "total_bugs" in OPTIONAL_SECTION_KEYS
    assert "challenges" in OPTIONAL_SECTION_KEYS
    assert "environment_issue" in OPTIONAL_SECTION_KEYS
    assert "internal_peds" in OPTIONAL_SECTION_KEYS


def test_build_report_environment_issue_per_bugcount_rules():
    """Environment Issue follows BugCount.cursorrules Section 9."""
    issue = {"fields": {"summary": "Test"}}
    linked = []
    dates = {"ready_for_qa": "", "qa_start": "", "bug_fixing_ip": "", "target_release": ""}
    # A) Total LED = 0
    report = build_report(
        "PROJ-1", issue, linked, dates,
        challenges="", led_count=0, open_leds=[],
        today_str="Today", include_optional={"environment_issue"}
    )
    assert "*Environment Issue* – 0" in report
    assert "No LED tickets linked to JIRA" in report
    # B) Total LED > 0, Open LEDs
    open_leds = [{"key": "LED-1", "summary": "LED summary", "assignee": "John Doe"}]
    report = build_report(
        "PROJ-1", issue, linked, dates,
        challenges="", led_count=2, open_leds=open_leds,
        today_str="Today", include_optional={"environment_issue"}
    )
    assert "*Environment Issue* – 2" in report
    assert "1 LED(s) in Open status" in report
    assert "LED-1 – LED summary" in report
    assert "Assignee: John Doe" in report
    # C) Total LED > 0, Open LED = 0
    report = build_report(
        "PROJ-1", issue, linked, dates,
        challenges="", led_count=2, open_leds=[],
        today_str="Today", include_optional={"environment_issue"}
    )
    assert "*Environment Issue* – 2" in report
    assert "No LED tickets are currently in Open status" in report
    # Internal PEDS
    linked_peds = [{"key": "PEDS-1", "issuetype": "PEDS Internal"}]
    report = build_report(
        "PROJ-1", issue, linked_peds, dates,
        challenges="", led_count=0, open_leds=[],
        today_str="Today", include_optional={"internal_peds"}
    )
    assert "*Internal PEDS* – 1" in report
