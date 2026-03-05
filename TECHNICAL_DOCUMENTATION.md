# QA Reporting Tool – Technical Documentation

## 1. Overview and Features

**QA Reporting Tool** is a web application for QA teams that:

- **QA Daily Report** – Generates a standardized QA update from JIRA (issue, linked bugs, dates) and Slack (today’s channel messages for “Challenges”), then posts it to Slack. Supports one-off run, preview, or scheduled runs (daily or every 3 min, Mon–Fri only). Reports can be posted directly to a channel or sent for review (ephemeral with Post / Edit & Post buttons).
- **Scheduler Logs** – View, pause, stop, resume, and edit scheduled QA daily report jobs. Shows per-job “posted to channel” success count and a total. Old completed/stopped jobs are pruned (retention: 2 months).
- **QA Project Challenges** – Generates a project challenges report (Markdown, CSV, optional slides and Gamma PPT) from JIRA issues and optional Slack channel context. Used for presentations and documentation.

All features are available via the **Web UI** (Flask + Tailwind). Key actions are also exposed as **REST APIs** for automation or integration.

---

## 2. Technologies Used

| Category        | Technology |
|----------------|------------|
| Backend        | **Python 3** |
| Web framework  | **Flask 3.x** |
| Scheduler      | **APScheduler 3.x** (background cron/date triggers) |
| HTTP client    | **requests** |
| Config         | **python-dotenv** (.env) |
| Optional AI    | **OpenAI** (challenges summary, slides) |
| Frontend       | **Tailwind CSS** (CDN), **Plus Jakarta Sans** |
| Database       | **SQLite 3** (see Section 3) |
| Testing        | **pytest** |

External integrations: **JIRA REST API**, **Slack API** (chat, channels history, interactivity).

---

## 3. Databases Used

| Database | File / Location | Purpose |
|----------|------------------|--------|
| **SQLite** | `data/qa_daily_report.db` | QA Daily Report: scheduler jobs (with `post_success_count`) and pending reports (review flow). |

- **Tables:** `scheduler_jobs`, `pending_reports`.
- **Cleanup:** On app startup, records older than **2 months** are deleted for **completed or stopped** scheduler jobs and for old pending reports. Active/paused jobs are never deleted by cleanup.
- No other databases are used; JIRA and Slack are accessed via their APIs only.

---

## 4. APIs and cURL Examples

Base URL: **`http://127.0.0.1:5000`** (default Flask port). Replace with your host/port if different. All JSON APIs use `Content-Type: application/json`.

---

### 4.1 Page routes (GET – browser or redirect)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Redirects to QA Project Challenges page. |
| GET | `/qa-daily-report` | QA Daily Report form page. |
| GET | `/qa-daily-report/scheduler-logs` | Scheduler logs page (list and manage scheduled jobs). |
| GET | `/qa-project-challenges` | QA Project Challenges form page. |

**Example (redirect):**
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/
# 302 → redirect to /qa-project-challenges
```

---

### 4.2 QA Project Challenges – Generate report

**POST** `/api/generate`

Generates the project challenges report (Markdown, optional CSV, slides, Gamma publish).

**Request body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue_keys` | string | Yes | Comma-separated JIRA issue keys (e.g. `CEPI-5451,CEPI-5452`). |
| `generate_slides` | boolean | No | Default `false`. Generate slides and Gamma outline. |
| `publish_to_gamma` | boolean | No | Default `false`. Publish to Gamma and return PPT URL. |
| `generate_csv` | boolean | No | Default `true`. Generate CSV. |
| `slack_channel_id` | string | No | Slack channel ID for channel context. |

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "issue_keys": "CEPI-5451,CEPI-5452",
    "generate_slides": false,
    "publish_to_gamma": false,
    "generate_csv": true,
    "slack_channel_id": "C0AFTQD06MP"
  }'
