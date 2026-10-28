"""Найти PayIn по id из кабинета PSP и показать, уходил ли колбек мерчу."""
from django.apps import apps
from django.db.models import Q
from django.db.models.fields import IntegerField

from payments.models import PayInTraceLog

RAW = """
a77fa0abb-2df3-4774-8e07-7e8ed835fc99g
afba32b04-bf65-41af-929b-34fa2dfd65f2g
aa4000d66-5786-4182-8bc8-f84d377f676ag
a34474ff0-88d1-4467-abfb-6111bf138e03g
a4a8bdc88-b34e-40a7-9446-7b54660e1fedg
acae1a135-925a-4022-8145-391d354a00fbg
a4510e426-9987-47ba-966e-80f339f269d4g
af6a0e9b6-6a6e-45d8-a02c-5d08f384f441g
ae2f684b1-a552-41f6-b8cb-7aa071ec7120g
"""

FIELDS = (
    "external_id",
    "provider_order_id",
    "provider_payment_id",
    "provider_invoice_id",
    "provider_deal_id",
    "provider_transaction_id",
)


def variants(raw: str) -> list[str]:
    s = raw.strip()
    out = [s]
    if s.startswith("a") and s.endswith("g") and "-" in s:
        out.append(s[1:-1])
    return out


sessions = [
    m
    for m in apps.get_app_config("payments").get_models()
    if m.__name__.endswith("PayInSession")
]

for raw in RAW.splitlines():
    raw = raw.strip()
    if not raw:
        continue
    keys = variants(raw)
    print("=" * 72)
    print("PSP id:", " | ".join(keys))
    found = []
    for model in sessions:
        q = Q()
        for field in model._meta.fields:
            if field.name not in FIELDS:
                continue
            for key in keys:
                if isinstance(field, IntegerField):
                    if not key.isdigit():
                        continue
                    q |= Q(**{field.name: int(key)})
                else:
                    q |= Q(**{field.name: key})
        if not q:
            continue
        for row in model.objects.filter(q).select_related(
            "pay_in", "pay_in__status", "pay_in__merchant__user", "pay_in__order__status"
        ):
            found.append((model.__name__, row))
    if not found:
        print("  NOT FOUND")
        continue
    for name, row in found:
        pi = row.pay_in
        order = getattr(pi, "order", None)
        print(f"  {name}")
        print(f"  payin={pi.id}")
        print(f"  merchant={pi.merchant.user.username if pi.merchant_id else None} moid={pi.merchant_order_id}")
        print(f"  payin_status={pi.status.name if pi.status_id else None}")
        print(f"  inorder={order.status.name if order and order.status_id else None}")
        for field in FIELDS:
            if hasattr(row, field):
                val = getattr(row, field)
                if val not in (None, ""):
                    print(f"  {field}={val}")
        cbs = list(PayInTraceLog.objects.filter(pay_in=pi, direction="merchant_callback").order_by("created_at"))
        print(f"  merchant_callback count={len(cbs)}")
        if not cbs:
            print("  callback: НЕ УХОДИЛ")
        for t in cbs:
            print(f"    {t.created_at} http={t.http_status} note={t.note!r}")
            print(f"    url={t.url}")
