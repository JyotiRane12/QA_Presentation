"""
Web UI for QA report and PPT generation.
Run: flask --app app run (or python app.py)
"""
import json
import os
import re
import subprocess
import uuid
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

_qa_scheduler = BackgroundScheduler()
_qa_scheduler.start()

# Persisted scheduler jobs (survives restarts). File path and in-memory list.
SCHEDULER_JOBS_FILE = PROJECT_ROOT / "data" / "scheduler_jobs.json"
_scheduler_logs: list[dict] = []

# Report output key -> display label (for Scheduler Logs and edit form)
REPORT_OUTPUT_LABELS = {
    "ready_for_qa_date": "Ready For QA Date",
    "qa_start_date": "QA Start Date",
    "one_round_of_testing_completion": "One Round Of Testing Completion",
    "total_bugs": "Total Bugs",
    "bugs_with_dev": "Bugs With Dev",
    "bugs_with_qa": "Bugs With QA",
    "closed_bugs": "Closed Bugs",
    "challenges": "Challenges",
    "environment_issue": "Environment Issue",
    "targetted_release_date": "Targetted Release Date",
    "uat_status": "UAT Status",
    "preprod_status": "Preprod Status",
}


def _load_scheduler_jobs() -> list[dict]:
    """Load scheduler log entries from disk. Returns [] if file missing or invalid."""
    if not SCHEDULER_JOBS_FILE.exists():
        return []
    try:
        with open(SCHEDULER_JOBS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_scheduler_jobs(jobs: list[dict]) -> None:
    """Persist scheduler log entries to disk."""
    SCHEDULER_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULER_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)


def _job_kwargs_for_entry(entry: dict) -> dict:
    """Build job kwargs for an entry, including _log_id for pause/stop/resume."""
    log_id = entry.get("id") or str(uuid.uuid4())
    return {
        "issue_keys": entry.get("issue_keys") or entry.get("jira_id") or "",
        "output_option": entry.get("output_option") or "preview",
        "slack_channel_id": entry.get("slack_channel_id") or None,
        "slack_user_id": entry.get("slack_user_id") or None,
        "report_output_keys": entry.get("report_output_keys") or [],
        "_log_id": log_id,
    }


def _add_job_for_entry(entry: dict) -> bool:
    """Register a single entry with the scheduler (for new jobs or resume). Returns True if added."""
    start_date = entry.get("scheduler_start_date") or ""
    end_date = entry.get("scheduler_end_date") or ""
    time_str = entry.get("scheduler_time") or "00:00"
    if not start_date:
        return False
    try:
        first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}:00")
    except ValueError:
        first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}")
    now = datetime.now()
    today = now.date()
    if end_date:
        end_d = date.fromisoformat(end_date)
        if today > end_d:
            return False
    else:
        if now >= first_run_dt:
            return False
    job_kwargs = _job_kwargs_for_entry(entry)
    if end_date:
        end_d = date.fromisoformat(end_date)
        end_dt = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59)
        _qa_scheduler.add_job(
            _run_scheduled_qa_daily_report,
            trigger=CronTrigger(
                hour=first_run_dt.hour,
                minute=first_run_dt.minute,
                second=first_run_dt.second,
                start_date=first_run_dt,
                end_date=end_dt,
            ),
            kwargs=job_kwargs,
            id=f"qa_daily_{first_run_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
            replace_existing=False,
        )
    else:
        _qa_scheduler.add_job(
            _run_scheduled_qa_daily_report,
            trigger=DateTrigger(run_date=first_run_dt),
            kwargs=job_kwargs,
            id=f"qa_daily_once_{first_run_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
            replace_existing=False,
        )
    return True


def _remove_job_by_log_id(log_id: str) -> bool:
    """Remove scheduler job(s) that match the given log id. Returns True if any removed."""
    removed = False
    for job in _qa_scheduler.get_jobs():
        if (getattr(job, "kwargs") or {}).get("_log_id") == log_id:
            try:
                _qa_scheduler.remove_job(job.id)
                removed = True
            except Exception:
                pass
    return removed


