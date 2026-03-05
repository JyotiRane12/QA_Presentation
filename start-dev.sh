#!/usr/bin/env bash
# Start QA Reporting Tool dev server (Flask).
# Usage: ./start-dev.sh   or   bash start-dev.sh

set -e
cd "$(dirname "$0")"

# Use venv if present
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# Optional: set in .env or export before running
# FLASK_DEBUG=1  - enable debug mode
# PORT=5001      - server port (default 5001 to avoid macOS AirPlay on 5000)

PORT="${PORT:-5001}"
echo "Starting QA Reporting Tool dev server..."
echo "Open http://127.0.0.1:$PORT"
echo ""

exec flask --app app run --host 0.0.0.0 --port "$PORT"
