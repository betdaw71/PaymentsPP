"""Подсказки с картинками для платёжной страницы (KZT)."""
from __future__ import annotations

from payments.payment_page_assets import kaspi_guide_public_url


def _action_ids(bank_actions: list[dict] | None) -> set[str]:
    return {(a.get("id") or "").lower() for a in (bank_actions or [])}


def build_bank_guides(
    *,
    currency: str,
    locale: str = "kk",
    bank_actions: list[dict] | None = None,
) -> list[dict[str, str]]:
    if (currency or "").upper() != "KZT":
        return []

    ids = _action_ids(bank_actions)
    has_kaspi = any(i == "kaspi" or i.startswith("kaspi_") for i in ids)
    has_halyk = "halyk" in ids

    if has_halyk and not has_kaspi:
        if locale == "kk":
            title = "Homebank-те шетел картасына аудару"
            caption = (
                "«Аударымдар» → «Барлық аударымдар» → «Шетел картасына». "
                "Реквизиттер көшірілген — карта мен соманы қойыңыз."
            )
        else:
            title = "Как перевести в Homebank"
            caption = (
                "Откройте «Переводы» → «Все переводы» → «На зарубежную карту». "
                "Реквизиты скопированы — вставьте карту и сумму."
            )
        return [
            {
                "id": "halyk_foreign",
                "image_url": "",
                "title": title,
                "caption": caption,
            }
        ]

    if bank_actions and not has_kaspi:
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
            "image_url": kaspi_guide_public_url(),
            "title": title,
            "caption": caption,
        }
    ]
