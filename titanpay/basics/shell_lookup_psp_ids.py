"""PayIn по merchant_order_id AggrePay (строка как есть, с a…g) + колбеки мерчу."""
from payments.models import PayIn, PayInTraceLog

IDS = [
    "a77fa0abb-2df3-4774-8e07-7e8ed835fc99g",
    "afba32b04-bf65-41af-929b-34fa2dfd65f2g",
    "aa4000d66-5786-4182-8bc8-f84d377f676ag",
    "a34474ff0-88d1-4467-abfb-6111bf138e03g",
    "a4a8bdc88-b34e-40a7-9446-7b54660e1fedg",
    "acae1a135-925a-4022-8145-391d354a00fbg",
    "a4510e426-9987-47ba-966e-80f339f269d4g",
    "af6a0e9b6-6a6e-45d8-a02c-5d08f384f441g",
    "ae2f684b1-a552-41f6-b8cb-7aa071ec7120g",
]

for moid in IDS:
    print("=" * 72)
    print("merchant_order_id:", moid)
    pi = (
        PayIn.objects.select_related("status", "merchant__user", "order__status", "payment_system")
        .filter(merchant_order_id=moid)
        .order_by("-created_at")
        .first()
    )
    if pi is None:
        print("  NOT FOUND")
        continue
    order = pi.order
    print(f"  payin={pi.id}")
    print(f"  merchant={pi.merchant.user.username if pi.merchant_id else None}")
    print(f"  ps={pi.payment_system.name if pi.payment_system_id else None} amount={pi.amount}")
    print(f"  payin_status={pi.status.name if pi.status_id else None}")
    print(f"  inorder_status={order.status.name if order and order.status_id else None}")
    print(f"  callback_url={pi.callback_url}")
    cbs = list(
        PayInTraceLog.objects.filter(pay_in=pi, direction="merchant_callback").order_by("created_at")
    )
    print(f"  merchant_callback count={len(cbs)}")
    if not cbs:
        print("  callback: НЕ УХОДИЛ")
    for t in cbs:
        print(f"    {t.created_at} http={t.http_status} note={t.note!r}")
        print(f"    url={t.url}")
        body = t.body if isinstance(t.body, dict) else {}
        if body:
            print("   ", str(body)[:500])
