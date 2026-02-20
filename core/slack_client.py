"""Slack API client. Retries failed messages 3 times. All credentials from environment."""

import json
import logging
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
SLACK_VERIFY_SSL = (os.getenv("SLACK_VERIFY_SSL", "true").lower() not in ("0", "false", "no"))

SLACK_RETRY_COUNT = 3
SLACK_TIMEOUT = 30


def _headers() -> dict:
    """Auth headers. Token from env only."""
    return {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}


def _post_with_retry(url: str, payload: dict) -> bool:
    """Post to Slack with 3 retries. Returns True on success."""
    last_error = None
    for attempt in range(1, SLACK_RETRY_COUNT + 1):
        try:
            r = requests.post(
                url,
                json=payload,
                headers=_headers(),
                timeout=SLACK_TIMEOUT,
                verify=SLACK_VERIFY_SSL,
            )
            data = r.json()
            if data.get("ok"):
                return True
            err = data.get("error", "unknown")
            last_error = err
            logger.warning("Slack API error (attempt %d/%d): %s", attempt, SLACK_RETRY_COUNT, err)
            if err == "channel_not_found":
                logger.info(
                    "Channel not found. Get ID: Slack → right-click channel → View channel details."
                )
        except requests.RequestException as e:
            last_error = e
            logger.warning("Slack request failed (attempt %d/%d): %s", attempt, SLACK_RETRY_COUNT, e)
    logger.error("Slack post failed after %d retries: %s", SLACK_RETRY_COUNT, last_error)
    return False


def post_message(channel_id: str, text: str, user_id: str | None = None) -> bool:
    """Post message to channel. Ephemeral if user_id given. Retries 3 times."""
    if not SLACK_BOT_TOKEN or not channel_id:
        logger.warning("Slack post skipped: missing token or channel_id")
        return False
    url = "https://slack.com/api/chat.postEphemeral" if user_id else "https://slack.com/api/chat.postMessage"
    payload = {"channel": channel_id, "text": _format_bullets(text)}
    if user_id:
        payload["user"] = user_id
    return _post_with_retry(url, payload)


def _format_bullets(text: str) -> str:
    """Ensure Slack message uses bullet points where appropriate."""
    if not text or "*" in text[:50]:  # Already has markdown
        return text
    lines = text.strip().split("\n")
    if len(lines) <= 1:
        return text
    formatted = []
    for line in lines:
        line = line.strip()
        if not line:
            formatted.append("")
        elif not line.startswith(("•", "-", "*")):
            formatted.append(f"• {line}")
        else:
            formatted.append(line)
    return "\n".join(formatted)


def post_ephemeral_with_buttons(
    channel_id: str, user_id: str, report_text: str, pending_dir: Path
) -> bool:
    """Post ephemeral with Post/Edit buttons. Retries 3 times."""
    if not SLACK_BOT_TOKEN or not channel_id or not user_id:
        return False
    report_id = str(uuid.uuid4())
    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_file = pending_dir / f"{report_id}.json"
    try:
        pending_file.write_text(
            json.dumps({"report": report_text, "channel_id": channel_id}), encoding="utf-8"
        )
    except OSError as e:
        logger.exception("Failed to save pending report: %s", e)
        return False
    preview = report_text[:2500] + ("..." if len(report_text) > 2500 else "")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": preview}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Click *Post* to share with everyone, or *Edit & Post* to edit before sharing.",
            },
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Post"}, "action_id": "post_report_to_channel", "value": report_id},
                {"type": "button", "text": {"type": "plain_text", "text": "Edit & Post"}, "action_id": "review_and_post_report", "value": report_id},
            ],
        },
    ]
    payload = {
        "channel": channel_id,
        "user": user_id,
        "text": (report_text[:500] + "..." if len(report_text) > 500 else report_text),
        "blocks": blocks,
    }
    ok = _post_with_retry("https://slack.com/api/chat.postEphemeral", payload)
    if not ok:
        pending_file.unlink(missing_ok=True)
    return ok


def open_dm_channel(user_id: str) -> str:
    """Open DM with user. Returns channel ID or empty string."""
    if not SLACK_BOT_TOKEN or not user_id:
        return ""
    try:
        r = requests.post(
            "https://slack.com/api/conversations.open",
            json={"users": user_id},
            headers=_headers(),
            timeout=SLACK_TIMEOUT,
            verify=SLACK_VERIFY_SSL,
        )
        data = r.json()
        if not data.get("ok"):
            return ""
        ch = data.get("channel") or {}
        return (ch.get("id") or "").strip()
    except requests.RequestException as e:
        logger.warning("Failed to open DM channel: %s", e)
        return ""


def fetch_channel_messages(channel_id: str, limit: int = 500) -> list[dict]:
    """Fetch channel messages. Returns empty list on failure."""
    if not SLACK_BOT_TOKEN or not channel_id:
        return []
    url = "https://slack.com/api/conversations.history"
    messages = []
    cursor = None
    try:
        while len(messages) < limit:
            params = {"channel": channel_id, "limit": min(200, limit - len(messages))}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(
                url,
                params=params,
                headers=_headers(),
                timeout=SLACK_TIMEOUT,
                verify=SLACK_VERIFY_SSL,
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ok"):
                break
            for msg in data.get("messages") or []:
                if msg.get("type") != "message" or msg.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
                    continue
                text = (msg.get("text") or "").strip()
                if text:
                    messages.append({"ts": msg.get("ts", ""), "user": msg.get("user", ""), "text": text})
            if not data.get("has_more"):
                break
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
    except requests.RequestException as e:
        logger.warning("Failed to fetch Slack messages: %s", e)
    return messages
