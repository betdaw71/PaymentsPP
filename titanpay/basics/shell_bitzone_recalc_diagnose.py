"""
Диагностика Bitzone перерасчёта по PayIn UUID + опциональный replay из last_webhook_payload.

Пример (dry-run):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_bitzone_recalc_diagnose.py

Replay перерасчёта — env внутрь контейнера через -e (не снаружи compose):
  docker compose exec -T \\
    -e PAYIN_ID=b4680fcc-60eb-4395-9e89-ad0cb56d569a \\
    -e APPLY=1 \\
    app python manage.py shell < titanpay/basics/shell_bitzone_recalc_diagnose.py
"""
from __future__ import annotations

import json
import os

from payments.models import BitzonePayInSession, PayIn, PayInTraceLog
from payments.psp_payin import handle_psp_success_webhook, parse_psp_webhook_paid_amount

PAYIN_ID = os.environ.get("PAYIN_ID", "b4680fcc-60eb-4395-9e89-ad0cb56d569a").strip()
APPLY = os.environ.get("APPLY", "").strip() in ("1", "true", "yes")
SIG_HINT = os.environ.get("SIG_HINT", "").strip()


def main() -> None:
    pay_in = PayIn.objects.select_related(
        "status",
        "merchant__user",
        "order",
        "order__status",
    ).get(id=PAYIN_ID)

    order = pay_in.order
    print(f"=== PayIn {pay_in.id} ===")
    print(f"merchant:      {pay_in.merchant.user.username if pay_in.merchant else None}")
    print(f"pay_in.status: {pay_in.status.name if pay_in.status else None}")
    print(f"amount:        {pay_in.amount}")
    print(f"recalculated:  {pay_in.recalculated}")

    if order:
        print(f"\n=== InOrder {order.id} ===")
        print(f"status:        {order.status.name if order.status else None}")
        print(f"amount:        {order.amount}")
        print(f"recalculated:  {order.recalculated}")
        print(f"recalc_amount: {order.recalculated_amount}")

    try:
        session = BitzonePayInSession.objects.get(pay_in=pay_in)
    except BitzonePayInSession.DoesNotExist:
        print("\nBitzone session: NOT FOUND")
        return

    print(f"\n=== Bitzone session ===")
    print(f"provider_id:   {session.provider_transaction_id}")
    print(f"external_id:   {session.external_id}")
    print(f"last_status:   {session.last_notified_status}")
    body = session.last_webhook_payload or {}
    print(f"last_webhook:\n{json.dumps(body, ensure_ascii=False, indent=2)}")

    paid = parse_psp_webhook_paid_amount(body) if body else None
    print(f"\nparsed_paid_amount: {paid}")

    traces = (
        PayInTraceLog.objects.filter(pay_in=pay_in, direction="bitzone_webhook")
        .order_by("-created_at")[:10]
    )
    print(f"\n=== Bitzone webhook traces ({traces.count()} latest) ===")
    for t in traces:
        st = (t.body or {}).get("status") if isinstance(t.body, dict) else None
        print(f"  {t.created_at} status={st} note={t.note}")

    if SIG_HINT:
        print(f"\nSignature hint from ops: {SIG_HINT}")
        print("Verify with: python basics/shell_verify_bitzone_webhook.py (paste raw body + sig)")

    if not body:
        print("\nNo last_webhook_payload — webhook likely never passed signature/session lookup.")
        return

    if not APPLY:
        print("\nDry-run. Replay:")
        print("  docker compose exec -T -e PAYIN_ID=%s -e APPLY=1 app python manage.py shell < titanpay/basics/shell_bitzone_recalc_diagnose.py" % PAYIN_ID)
        return

    if not order:
        print("\nNo InOrder — cannot apply.")
        return

    from django.db import transaction

    with transaction.atomic():
        locked = type(order).objects.select_for_update().get(pk=order.pk)
        result = handle_psp_success_webhook(locked, body)
    print(f"\nReplay result: {result}")


main()
