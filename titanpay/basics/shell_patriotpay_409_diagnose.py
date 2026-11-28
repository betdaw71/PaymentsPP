"""
Почему PatriotPay paid webhook отвечает 409.

  docker-compose exec -T app python3 manage.py shell < titanpay/basics/shell_patriotpay_409_diagnose.py

Закрыть заявки из last paid payload:
  docker-compose exec -T -e APPLY=1 app python3 manage.py shell < titanpay/basics/shell_patriotpay_409_diagnose.py

Опционально:
  PAY_IN_IDS=uuid1,uuid2
"""
from __future__ import annotations

import os

from django.db import transaction
from rest_framework.exceptions import ValidationError

from basics.models import Trader
from payments.models import PatriotpayPayInSession, PayInTraceLog
from payments.psp_payin import (
    handle_psp_success_webhook,
    parse_psp_webhook_paid_amount,
    psp_order_usd_ledger_amount,
)
from trade.models import InOrder, Transaction

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes", "y", "on"}

DEFAULT_IDS = (
    "7443256f-2fcf-42b9-ab97-a8f96a4cab03",
    "3d7f77d9-c1e5-4d9b-aaf5-5b694d2ca406",
)


def _ids() -> list[str]:
    raw = (os.environ.get("PAY_IN_IDS") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return list(DEFAULT_IDS)


tp = (
    Trader.objects.select_related("user", "balance_usdt", "frozen_balance_usdt")
    .get(user__username="patriot1")
)
print(
    "patriot1 available",
    tp.balance_usdt.amount if tp.balance_usdt_id else None,
    "frozen",
    tp.frozen_balance_usdt.amount if tp.frozen_balance_usdt_id else None,
    "credit",
    tp.credit_limit,
)

for pid in _ids():
    s = PatriotpayPayInSession.objects.select_related(
        "pay_in__status",
        "pay_in__order__status",
        "pay_in__order__payment_details",
    ).get(pay_in_id=pid)
    pi = s.pay_in
    od = pi.order
    body = s.last_webhook_payload if isinstance(s.last_webhook_payload, dict) else {}
    paid = parse_psp_webhook_paid_amount(body)
    inv = body.get("invoice") if isinstance(body.get("invoice"), dict) else {}
    print("=" * 72)
    print(pid)
    print(" payin", pi.status.name, "inorder", od.status.name if od.status else None)
    print(
        " amount",
        od.amount,
        "usd",
        od.usd_amount,
        "psp_ledger",
        psp_order_usd_ledger_amount(od) if od.payment_details_id else None,
    )
    print(" parsed_paid", paid)
    print(" invoice.status", inv.get("status"), "invoice.amount", inv.get("amount"), "sum", inv.get("sum"))
    for tx in (
        Transaction.objects.filter(linked_in_order=od)
        .select_related("transaction_type")
        .order_by("creation_date")
    ):
        print(" TX", tx.creation_date, tx.transaction_type.name, tx.value, tx.comment)
    for t in PayInTraceLog.objects.filter(pay_in=pi, direction="merchant_callback").order_by(
        "created_at"
    ):
        print(" CB", t.created_at, "http", t.status_code, t.note)
    try:
        with transaction.atomic():
            locked = InOrder.objects.select_for_update().get(pk=od.pk)
            outcome = handle_psp_success_webhook(locked, body)
            print(" DRY outcome", outcome, "would_status", locked.status.name)
            if APPLY:
                print(" APPLIED")
            else:
                raise RuntimeError("rollback")
    except RuntimeError:
        print(" DRY rolled back")
    except ValidationError as e:
        print(" DRY ValidationError", e.detail)
    except Exception as e:
        print(" DRY", type(e).__name__, e)
