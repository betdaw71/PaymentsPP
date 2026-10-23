"""Map merchant payout payment systems before routing (Mostbet C2C → C2CKZT)."""
from __future__ import annotations

from django.conf import settings

from basics.models import PaymentSystem


def payout_c2c_to_c2ckzt_usernames() -> set[str]:
    raw = getattr(settings, "PAYOUT_C2C_TO_C2CKZT_MERCHANTS", None)
    if raw is None:
        raw = "mostbet"
    if isinstance(raw, (list, tuple, set)):
        parts = [str(p) for p in raw]
    else:
        parts = str(raw).split(",")
    return {p.strip().lower() for p in parts if p.strip()}


def remap_payout_payment_system_id(data: dict, merchant) -> dict:
    """Mostbet C2C (KZT) payouts are executed as C2CKZT (PayPlat C2C USD corridor)."""
    if not merchant or not getattr(merchant, "user", None):
        return data
    username = (merchant.user.username or "").strip().lower()
    if username not in payout_c2c_to_c2ckzt_usernames():
        return data

    ps_id = data.get("payment_system")
    if not ps_id:
        return data
    ps = PaymentSystem.objects.filter(pk=ps_id).select_related("currency").first()
    if ps is None:
        return data
    if (ps.name or "").strip().upper() != (getattr(settings, "C2C_NAME", None) or "C2C"):
        return data
    symbol = (ps.currency.symbol if ps.currency else "").strip().upper()
    if symbol != "KZT":
        return data

    c2ckzt_name = (getattr(settings, "C2CKZT_NAME", None) or "C2CKZT").strip() or "C2CKZT"
    mapped = PaymentSystem.objects.filter(name__iexact=c2ckzt_name, currency=ps.currency).first()
    if mapped is None:
        return data
    data = dict(data)
    data["payment_system"] = mapped.id
    return data