def _register_scheduler_jobs() -> None:
    """Load persisted jobs and re-register active ones with the scheduler (call after startup)."""
    global _scheduler_logs
    _scheduler_logs = _load_scheduler_jobs()
    modified = False
    for e in _scheduler_logs:
        if not e.get("id"):
            e["id"] = str(uuid.uuid4())
            modified = True
        if "action_state" not in e:
            e["action_state"] = "active"
            modified = True
    if modified:
        _save_scheduler_jobs(_scheduler_logs)
    now = datetime.now()
    today = now.date()
    for entry in _scheduler_logs:
        if entry.get("action_state") not in (None, "active"):
            continue
        if not entry.get("id"):
            entry["id"] = str(uuid.uuid4())
        start_date = entry.get("scheduler_start_date") or ""
        end_date = entry.get("scheduler_end_date") or ""
        time_str = entry.get("scheduler_time") or "00:00"
        if not start_date:
            continue
        try:
            first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}:00")
        except ValueError:
            first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}")
        if end_date:
            end_d = date.fromisoformat(end_date)
            if today > end_d:
                continue
        else:
            if now >= first_run_dt:
                continue
        job_kwargs = _job_kwargs_for_entry(entry)
        if end_date:
            end_d = date.fromisoformat(end_date)
            end_dt = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59)
            _qa_scheduler.add_job(
                _run_scheduled_qa_daily_report,
                trigger=CronTrigger(
                    hour=first_run_dt.hour,
                    minute=first_run_dt.minute,
                    second=first_run_dt.second,
                    start_date=first_run_dt,
                    end_date=end_dt,
                ),
                kwargs=job_kwargs,
                id=f"qa_daily_{first_run_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
                replace_existing=False,
            )
        else:
            _qa_scheduler.add_job(
                _run_scheduled_qa_daily_report,
                trigger=DateTrigger(run_date=first_run_dt),
                kwargs=job_kwargs,
                id=f"qa_daily_once_{first_run_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
                replace_existing=False,
            )


# Match "Gamma PPT URL (share this): https://..."
GAMMA_URL_RE = re.compile(r"Gamma PPT URL \(share this\):\s*(\S+)")


def run_report(
    issue_keys: str,
    output_base: str,
    generate_slides: bool,
    publish_to_gamma: bool,
    generate_csv: bool = True,
    slack_channel_id: str | None = None,
) -> tuple[int, str, str | None]:
    """Run fetch_challenges.py; return (returncode, combined_stdout_stderr, gamma_url)."""
    cmd = [
        os.environ.get("PYTHON", "python"),
        str(PROJECT_ROOT / "fetch_challenges.py"),
        "--issues", issue_keys.strip(),
        "--output", output_base + ".md",
    ]
    if not generate_csv:
        cmd.append("--no-csv")
    if generate_slides:
        cmd.append("--slides")
    if publish_to_gamma:
        cmd.append("--gamma-publish")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if slack_channel_id is not None and slack_channel_id.strip():
        env["SLACK_CHANNEL_ID"] = slack_channel_id.strip()
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    gamma_url = None
    for line in out.splitlines():
        m = GAMMA_URL_RE.search(line)
        if m:
            gamma_url = m.group(1).strip()
            break
    return proc.returncode, out, gamma_url


@app.route("/")
def index():
    return redirect(url_for("qa_project_challenges"))


@app.route("/qa-daily-report")
def qa_daily_report():
    return render_template("qa_daily_report.html", active_page="qa_daily_report")


def _time_24_to_12(time_24: str) -> str:
    """Convert 'HH:mm' or 'HH:mm:ss' to 'h:mm AM/PM'."""
    if not time_24 or not time_24.strip():
        return ""
    parts = time_24.strip().split(":")
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    if h == 0:
        return f"12:{m:02d} AM"
    if h < 12:
        return f"{h}:{m:02d} AM"
    if h == 12:
        return f"12:{m:02d} PM"
    return f"{h - 12}:{m:02d} PM"


