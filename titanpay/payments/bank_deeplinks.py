"""Deep links / app open helpers for payment page (KZT C2C)."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode

KASPI_ANDROID_PACKAGE = "kz.kaspi.mobile"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _norm_bank(bank: str) -> str:
    return (bank or "").strip().lower()


def _format_amount(amount: str | Decimal) -> str:
    if isinstance(amount, Decimal):
        text = format(amount.normalize(), "f")
        return text.rstrip("0").rstrip(".") or "0"
    return str(amount)


def _is_kaspi_recipient_bank(bank: str) -> bool:
    b = _norm_bank(bank)
    return "kaspi" in b and "halyk" not in b


def _android_intent_https(path: str, query: str) -> str:
    https_url = f"https://kaspi.kz{path}?{query}" if query else f"https://kaspi.kz{path}"
    host_path = f"kaspi.kz{path}"
    if query:
        host_path = f"{host_path}?{query}"
    return (
        f"intent://{host_path}#Intent;"
        f"scheme=https;package={KASPI_ANDROID_PACKAGE};"
        f"S.browser_fallback_url={quote(https_url, safe='')};end"
    )


def _android_intent_custom(scheme: str, host_path: str, query: str) -> str:
    target = f"{host_path}?{query}" if query else host_path
    return (
        f"intent://{target}#Intent;"
        f"scheme={scheme};package={KASPI_ANDROID_PACKAGE};end"
    )


def build_kaspi_deeplink_candidates(
    *,
    card: str = "",
    phone: str = "",
    amount: str | Decimal = "",
    owner: str = "",
    external_bank: bool = True,
) -> list[dict[str, str]]:
    """
    Best-effort набор Kaspi deeplink для prefill перевода.
    Порядок: primary https → custom scheme → android intent.
    """
    card = _digits(card)
    phone = _digits(phone)
    amt = _format_amount(amount)
    owner = (owner or "").strip()

    if not card and not phone:
        return []

    param_sets: list[dict[str, str]] = []
    if card:
        param_sets.extend(
            [
                {"card": card, "amount": amt},
                {"cardNumber": card, "amount": amt},
                {"pan": card, "sum": amt},
                {"toCard": card, "amount": amt},
                {"destinationCard": card, "amount": amt},
            ]
        )
        if owner:
            param_sets.append({"card": card, "amount": amt, "name": owner, "recipientName": owner})
    elif phone:
        param_sets.extend(
            [
                {"phone": phone, "amount": amt},
                {"phoneNumber": phone, "amount": amt},
            ]
        )
        if owner:
            param_sets.append({"phone": phone, "amount": amt, "name": owner})

    https_paths = (
        [
            "/kz/transfers/card_to_card",
            "/kz/transfers/external_card",
            "/transfers/card_to_card",
            "/ru/transfers/card_to_card",
        ]
        if external_bank
        else [
            "/kz/transfers/client",
            "/kz/transfers/to_client",
            "/transfers/client",
            "/ru/transfers/client",
        ]
    )

    custom_schemes = (
        [
            ("kaspi", "transfers/card_to_card"),
            ("kaspi", "transfer/card"),
            ("kaspi", "pay/transfer"),
            ("kaspikz", "transfers/card_to_card"),
        ]
        if external_bank
        else [
            ("kaspi", "transfers/client"),
            ("kaspi", "transfer/client"),
            ("kaspikz", "transfers/client"),
        ]
    )

    candidates: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str, kind: str, priority: int):
        if not url or url in seen:
            return
        seen.add(url)
        candidates.append({"label": label, "url": url, "type": kind, "priority": str(priority)})

    primary_params = param_sets[0]
    primary_query = urlencode(primary_params)

    for idx, path in enumerate(https_paths):
        query = urlencode(param_sets[min(idx, len(param_sets) - 1)])
        add(
            f"HTTPS {path}",
            f"https://kaspi.kz{path}?{query}",
            "https",
            10 + idx,
        )

    for idx, (scheme, host_path) in enumerate(custom_schemes):
        query = urlencode(param_sets[min(idx, len(param_sets) - 1)])
        add(
            f"{scheme}://{host_path}",
            f"{scheme}://{host_path}?{query}",
            "custom",
            30 + idx,
        )

    add(
        "Android Intent (HTTPS card_to_card)",
        _android_intent_https(https_paths[0], primary_query),
        "intent",
        50,
    )

    for idx, (scheme, host_path) in enumerate(custom_schemes[:2]):
        query = urlencode(param_sets[min(idx, len(param_sets) - 1)])
        add(
            f"Android Intent ({scheme})",
            _android_intent_custom(scheme, host_path, query),
            "intent",
            51 + idx,
        )

    candidates.sort(key=lambda item: int(item["priority"]))
    return candidates


def _fallback_kaspi_https(external_bank: bool) -> str:
    path = "/kz/transfers/card_to_card" if external_bank else "/kz/transfers/client"
    return f"https://kaspi.kz{path}"


def get_kaspi_primary_deeplink(
    *,
    card: str = "",
    phone: str = "",
    amount: str | Decimal = "",
    owner: str = "",
    external_bank: bool = True,
) -> str:
    """iOS Universal Link / Android App Link: https://kaspi.kz/.../transfers/..."""
    candidates = build_kaspi_deeplink_candidates(
        card=card,
        phone=phone,
        amount=amount,
        owner=owner,
        external_bank=external_bank,
    )
    for item in candidates:
        url = str(item.get("url") or "")
        if url.startswith("https://kaspi.kz/") and "/transfers/" in url:
            return url
    for item in candidates:
        url = str(item.get("url") or "")
        if url.startswith("https://"):
            return url
    return _fallback_kaspi_https(external_bank)