```

**Success (200):** `{"success": true, "run_id": "<uuid>", "log": "...", "gamma_url": null, "files": [{"name": "report", "path": "report.md"}, ...]}`  
**Error (4xx/5xx):** `{"success": false, "error": "..."}` optionally with `"log"`, `"run_id"`.

---

### 4.3 Download generated report file

**GET** `/api/reports/<run_id>/<filename>`

Download a file from a previous generate run. Allowed filenames: `report.md`, `report.csv`, `report_slides.md`, `report_slides_gamma.md`.

**Example:**
```bash
curl -O -J "http://127.0.0.1:5000/api/reports/abc12345/report.md"
```

---

### 4.4 QA Daily Report – Run or schedule

**POST** `/api/qa-daily-report`

Runs the QA daily report now (or only schedules it if start/end dates are provided).

**Request body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue_keys` | string | Yes | JIRA issue key(s), e.g. `CEPI-5344` or `CEPI-5344,CEPI-5345`. |
| `output_option` | string | No | `channel` \| `review` \| `preview`. Default `preview`. |
| `slack_channel_id` | string | Yes* | Slack channel ID. *Required for channel/review and for challenges. |
| `slack_user_id` | string | Yes if review | Required when `output_option` is `review`. |
| `report_output_keys` | array | No | Optional section keys to include (e.g. `["ready_for_qa_date","total_bugs"]`). |
| `schedule_start` | string | No | Start date (YYYY-MM-DD). If set with `schedule_end`, only schedules (no immediate run). |
| `schedule_end` | string | No | End date (YYYY-MM-DD). Required if `schedule_start` is set. |
| `frequency` | string | No | `daily` \| `3min`. Default `daily`. |

**Example (preview only):**
```bash
curl -X POST http://127.0.0.1:5000/api/qa-daily-report \
  -H "Content-Type: application/json" \
  -d '{
    "issue_keys": "CEPI-5344",
    "output_option": "preview",
    "slack_channel_id": "C0AFTQD06MP",
    "report_output_keys": ["ready_for_qa_date", "total_bugs", "challenges"]
  }'
```

**Example (schedule daily run Mon–Fri):**
```bash
curl -X POST http://127.0.0.1:5000/api/qa-daily-report \
  -H "Content-Type: application/json" \
  -d '{
    "issue_keys": "CEPI-5344",
    "output_option": "channel",
    "slack_channel_id": "C0AFTQD06MP",
    "schedule_start": "2026-03-10",
    "schedule_end": "2026-03-31",
    "frequency": "daily"
  }'
```

**Success (200):** `{"success": true, "posted_channel": false, "posted_review": false, "report": "...", "log": "..."}` or with `"scheduled": true, "message": "..."` when only scheduling.  
**Error (4xx/5xx):** `{"success": false, "error": "..."}`.

---

### 4.5 Scheduler logs – Pause job

**POST** `/api/scheduler-logs/pause`

Pauses a scheduled job (can be resumed later).

**Request body (JSON):** `{"id": "<job_id>"}`

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/scheduler-logs/pause \
  -H "Content-Type: application/json" \
  -d '{"id": "47d2c3a6-d541-4116-bc30-12e064af6be5"}'
```

**Response:** `{"success": true, "message": "Job paused."}` or `{"success": false, "error": "..."}`.

---

### 4.6 Scheduler logs – Stop job

**POST** `/api/scheduler-logs/stop`

Stops a job permanently (no more runs; cannot resume).

**Request body (JSON):** `{"id": "<job_id>"}`

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/scheduler-logs/stop \
  -H "Content-Type: application/json" \
  -d '{"id": "47d2c3a6-d541-4116-bc30-12e064af6be5"}'
```

---

### 4.7 Scheduler logs – Resume job

**POST** `/api/scheduler-logs/resume`

Resumes a paused job (only paused jobs can be resumed).

**Request body (JSON):** `{"id": "<job_id>"}`

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/scheduler-logs/resume \
  -H "Content-Type: application/json" \
  -d '{"id": "47d2c3a6-d541-4116-bc30-12e064af6be5"}'