def _scheduler_log_status(log: dict) -> str:
    """Compute status: Paused/Stopped from action_state, else Scheduled/Running/Completed from dates."""
    if log.get("action_state") == "paused":
        return "Paused"
    if log.get("action_state") == "stopped":
        return "Stopped"
    start_date = log.get("scheduler_start_date") or ""
    end_date = log.get("scheduler_end_date") or ""
    time_str = log.get("scheduler_time") or "00:00"
    if not start_date:
        return "Scheduled"
    try:
        first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}:00")
    except ValueError:
        first_run_dt = datetime.fromisoformat(f"{start_date}T{time_str}")
    now = datetime.now()
    today = now.date()
    if end_date:
        end_d = date.fromisoformat(end_date)
        if today > end_d:
            return "Completed"
        if now < first_run_dt:
            return "Scheduled"
        return "Running"
    if now < first_run_dt:
        return "Scheduled"
    return "Completed"


@app.route("/qa-daily-report/scheduler-logs")
def scheduler_logs():
    logs_with_status = []
    for log in _scheduler_logs:
        log_copy = dict(log)
        log_copy["status"] = _scheduler_log_status(log)
        keys = log_copy.get("report_output_keys") or []
        log_copy["report_output_labels"] = ", ".join(
            REPORT_OUTPUT_LABELS.get(k, k) for k in keys if k
        ) or "None"
        log_copy["scheduler_time_12hr"] = _time_24_to_12(log_copy.get("scheduler_time") or "")
        logs_with_status.append(log_copy)
    return render_template(
        "scheduler_logs.html",
        active_page="scheduler_logs",
        logs=logs_with_status,
        report_output_options=list(REPORT_OUTPUT_LABELS.items()),
    )


def _find_log_entry(log_id: str) -> dict | None:
    """Return the first log entry with the given id."""
    for e in _scheduler_logs:
        if e.get("id") == log_id:
            return e
    return None


@app.route("/api/scheduler-logs/pause", methods=["POST"])
def api_scheduler_logs_pause():
    """Pause a scheduled job immediately; no upcoming reports. Can be resumed later."""
    data = request.get_json() or {}
    log_id = (data.get("id") or "").strip()
    if not log_id:
        return jsonify({"success": False, "error": "Missing job id."}), 400
    entry = _find_log_entry(log_id)
    if not entry:
        return jsonify({"success": False, "error": "Job not found."}), 404
    _remove_job_by_log_id(log_id)
    entry["action_state"] = "paused"
    _save_scheduler_jobs(_scheduler_logs)
    return jsonify({"success": True, "message": "Job paused."})


@app.route("/api/scheduler-logs/stop", methods=["POST"])
def api_scheduler_logs_stop():
    """Stop a job permanently; no upcoming reports. Cannot be resumed."""
    data = request.get_json() or {}
    log_id = (data.get("id") or "").strip()
    if not log_id:
        return jsonify({"success": False, "error": "Missing job id."}), 400
    entry = _find_log_entry(log_id)
    if not entry:
        return jsonify({"success": False, "error": "Job not found."}), 404
    _remove_job_by_log_id(log_id)
    entry["action_state"] = "stopped"
    _save_scheduler_jobs(_scheduler_logs)
    return jsonify({"success": True, "message": "Job stopped."})


@app.route("/api/scheduler-logs/resume", methods=["POST"])
def api_scheduler_logs_resume():
    """Resume a paused job. Only paused jobs can be resumed."""
    data = request.get_json() or {}
    log_id = (data.get("id") or "").strip()
    if not log_id:
        return jsonify({"success": False, "error": "Missing job id."}), 400
    entry = _find_log_entry(log_id)
    if not entry:
        return jsonify({"success": False, "error": "Job not found."}), 404
    if entry.get("action_state") != "paused":
        return jsonify({"success": False, "error": "Only paused jobs can be resumed."}), 400
    if not _add_job_for_entry(entry):
        return jsonify({"success": False, "error": "Job window has passed; cannot resume."}), 400
    entry["action_state"] = "active"
    _save_scheduler_jobs(_scheduler_logs)
    return jsonify({"success": True, "message": "Job resumed."})


