"""Подсказки с картинками для платёжной страницы (KZT)."""
from __future__ import annotations

from django.conf import settings

KASPI_GUIDE_STATIC_PATH = "/static/payment_page/kaspi-international-transfers-guide.png"


def kaspi_guide_image_url() -> str:
    base = (getattr(settings, "PUBLIC_API_URL", None) or "").rstrip("/")
    if base:
        return f"{base}{KASPI_GUIDE_STATIC_PATH}"
    return KASPI_GUIDE_STATIC_PATH


def build_bank_guides(
    *,
    currency: str,
    locale: str = "kk",
    bank_actions: list[dict] | None = None,
) -> list[dict[str, str]]:
    if (currency or "").upper() != "KZT":
        return []

    actions = bank_actions or []
    has_kaspi = any(
        (a.get("id") or "").lower() == "kaspi"
        or "kaspi" in (a.get("label") or "").lower()
        for a in actions
    )
    if actions and not has_kaspi:
        return []

    if locale == "kk":
        title = "Kaspi-де аудару"
        caption = (
            "«Аударымдар» бөліміне өтіп, «Халықаралық аударымдар» тармағын таңдаңыз, "
            "содан кейін алушы реквизиттерін енгізіңіз."
        )
    else:
        title = "Как перевести в Kaspi"
        caption = (
            "Откройте раздел «Переводы» и выберите «Международные переводы», "
            "затем введите реквизиты получателя."
        )

    return [
        {
            "id": "kaspi_international",
            "image_url": kaspi_guide_image_url(),
            "title": title,
            "caption": caption,
        }
    ]
