"""Грузинские банки не выдаём только перечисленным мерчантам.

Если провайдер или живой трейдер вернул реквизит, у которого поле bank
равно или содержит TBC, Bank of Georgia / Gorgia или BOG, заявку этого
мерчанта не закрываем этим реквизитом — запрос повторяется.
Остальные мерчанты не фильтруются.
"""
from __future__ import annotations

import re

GEORGIAN_BANK_BLOCKED = "georgian_bank_blocked"

_FOLD = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "к": "k",
        "т": "t",
        "б": "b",
        "в": "b",
        "м": "m",
        "н": "h",
        "і": "i",
        "ё": "e",
        "й": "i",
    }
)


def _merchant_usernames() -> set[str]:
    from django.conf import settings

    raw = getattr(settings, "GEORGIAN_BANK_BLOCK_MERCHANTS", "artur_kids")
    if isinstance(raw, (list, tuple, set)):
        parts = [str(item) for item in raw]
    else:
        parts = str(raw or "").split(",")
    return {part.strip().lower() for part in parts if part and part.strip()}


def merchant_username(merchant) -> str:
    if merchant is None:
        return ""
    if isinstance(merchant, str):
        return merchant.strip().lower()
    user = getattr(merchant, "user", None)
    return (getattr(user, "username", None) or "").strip().lower()


def merchant_blocks_georgian_banks(merchant) -> bool:
    username = merchant_username(merchant)
    return bool(username) and username in _merchant_usernames()


def payin_merchant(pay_in):
    order = getattr(pay_in, "order", None)
    solution = getattr(order, "solution", None) if order is not None else None
    merchant = getattr(solution, "merchant", None) if solution is not None else None
    if merchant is not None:
        return merchant
    return getattr(pay_in, "merchant", None)


def payin_blocks_georgian_banks(pay_in) -> bool:
    return merchant_blocks_georgian_banks(payin_merchant(pay_in))


def georgian_bank_retry_limit() -> int:
    from django.conf import settings

    raw = getattr(settings, "GEORGIAN_BANK_REQUISITE_RETRIES", 5)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = 5
    return max(1, limit)


def _normalize_bank(value: str | None) -> str:
    text = (value or "").strip().lower().translate(_FOLD)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def bank_name_is_georgian(value: str | None) -> bool:
    """Равно или содержит TBC / Bank of Georgia / BOG. Пустое имя — не грузинский банк."""
    text = _normalize_bank(value)
    if not text:
        return False
    compact = text.replace(" ", "")
    if "tbc" in compact:
        return True
    if "bank of georgia" in text or "bank of gorgia" in text:
        return True
    if "bankofgeorgia" in compact or "bankofgorgia" in compact:
        return True
    if re.search(r"(^| )bog( |$)", text) or "bog" in compact:
        return True
    return False


def detail_bank_is_georgian(detail) -> bool:
    """Банк, который уйдёт мерчанту с карты живого трейдера."""
    custom = (getattr(detail, "bank_name", None) or "").strip()
    group = getattr(detail, "group", None)
    payment_system = getattr(group, "payment_system", None) if group is not None else None
    ps_name = (getattr(payment_system, "name", None) or "").strip()
    from payments.utils import translate_bank

    shown = custom or (translate_bank(ps_name) or "")
    return bank_name_is_georgian(shown) or bank_name_is_georgian(ps_name)


def exclude_georgian_human_details(details, merchant):
    """Убрать карты с грузинским банком. Для других мерчантов queryset не меняется."""
    if not merchant_blocks_georgian_banks(merchant):
        return details, False
    blocked_ids = [
        detail.pk
        for detail in details.select_related("group__payment_system")
        if detail_bank_is_georgian(detail)
    ]
    if not blocked_ids:
        return details, False
    return details.exclude(pk__in=blocked_ids), True


def requisite_bank(req: dict | None) -> str:
    if not isinstance(req, dict):
        return ""
    return str(req.get("bank") or req.get("bank_name") or "").strip()


def requisite_bank_is_georgian(req: dict | None) -> bool:
    return bank_name_is_georgian(requisite_bank(req))


_PAYIN_SESSION_MODELS = (
    "FairpayPayInSession",
    "ExpayonePayInSession",
    "ProtocolPayInSession",
    "LayeronePayInSession",
    "GipayPayInSession",
    "VisionxPayInSession",
    "NexusPayInSession",
    "PrismaPayInSession",
    "ProchubPayInSession",
    "PatriotpayPayInSession",
    "PayplatPayInSession",
    "BitzonePayInSession",
    "SyndicatePayInSession",
    "BotonpayPayInSession",
    "PlutusPayInSession",
    "ConcoredPayInSession",
    "PaymapPayInSession",
    "PlaymentsPayInSession",
    "AstrumPayInSession",
)

_PROVIDER_ID_FIELDS = (
    "provider_order_id",
    "provider_invoice_id",
    "provider_deal_id",
    "provider_transaction_id",
    "provider_payment_id",
)


def scrub_psp_sessions(pay_in, *, bank: str, attempt: int) -> None:
    """Снять выданный реквизит, чтобы следующий запрос не отдал тот же банк."""
    from payments import models as payment_models

    payload = {
        "error": GEORGIAN_BANK_BLOCKED,
        "bank": bank,
        "attempt": attempt,
    }
    for model_name in _PAYIN_SESSION_MODELS:
        model = getattr(payment_models, model_name, None)
        if model is None:
            continue
        field_names = {field.name for field in model._meta.fields}
        if "create_response" not in field_names or "pay_in" not in field_names:
            continue
        for session in model.objects.filter(pay_in=pay_in):
            session.create_response = payload
            update_fields = ["create_response"]
            for field_name in _PROVIDER_ID_FIELDS:
                if field_name in field_names:
                    setattr(session, field_name, "")
                    update_fields.append(field_name)
            if "external_id" in field_names:
                current = str(getattr(session, "external_id", "") or "")
                if ":rejected:" not in current:
                    session.external_id = f"{current or pay_in.id}:rejected:{attempt}"
                    update_fields.append("external_id")
            session.save(update_fields=update_fields)


def psp_rejected_georgian_bank(pay_in) -> bool:
    from payments import models as payment_models

    for model_name in _PAYIN_SESSION_MODELS:
        model = getattr(payment_models, model_name, None)
        if model is None:
            continue
        field_names = {field.name for field in model._meta.fields}
        if "create_response" not in field_names or "pay_in" not in field_names:
            continue
        for body in model.objects.filter(pay_in=pay_in).values_list("create_response", flat=True):
            if isinstance(body, dict) and body.get("error") == GEORGIAN_BANK_BLOCKED:
                return True
    return False


def payplat_external_id(pay_in, session) -> str:
    """Первый запрос — id заявки. Повтор после грузинского банка — новый id сделки PayPlat."""
    base = str(pay_in.id)
    if not payin_blocks_georgian_banks(pay_in):
        return base
    body = session.create_response if isinstance(getattr(session, "create_response", None), dict) else {}
    if body.get("error") != GEORGIAN_BANK_BLOCKED:
        return base
    attempt = int(body.get("attempt") or 1)
    return f"{base}:{attempt + 1}"
