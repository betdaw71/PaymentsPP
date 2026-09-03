from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from django.conf import settings

from appeals.provider_privacy import provider_safe_caption, provider_safe_filename

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    message_id: int | None = None
    error: str = ""


def _bot_token() -> str:
    return getattr(settings, "APPEAL_TELEGRAM_BOT_TOKEN", "") or ""


def _api_post(method: str, payload: dict) -> dict:
    token = _bot_token()
    if not token:
        return {"ok": False, "description": "APPEAL_TELEGRAM_BOT_TOKEN не задан"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, json=payload, timeout=30)
    try:
        return response.json()
    except ValueError:
        return {"ok": False, "description": response.text[:300]}


def send_receipt_to_provider_chat(
    *,
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    caption: str,
) -> SendResult:
    token = _bot_token()
    if not token:
        return SendResult(ok=False, error="APPEAL_TELEGRAM_BOT_TOKEN не задан")

    base = f"https://api.telegram.org/bot{token}"
    safe_name = provider_safe_filename(filename, file_bytes)
    safe_caption = provider_safe_caption(caption, fallback="appeal")
    lower_name = safe_name.lower()
    is_image = lower_name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"))

    if is_image:
        url = f"{base}/sendPhoto"
        files = {"photo": (safe_name, file_bytes)}
    else:
        url = f"{base}/sendDocument"
        files = {"document": (safe_name, file_bytes)}

    data = {"chat_id": str(chat_id)}
    if safe_caption:
        data["caption"] = safe_caption

    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        payload = response.json()
    except requests.RequestException as exc:
        return SendResult(ok=False, error=str(exc))

    if not payload.get("ok"):
        description = payload.get("description") or response.text
        return SendResult(ok=False, error=description)

    message_id = payload.get("result", {}).get("message_id")
    return SendResult(ok=True, message_id=message_id)


def send_text_to_provider_chat(
    *,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
) -> SendResult:
    caption = provider_safe_caption(text, fallback="appeal")
    payload = {"chat_id": chat_id, "text": caption}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    result = _api_post("sendMessage", payload)
    if not result.get("ok"):
        return SendResult(ok=False, error=result.get("description") or "sendMessage failed")
    message_id = (result.get("result") or {}).get("message_id")
    return SendResult(ok=True, message_id=message_id)


def notify_merchant_appeal_message(
    *,
    chat_id: int | None,
    message_id: int | None,
    approved: bool,
) -> bool:
    if not chat_id or not message_id:
        logger.warning(
            "appeal notify skipped: missing chat_id=%s message_id=%s",
            chat_id,
            message_id,
        )
        return False

    emoji = "👍" if approved else "👎"
    text = "Успех" if approved else "Отклонена"

    reaction_result = _api_post(
        "setMessageReaction",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
            "is_big": approved,
        },
    )
    if not reaction_result.get("ok"):
        logger.warning(
            "appeal setMessageReaction failed chat_id=%s message_id=%s: %s",
            chat_id,
            message_id,
            reaction_result.get("description") or reaction_result,
        )

    message_result = _api_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": message_id,
        },
    )
    if not message_result.get("ok"):
        logger.error(
            "appeal sendMessage failed chat_id=%s message_id=%s: %s",
            chat_id,
            message_id,
            message_result.get("description") or message_result,
        )
        return False

    return True
