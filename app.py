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
from flask import Flask, jsonify, render_template, request, send_file

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
    return render_template("index.html")


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
