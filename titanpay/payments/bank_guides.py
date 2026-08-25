"""Подсказки с картинками для платёжной страницы (KZT)."""
from __future__ import annotations

KASPI_GUIDE_IMAGE = "/static/payment_page/kaspi-international-transfers-guide.png"


def build_bank_guides(
    *,
    currency: str,
    locale: str = "kk",
) -> list[dict[str, str]]:
    if (currency or "").upper() != "KZT":
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
            "image_url": KASPI_GUIDE_IMAGE,
            "title": title,
            "caption": caption,
        }
    ]
