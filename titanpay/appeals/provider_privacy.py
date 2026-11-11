"""Nothing sent to a PSP chat may identify the merchant (name, brand, ticket)."""

from __future__ import annotations

import logging
import os
import re
import zlib

logger = logging.getLogger(__name__)

MERCHANT_BRAND_RE = re.compile(
    r"melbet|мелбет|avapay|авапей|авапэй|titanpay|титанпэй|taserpay",
    re.IGNORECASE,
)

TICKET_FILENAME_RE = re.compile(
    r"melbet|мелбет|ticket|тикет|avapay|авапей",
    re.IGNORECASE,
)

_TICKET_HEX_RE = re.compile(r"тикет\s*[#№n]?\s*[:：]?\s*[0-9a-f]{8}", re.IGNORECASE)
_ORDER_LABEL_RE = re.compile(r"(заказ|order(?:\s*id)?)\s*[:：]", re.IGNORECASE)


def extract_pdf_text(data: bytes) -> str:
    if not data or not data.startswith(b"%PDF"):
        return ""
    text = _extract_pdf_fitz(data)
    if text.strip():
        return text
    return _extract_pdf_zlib(data)


def _extract_pdf_fitz(data: bytes) -> str:
    try:
        import fitz
    except Exception:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        logger.debug("fitz could not open pdf", exc_info=True)
        return ""
    try:
        parts = [page.get_text() or "" for page in doc]
        return "\n".join(parts).strip()
    except Exception:
        logger.debug("fitz text extract failed", exc_info=True)
        return ""
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _extract_pdf_zlib(data: bytes) -> str:
    """Best-effort plaintext from compressed PDF streams (no extra deps)."""
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        blob = match.group(1)
        decoded = blob
        try:
            decoded = zlib.decompress(blob)
        except zlib.error:
            try:
                decoded = zlib.decompress(blob.strip(b"\r\n"))
            except zlib.error:
                decoded = blob
        chunks.append(_strings_from_pdf_bytes(decoded))
    chunks.append(_strings_from_pdf_bytes(data))
    return "\n".join(part for part in chunks if part).strip()


def _strings_from_pdf_bytes(data: bytes) -> str:
    texts: list[str] = []
    for match in re.finditer(rb"\((?:\\.|[^\\)]){2,400}\)", data):
        raw = match.group(0)[1:-1]
        raw = raw.replace(br"\n", b"\n").replace(br"\r", b"\n").replace(br"\t", b"\t")
        raw = re.sub(br"\\(\d{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), raw)
        raw = raw.replace(br"\(", b"(").replace(br"\)", b")").replace(br"\\", b"\\")
        for encoding in ("utf-8", "latin-1"):
            try:
                texts.append(raw.decode(encoding))
                break
            except UnicodeDecodeError:
                continue
    for match in re.finditer(rb"(?:<feff|<FEFF)([0-9a-fA-F]{4,400})>", data):
        hexdata = match.group(1)
        try:
            texts.append(bytes.fromhex(hexdata.decode("ascii")).decode("utf-16-be", errors="ignore"))
        except ValueError:
            continue
    return "\n".join(texts)


def text_looks_like_merchant_ticket(text: str) -> bool:
    low = (text or "").lower()
    if not low.strip():
        return False
    if MERCHANT_BRAND_RE.search(low):
        return True
    score = 0
    if _TICKET_HEX_RE.search(low):
        score += 2
    if _ORDER_LABEL_RE.search(low):
        score += 1
    if "реквизиты из заявки" in low:
        score += 2
    if "маска юзера" in low:
        score += 2
    if "номер в пс" in low or "номер в гпс" in low:
        score += 1
    return score >= 2


def filename_looks_like_merchant_ticket(filename: str | None) -> bool:
    name = os.path.basename(filename or "")
    return bool(name and TICKET_FILENAME_RE.search(name))


def is_merchant_ticket_file(*, filename: str | None, file_bytes: bytes) -> bool:
    """True when this attachment is a merchant ticket, not a bank receipt."""
    data = file_bytes or b""
    name = (filename or "").lower()
    is_pdf = data.startswith(b"%PDF") or name.endswith(".pdf")
    if is_pdf and filename_looks_like_merchant_ticket(filename):
        return True
    if data.startswith(b"%PDF"):
        return text_looks_like_merchant_ticket(extract_pdf_text(data))
    return False


def provider_safe_filename(filename: str | None, file_bytes: bytes = b"") -> str:
    data = file_bytes or b""
    if data.startswith(b"\xff\xd8\xff"):
        return "receipt.jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "receipt.png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "receipt.webp"
    if data.startswith(b"%PDF"):
        return "receipt.pdf"
    if data.startswith(b"GIF8"):
        return "receipt.gif"
    ext = os.path.splitext(os.path.basename(filename or ""))[1].lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".heic", ".heif"}
    if ext in allowed:
        if ext in {".jpeg", ".jpg"}:
            return "receipt.jpg"
        if ext in {".heic", ".heif"}:
            return "receipt.jpg"
        return f"receipt{ext}"
    return "receipt.bin"


def _merchant_names(pay_in) -> list[str]:
    names: list[str] = []
    merchant = getattr(pay_in, "merchant", None)
    if merchant is None:
        return names
    user = getattr(merchant, "user", None)
    username = getattr(user, "username", None) or ""
    if username.strip():
        names.append(username.strip())
    return names


def caption_leaks_merchant(caption: str, *, pay_in=None) -> bool:
    text = caption or ""
    if not text.strip():
        return False
    if MERCHANT_BRAND_RE.search(text):
        return True
    if text_looks_like_merchant_ticket(text):
        return True
    for name in _merchant_names(pay_in):
        if len(name) < 3:
            continue
        if re.search(rf"(?i)(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text):
            return True
    return False


def provider_safe_caption(caption: str, *, fallback: str, pay_in=None) -> str:
    text = (caption or "").strip()
    safe_fallback = (fallback or "").strip() or "appeal"
    if not text:
        return safe_fallback
    if caption_leaks_merchant(text, pay_in=pay_in):
        logger.warning("stripped merchant identity from provider caption")
        return safe_fallback
    if caption_leaks_merchant(safe_fallback, pay_in=pay_in):
        return str(getattr(getattr(pay_in, "id", ""), "") or "appeal")
    return text
