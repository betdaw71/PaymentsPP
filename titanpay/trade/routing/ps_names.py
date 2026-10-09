"""Имена карточных PS и банк-алиасы для KZT C2C / C2CKZT."""
from __future__ import annotations

from django.conf import settings

from basics.models import PaymentSystem


def c2ckzt_name() -> str:
    return (getattr(settings, "C2CKZT_NAME", None) or "C2CKZT").strip() or "C2CKZT"


def kzt_c2c_merchant_ps_names() -> set[str]:
    """PS, которые мерчант шлёт по KZT трансграну (карта)."""
    names = {settings.C2C_NAME, c2ckzt_name()}
    proto = (getattr(settings, "PROTOCOL_C2C_NAME", None) or "").strip()
    if proto:
        names.add(proto)
    return names


def kzt_c2c_bank_ps_names() -> set[str]:
    """Банки-PS: группа на них попадает в роутинг C2C/C2CKZT, имя уходит в поле bank."""
    raw = getattr(settings, "KZT_C2C_BANK_PS_NAMES", None)
    if raw is None:
        raw = "Vietcombank"
    if isinstance(raw, (list, tuple, set)):
        parts = [str(p) for p in raw]
    else:
        parts = str(raw).split(",")
    return {p.strip() for p in parts if p.strip()}


def card_like_ps_names() -> set[str]:
    names = {
        settings.SBER_NAME,
        settings.C2C_NAME,
        settings.PROTOCOL_C2C_NAME,
        *kzt_c2c_bank_ps_names(),
    }
    test_ps = (getattr(settings, "PLUTUS_TEST_PS_NAME", None) or "").strip()
    if test_ps:
        names.add(test_ps)
    return names


def routing_payment_systems(payment_system: PaymentSystem) -> list[PaymentSystem]:
    """PS групп, которые можно взять при заявке на payment_system."""
    names = {payment_system.name}
    if payment_system.name in kzt_c2c_merchant_ps_names():
        names |= kzt_c2c_bank_ps_names()
    qs = PaymentSystem.objects.filter(name__in=names)
    if payment_system.currency_id:
        qs = qs.filter(currency_id=payment_system.currency_id)
    found = {ps.id: ps for ps in qs}
    found[payment_system.id] = payment_system
    return list(found.values())
