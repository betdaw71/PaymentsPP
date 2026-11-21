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
    Банк отправителя на платёжной странице Melbet KZT.

    card2card_kzt_kaspi / *kaspi* — Kaspi, международные переводы.
    card2card_kzt / *halyk* / *homebank* — Homebank, перевод на зарубежную карту.
    phone_kzt / *phone* / *mobile* — перевод по номеру, без карточных гайдов.
    qr_kgs / *_kgs / lkq / elqr — локальный KGS, без Kaspi/Halyk гайдов.
    """
    method = (melbet_method or "").strip().lower()
    if not method:
        return None
    if method.endswith("_kgs") or "kgs" in method or method in {"lkq", "elqr", "qr"}:
        return None
    if "phone" in method or "mobile" in method:
        return None
    if "kaspi" in method:
        return "kaspi"
    if "halyk" in method or "homebank" in method or method in {"card2card_kzt", "c2ckzt"}:
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
    """Melbet withdrawal account_number → destination details for OutOrder.check_details.

    Local KGS PS required_fields include bank_name (and QR fields) — fill defaults so
    Melbet host-to-host payouts are not rejected before routing.
    """
    acct = (account_number or "").strip().replace(" ", "")
    ps = (payment_system_name or "").upper()
    if ps == "C2CTRY" or acct.upper().startswith("TR"):
        return {"iban": acct}

    digits = "".join(c for c in acct if c.isdigit())
    is_kgs = ps in {"C2CKGS", "PHONEKGS", "QRKGS"} or ps.endswith("KGS")

    if ps in {"PHONEKGS", "PHONEKZT"} or acct.startswith("+") or (
        is_kgs and ps.startswith("PHONE") and digits
    ):
        phone = acct if acct.startswith("+") else (f"+{digits}" if digits else acct)
        out: dict[str, str] = {"phone": phone}
        if is_kgs or ps == "PHONEKGS":
            out["bank_name"] = "MBank"
        if ps == "QRKGS":
            # PS requires qr_payload + phone; Melbet may send only phone/account.
            out["qr_payload"] = phone or acct or "pending"
        return out

    if digits and len(digits) >= 16:
        out = {"card_number": digits[:19]}
        if is_kgs or ps in {"C2CKGS", "C2CKZT"}:
            out["bank_name"] = "MBank"
        return out

    out = {"card_number": acct}
    if is_kgs:
        out["bank_name"] = "MBank"
    return out


def client_name_from_fields(fields: dict | None) -> str | None:
    fields = fields if isinstance(fields, dict) else {}
    parts = [
        (fields.get("first_name") or fields.get("firstName") or "").strip(),
        (fields.get("middle_name") or fields.get("middleName") or "").strip(),
        (fields.get("last_name") or fields.get("lastName") or "").strip(),
    ]
    name = " ".join(p for p in parts if p).strip()
    return name or None
