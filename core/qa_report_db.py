"""
SQLite persistence for QA Daily Report: scheduler jobs and pending reports.
Used by app.py and core/slack_client.py (and daily_qa_report subprocess).
"""
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# Delete records older than this (current date - RETENTION_MONTHS). Keeps DB clean.
RETENTION_MONTHS = 2

# Project root: parent of core/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "qa_daily_report.db"

# Legacy paths for one-time migration
SCHEDULER_JOBS_FILE = DATA_DIR / "scheduler_jobs.json"
PENDING_REPORTS_DIR = DATA_DIR / "pending_reports"


def _get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                id TEXT PRIMARY KEY,
                action_state TEXT,
                task_type TEXT,
                jira_id TEXT,
                scheduler_start_date TEXT,
                scheduler_end_date TEXT,
                scheduler_time TEXT,
                frequency TEXT,
                issue_keys TEXT,
                output_option TEXT,
                slack_channel_id TEXT,
                slack_user_id TEXT,
                report_output_keys TEXT,
                post_success_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_reports (
                id TEXT PRIMARY KEY,
                report TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    _migrate_add_post_success_count()


def _migrate_add_post_success_count() -> None:
    """Add post_success_count column if it does not exist."""
    conn = _get_conn()
    try:
        cursor = conn.execute("PRAGMA table_info(scheduler_jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        if "post_success_count" not in columns:
            conn.execute("ALTER TABLE scheduler_jobs ADD COLUMN post_success_count INTEGER DEFAULT 0")
            conn.commit()
    finally:
        conn.close()


def load_scheduler_jobs() -> list[dict]:
    """Load all scheduler job entries from the database."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM scheduler_jobs ORDER BY rowid").fetchall()
        jobs = []
        for row in rows:
            keys_json = row["report_output_keys"]
            report_output_keys = json.loads(keys_json) if keys_json else []
            post_count = 0
            try:
                post_count = int(row["post_success_count"]) if row["post_success_count"] is not None else 0
            except (KeyError, TypeError, ValueError):
                pass
            jobs.append({
                "id": row["id"],
                "action_state": row["action_state"] or "active",
                "task_type": row["task_type"] or "QA daily report",
                "jira_id": row["jira_id"],
                "scheduler_start_date": row["scheduler_start_date"],
                "scheduler_end_date": row["scheduler_end_date"],
                "scheduler_time": row["scheduler_time"],
                "frequency": row["frequency"],
                "issue_keys": row["issue_keys"],
                "output_option": row["output_option"],
                "slack_channel_id": row["slack_channel_id"],
                "slack_user_id": row["slack_user_id"],
                "report_output_keys": report_output_keys,
                "post_success_count": post_count,
            })
        return jobs
    finally:
        conn.close()


def save_scheduler_jobs(jobs: list[dict]) -> None:
    """Replace all scheduler jobs in the database with the given list."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM scheduler_jobs")
        for e in jobs:
            conn.execute(
                """INSERT INTO scheduler_jobs (
                    id, action_state, task_type, jira_id,
                    scheduler_start_date, scheduler_end_date, scheduler_time,
                    frequency, issue_keys, output_option,
                    slack_channel_id, slack_user_id, report_output_keys,
                    post_success_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.get("id") or "",
                    e.get("action_state"),
                    e.get("task_type"),
                    e.get("jira_id"),
                    e.get("scheduler_start_date"),
                    e.get("scheduler_end_date"),
                    e.get("scheduler_time"),
                    e.get("frequency"),
                    e.get("issue_keys"),
                    e.get("output_option"),
                    e.get("slack_channel_id"),
                    e.get("slack_user_id"),
                    json.dumps(e.get("report_output_keys") or []),
                    int(e.get("post_success_count") or 0),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def increment_post_success_count(log_id: str) -> None:
    """Increment the post_success_count for a scheduler job (when report posted to channel/review successfully)."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE scheduler_jobs SET post_success_count = COALESCE(post_success_count, 0) + 1 WHERE id = ?",
            (log_id,),
        )
        conn.commit()
    finally:
        conn.close()


def save_pending_report(report_id: str, report: str, channel_id: str) -> bool:
    """Store a pending report (for Review flow). Returns True on success."""
    from datetime import datetime, timezone
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO pending_reports (id, report, channel_id, created_at) VALUES (?, ?, ?, ?)",
            (report_id, report, channel_id, datetime.now(tz=timezone.utc).isoformat()),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_pending_report(report_id: str) -> dict | None:
    """Return pending report dict with 'report' and 'channel_id', or None."""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT report, channel_id FROM pending_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return {"report": row["report"], "channel_id": row["channel_id"]}
    finally:
        conn.close()


def delete_pending_report(report_id: str) -> None:
    """Remove a pending report by id."""
    init_db()
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM pending_reports WHERE id = ?", (report_id,))
        conn.commit()
    finally:
        conn.close()


def migrate_scheduler_jobs_from_json() -> bool:
    """
    If scheduler_jobs.json exists and DB has no jobs, load JSON and save to DB.
    Returns True if migration was performed.
    """
    if not SCHEDULER_JOBS_FILE.exists():
        return False
    existing = load_scheduler_jobs()
    if existing:
        return False
    try:
        data = json.loads(SCHEDULER_JOBS_FILE.read_text(encoding="utf-8"))
        jobs = data if isinstance(data, list) else []
        if jobs:
            save_scheduler_jobs(jobs)
            return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def migrate_pending_report_from_file(report_id: str) -> dict | None:
    """
    If a legacy pending report file exists, load it, insert into DB, delete file, return data.
    Returns None if no file or on error.
    """
    path = PENDING_REPORTS_DIR / f"{report_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        report = data.get("report") or ""
        channel_id = (data.get("channel_id") or "").strip()
        if report and channel_id:
            save_pending_report(report_id, report, channel_id)
        path.unlink(missing_ok=True)
        return {"report": report, "channel_id": channel_id}
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def clean_old_data(retention_months: int = RETENTION_MONTHS) -> tuple[int, int]:
    """
    Delete records older than (current date - retention_months).
    - scheduler_jobs: delete only completed or stopped jobs (never active/paused). Completed = end date in past.
    - pending_reports: delete where created_at is before cutoff.
    Returns (scheduler_jobs_deleted, pending_reports_deleted).
    """
    init_db()
    today = date.today()
    # Approximate: 1 month ~ 30 days
    cutoff = today - timedelta(days=retention_months * 30)
    cutoff_str = cutoff.isoformat()

    conn = _get_conn()
    try:
        # Delete only stopped jobs, or jobs that have ended (end date < today) and are older than cutoff
        today_str = today.isoformat()
        cursor = conn.execute(
            """SELECT id FROM scheduler_jobs WHERE
               (
                 action_state = 'stopped'
                 OR (scheduler_end_date IS NOT NULL AND TRIM(scheduler_end_date) != '' AND scheduler_end_date < ?)
               )
               AND COALESCE(NULLIF(TRIM(scheduler_end_date), ''), scheduler_start_date) < ?""",
            (today_str, cutoff_str),
        )
        old_job_ids = [row[0] for row in cursor.fetchall()]
        for jid in old_job_ids:
            conn.execute("DELETE FROM scheduler_jobs WHERE id = ?", (jid,))
        scheduler_deleted = len(old_job_ids)

        # Delete pending_reports where created_at date part is before cutoff (created_at is ISO with optional time)
        cursor = conn.execute("SELECT id, created_at FROM pending_reports")
        pending_deleted = 0
        for row in cursor.fetchall():
            created = row["created_at"]
            if not created:
                continue
            try:
                # created_at is ISO e.g. 2025-01-15T12:00:00+00:00 or 2025-01-15
                date_part = created.split("T")[0].strip()
                if len(date_part) >= 10 and date_part < cutoff_str:
                    conn.execute("DELETE FROM pending_reports WHERE id = ?", (row["id"],))
                    pending_deleted += 1
            except (ValueError, IndexError):
                pass

        conn.commit()
        return (scheduler_deleted, pending_deleted)
    finally:
        conn.close()
