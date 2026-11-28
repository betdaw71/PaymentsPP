"""Костыль pay-in C2C KZT.

pandapay шлёт трансгран как C2C — до поиска солюшна читаем это как C2CKZT
и оставляем его на текущем каскаде C2CKZT.
Локальный каскад (второй Astrum, затем Prochub) только у мерчантов из
PAYIN_LOCAL_C2C_KZT_MERCHANTS. Остальные C2C KZT и все прочие методы не трогаем.
"""
from django.conf import settings


def payin_c2c_kzt_as_c2ckzt_usernames() -> set[str]:
    raw = getattr(settings, "PAYIN_C2C_KZT_AS_C2CKZT_MERCHANTS", "pandapay") or ""
    return {p.strip().lower() for p in str(raw).split(",") if p.strip()}


def _merchant_username(merchant) -> str:
    user = getattr(merchant, "user", None)
    return (getattr(user, "username", None) or "").strip().lower()


def payin_local_c2c_kzt_usernames() -> set[str]:
    raw = getattr(settings, "PAYIN_LOCAL_C2C_KZT_MERCHANTS", None)
    if raw is None:
        raw = "pandapay_local_kzt,pandapay_kz_local"
    return {p.strip().lower() for p in str(raw).split(",") if p.strip()}


def merchant_sends_c2c_kzt_as_transgran(merchant) -> bool:
    name = _merchant_username(merchant)
    return bool(name) and name in payin_c2c_kzt_as_c2ckzt_usernames()


def is_c2c_kzt_payment_system(payment_system) -> bool:
    if payment_system is None:
        return False
    name = (getattr(payment_system, "name", None) or "").strip().upper()
    c2c = (getattr(settings, "C2C_NAME", None) or "C2C").strip().upper()
    if name != c2c:
        return False
    currency = getattr(payment_system, "currency", None)
    symbol = (getattr(currency, "symbol", None) or "").strip().upper()
    return symbol == "KZT"


def local_kzt_c2c_cascade_for(merchant, payment_system) -> dict[str, int] | None:
    """Локальный C2C KZT только для явного списка. Чужие каскады не подменяем."""
    if merchant is None or not is_c2c_kzt_payment_system(payment_system):
        return None
    if merchant_sends_c2c_kzt_as_transgran(merchant):
        return None
    if _merchant_username(merchant) not in payin_local_c2c_kzt_usernames():
        return None
    from payments.astrum_client import astrum_local_trader_username
    from payments.prochub_client import prochub_trader_username

    return {
        astrum_local_trader_username(): 1,
        prochub_trader_username(): 2,
    }


def local_c2c_provider_groups(payment_system):
    """Группы второго Astrum и Prochub на валюте заявки, даже если они заведены не на C2C."""
    from basics.models import PaymentDetailsGroup
    from payments.astrum_client import astrum_local_trader_username
    from payments.prochub_client import prochub_trader_username

    qs = PaymentDetailsGroup.objects.filter(
        trader__user__username__in=[
            astrum_local_trader_username(),
            prochub_trader_username(),
        ],
        status=1,
        in_active=True,
        work_type="by_card",
        trader__blocked=False,
    )
    currency_id = getattr(payment_system, "currency_id", None)
    if currency_id:
        qs = qs.filter(currency_id=currency_id)
    return qs


def remap_payin_payment_system_id(data: dict, merchant) -> dict:
    """pandapay + C2C + KZT → C2CKZT той же валюты. Остальное без изменений."""
    if not isinstance(data, dict) or not merchant_sends_c2c_kzt_as_transgran(merchant):
        return data
    ps_id = data.get("payment_system")
    if not ps_id:
        return data
    from basics.models import PaymentSystem

    ps = (
        PaymentSystem.objects.select_related("currency")
        .filter(id=ps_id)
        .first()
    )
    if ps is None or not is_c2c_kzt_payment_system(ps):
        return data
    target_name = (getattr(settings, "C2CKZT_NAME", None) or "C2CKZT").strip()
    target = (
        PaymentSystem.objects.filter(name__iexact=target_name, currency_id=ps.currency_id)
        .order_by("id")
        .first()
    )
    if target is None or target.id == ps.id:
        return data
    data = dict(data)
    data["payment_system"] = target.id
    return data
