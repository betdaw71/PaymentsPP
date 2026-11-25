"""Shared ticket / receipt heuristics for the Bot API bot and the userbot."""

from __future__ import annotations

import re

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# Mostbet CX<>Avapay_Op: "uuid / 1179… / 498… / 724… VIP"
CX_SLASH_LINE_RE = re.compile(
    r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?:\s*[\\/|]+\s*\d+){1,}(?:\s+VIP)?\b",
    re.IGNORECASE,
)
FOLLOWUP_CHATTER_RE = re.compile(
    r"новост|скорректир|удалось|какое решение|дайте ответ|приоритет|ознаком|"
    r"any\s*news|any\s*update|does\s+the\s+receipt|colleagues\??|"
    r"неверный\s+реквизит|не\s+наш\s+реквизит|"
    r"update\s*\?|news\s*\?|статус\s*\?|есть\s+ответ",
    re.IGNORECASE,
)
TICKET_HINT_RE = re.compile(
    r"(тикет\s*[#№n]?\s*[:：]?\s*[0-9a-fA-F]{8}|заказ\s*[:：]|id\s*заказа|номер заказа|"
    r"реквизиты из заявки|маска юзера|номер в [пг]?пс|order\s*id\s*[:：]|"
    r"id\s*сделки|id\s+заявки\s+провайдера|чек\s+по\s+сделке|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|"
    r"[0-9a-fA-F]{9}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}g\b|"
    r"\b[0-9a-fA-F]{32}\b|\b\d{8,}\b)",
    re.IGNORECASE,
)
RECEIPT_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".mp4", ".mov", ".webm")
TICKET_NAME_HINTS = ("melbet", "мелбет", "ticket", "тикет", "avapay")


def looks_like_ticket(text: str) -> bool:
    if not text:
        return False
    if UUID_RE.search(text):
        return True
    return bool(TICKET_HINT_RE.search(text))


def is_followup_chatter(text: str) -> bool:
    """Уточнение по уже открытой апелляции (any news?), не новая заявка с чеком."""
    return bool(FOLLOWUP_CHATTER_RE.search(text or ""))


def extract_uuids(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in UUID_RE.findall(text):
        key = match.lower()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def extract_cx_slash_uuids(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in CX_SLASH_LINE_RE.finditer(text):
        key = match.group("uuid").lower()
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def filename_looks_like_ticket(name: str | None) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in TICKET_NAME_HINTS)


def is_pdf_document(mime: str | None, name: str | None) -> bool:
    mime_l = (mime or "").lower()
    name_l = (name or "").lower()
    if mime_l in ("application/pdf", "application/x-pdf"):
        return True
    if name_l.endswith(".pdf"):
        return True
    if mime_l in ("application/octet-stream", "binary/octet-stream", "") and name_l.endswith(".pdf"):
        return True
    return False


def is_receipt_document(mime: str | None, name: str | None) -> bool:
    mime_l = (mime or "").lower()
    name_l = (name or "").lower()
    if mime_l.startswith("image/") or mime_l.startswith("video/") or mime_l in ("application/pdf", "application/x-pdf"):
        return True
    if mime_l in ("application/octet-stream", "binary/octet-stream", ""):
        return name_l.endswith(RECEIPT_EXTS)
    return name_l.endswith(RECEIPT_EXTS)


def looks_like_ticket_document(mime: str | None, name: str | None, caption: str | None) -> bool:
    """True only for merchant *ticket* files (Melbet etc.), not bank receipts.

    Important: a PDF/photo whose caption contains an order UUID is a normal appeal
    (Pandapay/Melbet ops), NOT a ticket attachment. Treating UUID captions as
    tickets dropped the receipt and made appeals fail with «ID не распознан».
    """
    return filename_looks_like_ticket(name)


def attachment_is_ticket_file(mime: str | None, name: str | None, caption: str | None) -> bool:
    """Whether this attachment is the merchant ticket rather than the payment receipt.

    Mel Transaction Bot sends one message: ticket text in the caption and a PDF
    whose name is a content hash. The caption looks like a ticket, but the file
    is the receipt. Only a ticket-like filename moves the bytes out of the receipt.
    """
    return looks_like_ticket_document(mime, name, caption)


def generic_receipt_name(filename: str | None, content: bytes) -> str:
    if content.startswith(b"\xff\xd8\xff"):
        return "receipt.jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "receipt.png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "receipt.webp"
    if content.startswith(b"%PDF"):
        return "receipt.pdf"
    if content.startswith(b"GIF8"):
        return "receipt.gif"
    name = (filename or "").lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".heic", ".heif", ".mp4", ".mov", ".webm"):
        if name.endswith(ext):
            if ext in {".jpeg", ".heic", ".heif"}:
                return "receipt.jpg"
            return f"receipt{ext}"
    return "receipt.bin"


def inline_button_action(text: str) -> str | None:
    """Map Mel Transaction Bot button labels to approve/reject. Extra-info buttons are ignored."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return None
    if "доп" in lowered or "информац" in lowered:
        return None
    if "подтверд" in lowered:
        return "approve"
    if "отклон" in lowered:
        return "reject"
    return None


def should_watch_sender(
    *,
    is_self: bool,
    is_bot: bool,
    username: str,
    allowed_usernames: set[str],
    allow_humans: bool = False,
) -> bool:
    """Who to ingest from.

    - allowlist set → only those usernames
    - else bots always; humans only if allow_humans (Mostbet CX / CSSUP* agents)
    """
    if is_self:
        return False
    uname = (username or "").lstrip("@").lower()
    if allowed_usernames:
        return uname in allowed_usernames
    if is_bot:
        return True
    return allow_humans


def parse_int_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def parse_usernames(raw: str) -> set[str]:
    out: set[str] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip().lstrip("@").lower()
        if part:
            out.add(part)
    return out


def env_flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}
