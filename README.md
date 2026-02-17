# QA Project Challenges Presentation

Generate a **project-specific challenges report** for QA presentations by pulling:

- **JIRA**: issue details, comments, and linked issues
- **Slack**: project channel context (from export or manual file)

## Quick start

1. **Install dependencies** (use a venv if your system says "externally managed" or `pip` not found)
   ```bash
   # Option A: virtual environment (recommended on macOS/Homebrew Python)
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

   # Option B: direct install
   pip install -r requirements.txt
   ```

2. **Configure**
   - Copy `config.example.env` to `.env`
   - Set your JIRA base URL, email, and API token ([Create API token](https://id.atlassian.com/manage-profile/security/api-tokens))
   - Optionally set path to Slack export or leave blank

3. **Run** (if using a venv, either `source .venv/bin/activate` first or use `.venv/bin/python` below)
   ```bash
   # All issues in a project (optional: limit with --limit)
   python fetch_challenges.py --project PROJ --output report.md

   # Specific issue keys (e.g. from a sprint or filter)
   python fetch_challenges.py --issues PROJ-101,PROJ-102,PROJ-103 --output report.md

   # Include Slack channel context (if SLACK_EXPORT_PATH is set or --slack path given)
   python fetch_challenges.py --project PROJ --slack ./slack_export --output report.md
   ```

4. Use `report.md` in your deck or convert to PDF/slides.

## Data sources

| Source | What it pulls | How |
|--------|----------------|-----|
| **JIRA** | Issue summary, status, description, **comments**, **linked issues** (blocks/blocked by, relates to, etc.) | JIRA REST API (project key or list of issue keys) |
| **Slack** | Messages from the project channel | **Slack API** (token + channel ID) or export/JSON file |

### Connect Slack from code (API) – recommended for QA challenges

To **fetch channel conversations in code** and use them to identify QA challenges:

1. **Create a Slack app** at [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. **Add Bot Token Scopes**: **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** → add **`channels:history`** (public channels) and/or **`groups:history`** (private channels).
3. **Install the app** to your workspace (**Install to Workspace**), then copy the **Bot User OAuth Token** (starts with `xoxb-`).
4. **Get the channel ID**: In Slack, right‑click the project/QA channel → **View channel details** → scroll to the bottom or open the link; the ID is in the URL or shown there (e.g. `C01234ABC`).
5. **Add to `.env`**:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-token
   SLACK_CHANNEL_ID=C01234ABC
   ```
6. Run the report (no `--slack` needed). The script will call the Slack API and load recent messages from that channel into the report and CSV **Slack channel summary** column.

If you get SSL errors (e.g. corporate proxy), add `SLACK_VERIFY_SSL=false` to `.env`.

### Slack export or JSON (alternative)

- **Export:** Slack **Settings & administration** → **Workspace settings** → **Import/Export Data** → **Export**; unzip and set `SLACK_EXPORT_PATH` (or `--slack path`).
- **Manual JSON:** Put messages into `slack_channel_messages.json` (see `slack_channel_messages.example.json`) and point `--slack` at the folder containing it.

## Output

The script produces a Markdown report with:

- **Project / scope** (project key and issue keys or “all project issues”)
- **Challenges from JIRA**: issues (with status), key comments, and linked issues
- **Challenges from Slack**: notable channel messages (e.g. blockers, questions)
- **Summary** for talking points

You can paste sections into slides or use a Markdown→PDF tool (e.g. Pandoc, Marp) for the presentation.

## Environment variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_BASE_URL` | Yes | e.g. `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | Yes | Email used for JIRA |
| `JIRA_API_TOKEN` | Yes | JIRA API token |
| `JIRA_VERIFY_SSL` | No | Set to `false` if you get SSL certificate errors (e.g. corporate proxy) |
| `OPENAI_API_KEY` | No | OpenAI API key to generate QA challenges summary with AI (CSV column). Use with `--ai`. |
| `OPENAI_QA_SUMMARY` | No | Set to `true` to enable AI summary by default (no need for `--ai` flag). |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`). |
| `OPENAI_VERIFY_SSL` | No | Set to `false` if you get SSL/connection errors (e.g. corporate proxy). |
| `OPENAI_HTTP_PROXY` | No | Proxy URL (e.g. `http://proxy.company:8080`) when behind a corporate proxy. |
| `GAMMA_API_KEY` | No | Gamma API key for `--gamma-publish` (create 10-slide PPT on gamma.app and get URL). Get it at gamma.app → Account → Developer/API. |
| `GAMMA_VERIFY_SSL` | No | Set to `false` if you get SSL certificate errors when calling Gamma API (e.g. corporate proxy). |
| `SLACK_BOT_TOKEN` | No | Slack Bot OAuth token (xoxb-...) to **fetch channel conversations via API**. Create app at [api.slack.com/apps](https://api.slack.com/apps), add scope `channels:history` (or `groups:history` for private), install to workspace. |
| `SLACK_CHANNEL_ID` | No | Slack **channel ID** (e.g. C01234ABC) to fetch. Right-click channel → View channel details → copy ID. Used with `SLACK_BOT_TOKEN`. |
| `SLACK_VERIFY_SSL` | No | Set to `false` if you get SSL errors when calling Slack API (e.g. corporate proxy). |
| `SLACK_EXPORT_PATH` | No | **Alternative to API:** path to Slack export folder or folder containing `slack_channel_messages.json`. |

### Fixing OpenAI API failure (Connection error)

If you see `AI API failed for CEPI-27: Connection error` and the **AI generated summary** column is empty:

1. **Corporate proxy / SSL**  
   Add to `.env`:
   ```env
   OPENAI_VERIFY_SSL=false
   ```
   If your network uses a proxy, also set:
   ```env
   OPENAI_HTTP_PROXY=http://your-proxy-host:port
   ```
   (Or `HTTPS_PROXY` / `HTTP_PROXY` in the environment.)

2. **Run outside restricted networks**  
   Run the script from your own terminal on a network that can reach `api.openai.com` (e.g. home Wi‑Fi or mobile hotspot if office blocks it).

3. **Check API key**  
   Ensure `OPENAI_API_KEY` in `.env` is correct and has no extra spaces. Create a new key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) if needed.

4. **Skip AI**  
   Run without `--ai`; the CSV will still have all other columns. The **AI generated summary** column will be empty.

## Options

- `--project PROJ` – JIRA project key; fetches recent issues (respects `--limit`).
- `--issues KEY1,KEY2` – Specific JIRA issue IDs; fetches those issues plus comments and linked issues.
- `--slack path` – Override Slack export/channel path.
- `--output report.md` – Output file (default: `qa_challenges_report.md`).
- `--limit N` – Max issues when using `--project` (default: 50).
- `--ai` – Use OpenAI to write the **QA challenges summary** in the CSV (needs `OPENAI_API_KEY` in `.env`).
- `--slides` – Use AI to generate **2 slides** plus a **10-slide Gamma outline** (`report_slides_gamma.md`). Needs `OPENAI_API_KEY`. See **GAMMA_INSTRUCTIONS.md**.
- `--gamma-publish` – Create the **10-slide deck on Gamma** and print the **shareable PPT URL**. Needs `GAMMA_API_KEY` in `.env`; run with `--slides` (e.g. `--slides --gamma-publish`). The URL is your Gamma presentation link.
