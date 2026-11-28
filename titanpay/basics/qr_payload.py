"""Нормализация qr_payload живого трейдера → поля платёжной страницы."""
from __future__ import annotations

from base64 import b64encode
from io import BytesIO


def _make_qr_data_uri(content: str) -> str:
    import qrcode

    img = qrcode.make(content)
    stream = BytesIO()
    img.save(stream, format="PNG")
    return "data:image/png;base64," + b64encode(stream.getvalue()).decode("ascii")


def _looks_like_image_url(url: str) -> bool:
    lower = url.lower().split("?", 1)[0]
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
        return True
    # Фото из ЛК: /media/pd_qr/<trader>/<uuid>.jpg
    return "/media/pd_qr/" in lower or "/pd_qr/" in lower


def payment_page_fields_from_qr_payload(payload: str | None) -> dict:
    """
    Из строки трейдера:
      - data:image/... → qr_image_url как есть
      - http(s) фото QR (в т.ч. media/pd_qr) → qr_image_url
      - http(s) иное / ELQR 000201… / любой текст → рисуем QR (data URI)
    """
    raw = (payload or "").strip()
    if not raw:
        return {}
    if raw.startswith("data:image/"):
        return {"qr_image_url": raw}
    if raw.startswith("http://") or raw.startswith("https://"):
        if _looks_like_image_url(raw):
            return {"qr_image_url": raw}
        # Ссылка на виджет/оплату: и картинка QR со ссылкой, и URL на всякий случай.
        return {
            "qr_image_url": _make_qr_data_uri(raw),
            "payment_form_url": raw,
        }
    return {"qr_image_url": _make_qr_data_uri(raw)}