```

---

### 4.8 Scheduler logs – Update job

**POST** `/api/scheduler-logs/update`

Updates a task: optional report sections, frequency, start/end date, time.

**Request body (JSON):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Job ID. |
| `report_output_keys` | array | No | Optional section keys. |
| `frequency` | string | No | `daily` \| `3min`. |
| `schedule_start` | string | No | Start date (YYYY-MM-DD). |
| `schedule_end` | string | No | End date (YYYY-MM-DD). |
| `schedule_time` | string | No | Time (e.g. HH:MM). |

**Example:**
```bash
curl -X POST http://127.0.0.1:5000/api/scheduler-logs/update \
  -H "Content-Type: application/json" \
  -d '{
    "id": "47d2c3a6-d541-4116-bc30-12e064af6be5",
    "report_output_keys": ["ready_for_qa_date", "total_bugs", "challenges"],
    "frequency": "daily"
  }'
```

**Response:** `{"success": true, "message": "Task updated."}` or error JSON.

---

### 4.9 Slack interactivity (QA Daily Report buttons)

**POST** `/api/slack-interaction`

Called by Slack when users click **Post** or **Edit & Post** on the QA Daily Report message, or submit the edit modal. Expects `application/x-www-form-urlencoded` with a `payload` field (JSON string). Not intended for manual cURL use; Slack sends this when interactivity is configured.

---

## 5. How to Use the Features (Instructions)

### 5.1 Setup

1. **Install dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**
   - Copy `config.example.env` to `.env`.
   - Set **JIRA**: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.
   - For **Slack** (QA Daily Report and Challenges): create a Slack app, add Bot scopes (`channels:history`, `chat:write`), install to workspace, set `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID` in `.env`.
   - Optional: `OPENAI_API_KEY` (challenges summary, slides), `GAMMA_API_KEY` (publish slides).

3. **Start the app**
   ```bash
   flask --app app run
   # Or: python app.py
   ```
   Open **http://127.0.0.1:5000**. Root redirects to QA Project Challenges.

---

### 5.2 QA Daily Report

1. Open **QA Daily Report** from the sidebar.
2. **Set up:** Enter **JIRA ID(s)** (e.g. `CEPI-5344`) and **Slack Channel ID** (required for challenges and posting).
3. **Schedule (optional):** Expand “Schedule Report”, set start/end dates and time. Leave empty to run once now. Frequency: Daily or Every 3 min (Mon–Fri only).
4. **Output options:** Choose **Post Report To Channel**, **Review Report and Post to Channel** (ephemeral with Post / Edit & Post), or **Generate Report To Preview** (no post). For Review, enter **Slack User ID**.
5. **Report output:** Optionally select which sections to include (Ready for QA Date, Total Bugs, Challenges, etc.).
6. Click **Generate QA Daily Report**. If scheduled, the job appears under **Scheduler Logs**; runs occur Mon–Fri only. Success count is shown per job and in the summary card.

**Scheduler Logs:** Use the table to Pause, Stop, Resume, or Edit jobs. “Posted” column shows how many times that job posted to the channel successfully.

---

### 5.3 QA Project Challenges

1. Open **QA Project Challenges** from the sidebar.
2. Enter **JIRA issue keys** (comma-separated). Optionally set **Slack Channel ID** for channel context.
3. Check **Generate CSV**, **Generate slides**, or **Publish to Gamma** as needed.
4. Click **Generate report**. When done, download **report**, **csv**, or **slides** from the links, or use the Gamma URL if published.

---

### 5.4 Database and cleanup

- **SQLite** file: `data/qa_daily_report.db`. Contains `scheduler_jobs` and `pending_reports`.
- **Cleanup** runs on every app startup: deletes **completed or stopped** scheduler jobs and **pending reports** older than **2 months**. Active and paused jobs are kept.
- Scheduled runs **do not run on Saturday or Sunday**; they are skipped.

---

## 6. Document info

- **Application:** QA Reporting Tool (Flask app + daily_qa_report + fetch_challenges).
- **Rules:** Bug counts and UAT/Preprod logic follow `Rules/BugCount.cursorrules`.
- **API base:** `http://127.0.0.1:5000` by default; override with `PORT` and host as needed.