@app.route("/api/scheduler-logs/update", methods=["POST"])
def api_scheduler_logs_update():
    """Update a task: report output selection and/or timing."""
    data = request.get_json() or {}
    log_id = (data.get("id") or "").strip()
    if not log_id:
        return jsonify({"success": False, "error": "Missing job id."}), 400
    entry = _find_log_entry(log_id)
    if not entry:
        return jsonify({"success": False, "error": "Job not found."}), 404

    report_output_keys = data.get("report_output_keys")
    if isinstance(report_output_keys, list):
        entry["report_output_keys"] = [k for k in report_output_keys if k]

    schedule_start = (data.get("schedule_start") or "").strip() or None
    schedule_end = (data.get("schedule_end") or "").strip() or None
    if schedule_start:
        try:
            start_dt = datetime.fromisoformat(schedule_start.replace("Z", "+00:00"))
            entry["scheduler_start_date"] = start_dt.date().isoformat()
            entry["scheduler_time"] = start_dt.strftime("%H:%M")
        except ValueError:
            return jsonify({"success": False, "error": "Invalid schedule start date/time."}), 400
    if schedule_end:
        try:
            end_dt = datetime.fromisoformat(schedule_end.replace("Z", "+00:00"))
            entry["scheduler_end_date"] = end_dt.date().isoformat()
        except ValueError:
            return jsonify({"success": False, "error": "Invalid schedule end date/time."}), 400

    action_state = entry.get("action_state", "active")
    if action_state == "active":
        _remove_job_by_log_id(log_id)
        if not _add_job_for_entry(entry):
            pass  # window passed; entry still updated
    elif action_state == "paused":
        pass  # just update entry; when resumed will use new params

    _save_scheduler_jobs(_scheduler_logs)
    return jsonify({"success": True, "message": "Task updated."})


