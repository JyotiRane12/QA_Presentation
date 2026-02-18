"""
Web UI for QA report and PPT generation.
Run: flask --app app run (or python app.py)
"""
import os
import re
import subprocess
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

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


def run_qa_daily_report(
    issue_keys: str,
    output_option: str,
    slack_channel_id: str | None = None,
    slack_user_id: str | None = None,
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

    try:
        returncode, report, log = run_qa_daily_report(
            issue_keys=issue_keys,
            output_option=output_option,
            slack_channel_id=slack_channel_id,
            slack_user_id=slack_user_id,
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
