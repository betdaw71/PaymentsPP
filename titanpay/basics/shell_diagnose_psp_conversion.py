"""
Диагностика 0-конверсии PSP: выданы реквизиты vs Success vs дошёл ли webhook.

Только читает. Ничего не закрывает и не начисляет.

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_diagnose_psp_conversion.py

Опционально:
  DAYS=2 LIMIT=30
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from payments.gipay_client import gipay_map_requisite, gipay_webhook_outcome
from payments.layerone_client import layerone_map_requisite, layerone_webhook_outcome
from payments.models import (
    GipayPayInSession,
    LayeronePayInSession,
    PatriotpayPayInSession,
    PayInTraceLog,
    PayplatPayInSession,
    PlutusPayInSession,
)
from payments.patriotpay_client import patriotpay_map_requisite, patriotpay_webhook_outcome
from payments.plutus_client import plutus_map_requisite, plutus_webhook_outcome
from payments.payin_trace import Direction
from payments.payplat_client import payplat_map_requisite, payplat_webhook_outcome
from payments.psp_payin import requisite_payload_has_fields

DAYS = float(os.environ.get("DAYS", "2"))
LIMIT = int(os.environ.get("LIMIT", "25"))
SINCE = timezone.now() - timedelta(days=DAYS)


def _status(pay_in) -> str:
    return pay_in.status.name if pay_in and pay_in.status else "-"


def _order_status(pay_in) -> str:
    order = pay_in.order if pay_in else None
    return order.status.name if order and order.status else "-"


def _req_ok(mapper, session) -> bool:
    return requisite_payload_has_fields(mapper(session.create_response or {}))


def _summarize(label, qs, mapper, outcome_fn, webhook_direction):
    rows = list(qs.filter(created_at__gte=SINCE).select_related("pay_in", "pay_in__order").order_by("-created_at")[:LIMIT])
    print(f"\n=== {label} last {len(rows)} (since {SINCE:%Y-%m-%d %H:%M} UTC, cap {LIMIT}) ===")
    if not rows:
        print("  (none)")
        return
    issued = success = webhook_rows = ignored_like = 0
    pay_statuses = Counter()
    last_states = Counter()
    for session in rows:
        pay_in = session.pay_in
        has_req = _req_ok(mapper, session)
        is_ok = _status(pay_in) == "Success"
        issued += int(has_req)
        success += int(is_ok)
        pay_statuses[_status(pay_in)] += 1
        last_state = (getattr(session, "last_notified_state", None) or getattr(session, "last_notified_status", None) or "-")
        last_states[last_state or "-"] += 1
        payload = session.last_webhook_payload or {}
        if payload:
            webhook_rows += 1
            if outcome_fn(payload) is None:
                ignored_like += 1
        print(
            f"  pay_in={session.pay_in_id} req={int(has_req)} "
            f"payin={_status(pay_in)} order={_order_status(pay_in)} "
            f"last_state={last_state or '-'} webhook={int(bool(payload))}"
        )
        if payload and not is_ok:
            print(
                f"    webhook_keys={list(payload)[:12]} "
                f"outcome={outcome_fn(payload)}"
            )
    traces = PayInTraceLog.objects.filter(direction=webhook_direction, created_at__gte=SINCE).count()
    print(
        f"  issued={issued}/{len(rows)} success={success}/{len(rows)} "
        f"sessions_with_webhook_payload={webhook_rows} "
        f"payload_would_ignore={ignored_like} traces[{webhook_direction}]={traces}"
    )
    print(f"  payin_status={dict(pay_statuses)}")
    print(f"  last_notified={dict(last_states)}")


print(f"PSP conversion diagnose DAYS={DAYS}")
_summarize("PayPlat", PayplatPayInSession.objects, payplat_map_requisite, payplat_webhook_outcome, Direction.PAYPLAT_WEBHOOK)
_summarize("GiPay", GipayPayInSession.objects, gipay_map_requisite, gipay_webhook_outcome, Direction.GIPAY_WEBHOOK)
_summarize("LayerOne", LayeronePayInSession.objects, layerone_map_requisite, layerone_webhook_outcome, Direction.LAYERONE_WEBHOOK)
_summarize("Plutus", PlutusPayInSession.objects, plutus_map_requisite, plutus_webhook_outcome, Direction.PLUTUS_WEBHOOK)
_summarize("PatriotPay", PatriotpayPayInSession.objects, patriotpay_map_requisite, patriotpay_webhook_outcome, Direction.PATRIOTPAY_WEBHOOK)

print("\nКак читать:")
print("  issued>0 и success=0 + webhook=0 → колбек до нас не доходит (URL/подпись/ЛК провайдера).")
print("  issued>0 и success=0 + webhook=1 + outcome=None → статус колбека мы раньше игнорировали.")
print("  issued>0 и success=0 + last_state empty → реквизит выдан, оплаты/колбека не было.")
print("  PayPlat success>0 при тех же DAYS — эталон рабочего колбека.")