def get_kaspi_android_intent(
    *,
    card: str = "",
    phone: str = "",
    amount: str | Decimal = "",
    owner: str = "",
    external_bank: bool = True,
) -> str:
    """Chrome Intent for Android, where App Links are less reliable than intent://."""
    candidates = build_kaspi_deeplink_candidates(
        card=card,
        phone=phone,
        amount=amount,
        owner=owner,
        external_bank=external_bank,
    )
    for item in candidates:
        if item.get("type") == "intent":
            return str(item.get("url") or "")
    path = "/kz/transfers/card_to_card" if external_bank else "/kz/transfers/client"
    return _android_intent_https(path, "")


def build_transfer_clipboard(
    *,
    amount: str | Decimal,
    currency: str,
    payment_details: dict[str, Any],
    locale: str = "kk",
) -> str:
    pd = payment_details or {}
    card = _digits(pd.get("card_number") or "")
    phone = (pd.get("phone") or "").strip()
    owner = (pd.get("owner") or "").strip()
    bank = (pd.get("bank") or pd.get("bankName") or "").strip()
    amt = _format_amount(amount)

    if locale == "kk":
        lines = [f"Сома: {amt} {currency}"]
        if card:
            lines.append(f"Карта: {card}")
        if phone:
            lines.append(f"Телефон: {phone}")
        if owner:
            lines.append(f"Алушы: {owner}")
        if bank:
            lines.append(f"Банк: {bank}")
        return "\n".join(lines)

    lines = [f"Сумма: {amt} {currency}"]
    if card:
        lines.append(f"Карта: {card}")
    if phone:
        lines.append(f"Телефон: {phone}")
    if owner:
        lines.append(f"Получатель: {owner}")
    if bank:
        lines.append(f"Банк: {bank}")
    return "\n".join(lines)


def build_bank_actions(
    *,
    amount: str | Decimal,
    currency: str,
    payment_details: dict[str, Any],
    locale: str = "kk",
    sender_bank: str | None = None,
) -> list[dict[str, str]]:
    """
    Кнопки «открыть банк».
    sender_bank: kaspi | halyk — только одна кнопка (для Melbet KZT по методу).
    """
    pd = payment_details or {}
    bank = _norm_bank(pd.get("bank") or pd.get("bankName") or "")
    phone = _digits(pd.get("phone") or "")
    card = _digits(pd.get("card_number") or "")
    owner = (pd.get("owner") or "").strip()
    external_bank = not _is_kaspi_recipient_bank(bank)

    kaspi_primary = get_kaspi_primary_deeplink(
        card=card,
        phone=phone,
        amount=amount,
        owner=owner,
        external_bank=external_bank,
    )
    kaspi_android = get_kaspi_android_intent(
        card=card,
        phone=phone,
        amount=amount,
        owner=owner,
        external_bank=external_bank,
    )
    kaspi_https = kaspi_primary if kaspi_primary.startswith("https://") else _fallback_kaspi_https(external_bank)
    kaspi_hint_kk = (
        "Kaspi қосымшасы → Аударымдар. Реквизиттер көшірілген — карта мен соманы қойыңыз, егер өрістер бос болса."
    )
    kaspi_hint_ru = (
        "Откроется приложение Kaspi → Переводы. Реквизиты скопированы — вставьте карту и сумму, если поля пустые."
    )
    if not card and not phone:
        kaspi_hint_kk = "«Барлығын көшіру» → Kaspi → Сыртқы картаға аударым"
        kaspi_hint_ru = "«Скопировать всё» → Kaspi → Перевод на карту другого банка"

    actions: list[dict[str, str]] = []

    def add(
        action_id: str,
        label_kk: str,
        label_ru: str,
        url: str,
        hint_kk: str,
        hint_ru: str,
        *,
        primary_url: str = "",
        android_url: str = "",
    ):
        item = {
            "id": action_id,
            "label": label_kk if locale == "kk" else label_ru,
            "url": url,
            "hint": hint_kk if locale == "kk" else hint_ru,
        }
        if primary_url:
            item["primary_url"] = primary_url
        if android_url:
            item["android_url"] = android_url
        actions.append(item)

    def add_kaspi(action_id: str):
        add(
            action_id,
            "Kaspi-де ашу",
            "Открыть Kaspi",
            kaspi_https,
            kaspi_hint_kk,
            kaspi_hint_ru,
            primary_url=kaspi_https,
            android_url=kaspi_android,
        )

    def add_halyk(action_id: str = "halyk"):
        add(
            action_id,
            "Homebank-та ашу",
            "Открыть Homebank",
            "https://homebank.kz/",
            "Аудару → карта/by phone",
            "Перевод → на карту/телефон",
        )

    preferred = (sender_bank or "").strip().lower()
    if preferred == "kaspi":
        add_kaspi("kaspi")
        return actions
    if preferred == "halyk":
        add_halyk()
        return actions

    if "kaspi" in bank:
        add_kaspi("kaspi")

    if any(x in bank for x in ("halyk", "homebank", "хalyk")):
        add_halyk()

    if "forte" in bank:
        add(
            "forte",
            "ForteBank-та ашу",
            "Открыть ForteBank",
            "https://fortebank.com/",
            "",
            "",
        )

    if "jusan" in bank or "alatau" in bank:
        add(
            "jusan",
            "Jusan-да ашу",
            "Открыть Jusan",
            "https://jusan.kz/",
            "",
            "",
        )

    if currency.upper() == "KZT" and not any(a["id"] in ("kaspi", "kaspi_generic") for a in actions):
        add_kaspi("kaspi_generic")

    return actions
