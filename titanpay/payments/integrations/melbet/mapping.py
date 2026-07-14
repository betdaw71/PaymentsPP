from __future__ import annotations

from payments.integrations.melbet.models import MelbetIntegrationConfig

TERMINAL_CALLBACK_STATUSES = frozenset({"Success", "Failed", "Declined", "Expired"})

MELBET_STATUS_SUCCESS = "SUCCESS"
MELBET_STATUS_FAILED = "FAILED"
MELBET_STATUS_PENDING = "PENDING"


def merchant_uses_melbet(merchant) -> bool:
    if merchant is None:
        return False
    return MelbetIntegrationConfig.objects.filter(merchant=merchant, active=True).exists()


def melbet_config_for_merchant(merchant) -> MelbetIntegrationConfig | None:
    if merchant is None:
        return None
    return MelbetIntegrationConfig.objects.filter(merchant=merchant, active=True).first()


def sender_bank_for_melbet_method(melbet_method: str | None) -> str | None:
    """
    Банк отправителя по методу Melbet → кнопка на платёжной странице.
    card2card_kzt_kaspi — только Kaspi; card2card_kzt — только Halyk/Homebank.
    """
    method = (melbet_method or "").strip().lower()
    if method == "card2card_kzt_kaspi":
        return "kaspi"
    if method == "card2card_kzt":
        return "halyk"
    return None


def resolve_method_entry(
    config: MelbetIntegrationConfig,
    *,
    currency: str,
    method: str | None,
) -> dict:
    method_map = config.method_map if isinstance(config.method_map, dict) else {}
    cur = (currency or "").strip().upper()
    if not cur:
        raise ValueError("currency is required")
    meth = (method or "").strip().lower()

    lookup_keys: list[str] = []
    if meth:
        lookup_keys.append(f"{meth}_{cur.lower()}")
        lookup_keys.append(meth)
    lookup_keys.append(f"default_{cur.lower()}")
    lookup_keys.append("default")

    for key in lookup_keys:
        entry = method_map.get(key)
        if not isinstance(entry, dict) or not entry.get("payment_system"):
            continue
        entry_currency = (entry.get("currency") or cur).strip().upper()
        if entry_currency != cur:
            continue
        ps = str(entry["payment_system"]).strip()
        return {"payment_system": ps, "currency": cur}

    raise ValueError(f"Payment method '{method or 'default'}' is not configured for currency {cur}")


def map_internal_status_to_melbet(status_name: str | None) -> str | None:
    if not status_name:
        return None
    if status_name == "Success":
        return MELBET_STATUS_SUCCESS
    if status_name in ("Failed", "Declined", "Expired"):
        return MELBET_STATUS_FAILED
    if status_name in ("New", "In Progress"):
        return MELBET_STATUS_PENDING
    return MELBET_STATUS_PENDING


def mask_account_number(raw: str | None) -> str:
    value = (raw or "").replace(" ", "")
    if not value:
        return ""
    if value.startswith("+") or "@" in value:
        return value
    if len(value) >= 16 and value.isdigit():
        return f"{value[:6]}**{'*' * 4}{value[-4:]}"
    if value.upper().startswith("TR") and len(value) > 8:
        return f"{value[:4]}****{value[-4:]}"
    if len(value) > 8:
        return f"{value[:4]}****{value[-4:]}"
    return value


def account_number_to_details(account_number: str, payment_system_name: str) -> dict:
    acct = (account_number or "").strip().replace(" ", "")
    ps = (payment_system_name or "").upper()
    if ps == "C2CTRY" or acct.upper().startswith("TR"):
        return {"iban": acct}
    if acct.startswith("+"):
        return {"phone": acct}
    if acct.isdigit() and len(acct) == 16:
        return {"card_number": acct}
    return {"card_number": acct}


def client_name_from_fields(fields: dict | None) -> str | None:
    fields = fields if isinstance(fields, dict) else {}
    parts = [
        (fields.get("first_name") or fields.get("firstName") or "").strip(),
        (fields.get("middle_name") or fields.get("middleName") or "").strip(),
        (fields.get("last_name") or fields.get("lastName") or "").strip(),
    ]
    name = " ".join(p for p in parts if p).strip()
    return name or None