@app.route("/qa-project-challenges")
def qa_project_challenges():
    return render_template("qa_project_challenges.html", active_page="qa_project_challenges")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json() or {}
    issue_keys = (data.get("issue_keys") or "").strip()
    if not issue_keys:
        return jsonify({"success": False, "error": "Issue keys are required (e.g. CEPI-5451,CEPI-5452)"}), 400

    generate_slides = data.get("generate_slides", False)
    publish_to_gamma = data.get("publish_to_gamma", False)
    generate_csv = data.get("generate_csv", True)
    slack_channel_id = (data.get("slack_channel_id") or "").strip() or None

    run_id = str(uuid.uuid4())[:8]
    run_dir = REPORTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_base = str(run_dir / "report")

    try:
        returncode, log, gamma_url = run_report(
            issue_keys=issue_keys,
            output_base=output_base,
            generate_slides=generate_slides,
            publish_to_gamma=publish_to_gamma,
            generate_csv=generate_csv,
            slack_channel_id=slack_channel_id,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Report generation timed out (5 min)."}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    if returncode != 0:
        return jsonify({
            "success": False,
            "error": "Script exited with an error.",
            "log": log,
            "run_id": run_id,
        }), 422

    # Build list of generated files
    files = []
    for name, path in [
        ("report", run_dir / "report.md"),
        ("csv", run_dir / "report.csv"),
        ("slides", run_dir / "report_slides.md"),
        ("gamma_outline", run_dir / "report_slides_gamma.md"),
    ]:
        if path.exists():
            files.append({"name": name, "path": path.name})

    return jsonify({
        "success": True,
        "run_id": run_id,
        "log": log,
        "gamma_url": gamma_url,
        "files": files,
    })


def _run_scheduled_qa_daily_report(
    issue_keys: str,
    output_option: str,
    slack_channel_id: str | None,
    slack_user_id: str | None,
    report_output_keys: list[str] | None,
    **_kwargs: object,
) -> None:
    """Run the QA daily report (used by scheduler). Logs result; no return to caller. _kwargs absorbs _log_id etc."""
    try:
        returncode, report, log = run_qa_daily_report(
            issue_keys=issue_keys,
            output_option=output_option,
            slack_channel_id=slack_channel_id,
            slack_user_id=slack_user_id,
            report_output_keys=report_output_keys or [],
        )
        if returncode != 0:
            print(f"[QA Daily Report scheduled run] non-zero exit {returncode}: {log[:500]}")
        else:
            print(f"[QA Daily Report scheduled run] completed successfully.")
    except Exception as e:
        print(f"[QA Daily Report scheduled run] error: {e}")


_register_scheduler_jobs()


def run_qa_daily_report(
    issue_keys: str,
    output_option: str,
    slack_channel_id: str | None = None,
    slack_user_id: str | None = None,
    report_output_keys: list[str] | None = None,
) -> tuple[int, str, str]:
    """Run daily_qa_report.py. output_option: 'channel' | 'review' | 'preview'. Returns (returncode, report_text, log)."""
    cmd = [
        os.environ.get("PYTHON", "python"),
        str(PROJECT_ROOT / "daily_qa_report.py"),
        "--issues", issue_keys.strip(),
    ]
    if output_option == "preview":
        cmd.append("--dry-run")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if report_output_keys is not None:
        env["REPORT_OUTPUT_KEYS"] = ",".join(k.strip() for k in report_output_keys if k and k.strip())
    if output_option == "channel":
        if slack_channel_id and slack_channel_id.strip():
            env["SLACK_CHANNEL_ID"] = slack_channel_id.strip()
        env.pop("SLACK_REVIEW_CHANNEL_ID", None)
        env.pop("SLACK_REVIEW_USER_ID", None)
    elif output_option == "review":
        if slack_user_id and slack_user_id.strip():
            env["SLACK_REVIEW_USER_ID"] = slack_user_id.strip()
        env.pop("SLACK_CHANNEL_ID", None)
        env.pop("SLACK_REVIEW_CHANNEL_ID", None)
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    report = ""
    stdout = proc.stdout or ""
    if "*QA Update*" in stdout:
        report = stdout[stdout.find("*QA Update*"):].strip()
    return proc.returncode, report, log


@app.route("/api/qa-daily-report", methods=["POST"])
def api_qa_daily_report():
    data = request.get_json() or {}
    issue_keys = (data.get("issue_keys") or "").strip()
    if not issue_keys:
        return jsonify({"success": False, "error": "JIRA Id is required (e.g. CEPI-5344)"}), 400
    output_option = (data.get("output_option") or "preview").strip().lower()
    if output_option not in ("channel", "review", "preview"):
        output_option = "preview"
    slack_channel_id = (data.get("slack_channel_id") or "").strip() or None
    slack_user_id = (data.get("slack_user_id") or "").strip() or None

    if not slack_channel_id:
        return jsonify({
            "success": False,
            "error": "Slack Channel ID is required to read conversations and create Challenges.",
        }), 400

    if output_option == "review" and not slack_user_id:
        return jsonify({
            "success": False,
            "error": "Slack User ID is required to send the report to review.",
        }), 400

    report_output_keys = data.get("report_output_keys")
    if not isinstance(report_output_keys, list):
        report_output_keys = []

    schedule_start = (data.get("schedule_start") or "").strip() or None
    schedule_end = (data.get("schedule_end") or "").strip() or None
    frequency = (data.get("frequency") or "daily").strip().lower() or "daily"

    # If a schedule is set, run only at that date/time (or daily until end); do not run now.
    if schedule_start:
        try:
            start_dt = datetime.fromisoformat(schedule_start.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"success": False, "error": "Invalid schedule start date/time."}), 400
        end_dt = None
        if schedule_end:
            try:
                end_dt = datetime.fromisoformat(schedule_end.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"success": False, "error": "Invalid schedule end date/time."}), 400
            if end_dt < start_dt:
                return jsonify({"success": False, "error": "Schedule end must be after start."}), 400

        if frequency == "daily" and end_dt:
            entry = {
                "id": str(uuid.uuid4()),
                "action_state": "active",
                "task_type": "QA daily report",
                "jira_id": issue_keys,
                "scheduler_start_date": start_dt.date().isoformat(),
                "scheduler_end_date": end_dt.date().isoformat(),
                "scheduler_time": start_dt.strftime("%H:%M"),
                "issue_keys": issue_keys,
                "output_option": output_option,
                "slack_channel_id": slack_channel_id,
                "slack_user_id": slack_user_id,
                "report_output_keys": report_output_keys,
            }
            job_kwargs = _job_kwargs_for_entry(entry)
            _qa_scheduler.add_job(
                _run_scheduled_qa_daily_report,
                trigger=CronTrigger(
                    hour=start_dt.hour,
                    minute=start_dt.minute,
                    second=start_dt.second,
                    start_date=start_dt,
                    end_date=end_dt,
                ),
                kwargs=job_kwargs,
                id=f"qa_daily_{start_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
                replace_existing=False,
            )
            _scheduler_logs.append(entry)
            _save_scheduler_jobs(_scheduler_logs)
            msg = f"Report scheduled daily at {start_dt.strftime('%H:%M')} from {start_dt.date()} to {end_dt.date()}."
        else:
            entry = {
                "id": str(uuid.uuid4()),
                "action_state": "active",
                "task_type": "QA daily report",
                "jira_id": issue_keys,
                "scheduler_start_date": start_dt.date().isoformat(),
                "scheduler_end_date": "",
                "scheduler_time": start_dt.strftime("%H:%M"),
                "issue_keys": issue_keys,
                "output_option": output_option,
                "slack_channel_id": slack_channel_id,
                "slack_user_id": slack_user_id,
                "report_output_keys": report_output_keys,
            }
            job_kwargs = _job_kwargs_for_entry(entry)
            _qa_scheduler.add_job(
                _run_scheduled_qa_daily_report,
                trigger=DateTrigger(run_date=start_dt),
                kwargs=job_kwargs,
                id=f"qa_daily_once_{start_dt.isoformat()}_{uuid.uuid4().hex[:8]}",
                replace_existing=False,
            )
            _scheduler_logs.append(entry)
            _save_scheduler_jobs(_scheduler_logs)
            msg = f"Report scheduled for {start_dt.strftime('%Y-%m-%d %H:%M')}."
        return jsonify({
            "success": True,
            "scheduled": True,
            "message": msg,
            "report": "",
            "log": "",
        })

    try:
        returncode, report, log = run_qa_daily_report(
            issue_keys=issue_keys,
            output_option=output_option,
            slack_channel_id=slack_channel_id,
            slack_user_id=slack_user_id,
            report_output_keys=report_output_keys,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "QA Daily Report timed out (2 min).", "log": ""}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "log": ""}), 500

    if returncode != 0:
        # Prefer a clear error line from the script (e.g. "JIRA ID not found or incorrect: ...")
        error_msg = "Script exited with an error."
        for line in (log or "").splitlines():
            line = line.strip()
            if line.startswith("JIRA ID not found or incorrect:"):
                error_msg = line
                break
            if "Slack Channel ID is incorrect or empty" in line:
                error_msg = "Slack Channel ID is incorrect or empty. Report was not posted."
                break
            if "Slack Channel ID not found or incorrect" in line:
                error_msg = "Slack Channel ID not found or incorrect. Report was not posted."
                break
            if "Slack User ID is incorrect or empty" in line:
                error_msg = "Slack User ID is incorrect or empty. Report was not sent."
                break
            if "Slack User ID not found or incorrect" in line:
                error_msg = "Slack User ID not found or incorrect. Report was not sent."
                break
            if "SystemExit:" in line or "Error:" in line:
                # Fallback: use first substantive error-like line
                clean = line.replace("SystemExit:", "").strip()
                if clean and len(clean) < 200:
                    error_msg = clean
                    break
        return jsonify({
            "success": False,
            "error": error_msg,
            "log": log,
            "report": report,
        }), 422

    posted_channel = output_option == "channel" and "Report posted to Slack" in log
    posted_review = output_option == "review" and ("Report sent to user" in log or "Report posted to Slack" in log or "Report posted to channel" in log)
    return jsonify({
        "success": True,
        "posted_channel": posted_channel,
        "posted_review": posted_review,
        "report": report,
        "log": log,
    })


@app.route("/api/reports/<run_id>/<filename>")
def download_report(run_id: str, filename: str):
    """Download a generated file. Filename must be report.md, report.csv, etc."""
    allowed = {"report.md", "report.csv", "report_slides.md", "report_slides_gamma.md"}
    if filename not in allowed:
        return jsonify({"error": "Invalid file"}), 404
    path = REPORTS_DIR / run_id / filename
    if not path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=os.getenv("FLASK_DEBUG", "0") == "1", port=int(os.getenv("PORT", "5000")))
