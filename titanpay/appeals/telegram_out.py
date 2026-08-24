from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings


@dataclass
class SendResult:
    ok: bool
    message_id: int | None = None
    error: str = ""


def _bot_token() -> str:
    return getattr(settings, "APPEAL_TELEGRAM_BOT_TOKEN", "") or ""


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
    lower_name = (filename or "").lower()
    is_image = lower_name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"))

    if is_image:
        url = f"{base}/sendPhoto"
        files = {"photo": (filename or "receipt.jpg", file_bytes)}
    else:
        url = f"{base}/sendDocument"
        files = {"document": (filename or "receipt", file_bytes)}

    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption

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
