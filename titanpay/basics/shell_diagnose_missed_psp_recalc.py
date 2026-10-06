"""
Диагностика: провайдер прислал колбек с новой суммой, а перерасчёт не применился.

Только чтение. APPLY нет.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_diagnose_missed_psp_recalc.py
"""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from zoneinfo import ZoneInfo

from django.db.models import Q

from appeals.id_resolve import resolve_pay_in_from_message
from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import (
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)
from trade.models import InOrder

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# (merchant_order_or_hint, expected_amount, uuid)
CASES = [
    ("23821595903", "10000.04", "313ff253-f16c-46cc-a35a-452a53caa664"),
    ("23827027379", "25002.94", "d28a17b7-ef74-499b-92e1-3971b48ad25d"),
    ("23828758673", "501.06", "e93e57e7-2785-43ed-a844-a7e9277cba6f"),
    ("23829018219", "5001.5", "4f687e57-886c-4c78-a798-d1b5581abaab"),
    ("23799841571", "17001.3", "10fe928c-f936-4bdd-9bce-00208e90c93d"),
    ("23796579497", "90004", "73071ff3-4d0d-43bd-b2a1-1503389a2711"),
    ("23491821427", "5002.54", "9c839891-a065-4aa7-b9d2-e2416d9ac6c6"),
    ("ad16c67fe-9cc4-4499-8e5d-c451e9547a0ag", "10", "9d133a64-d172-499f-a600-9b2eb11132e2"),
    ("a0ad2db3e-2b71-46ae-856e-77434ac53c3cg", "12003.67", "ab896cea-c50e-42e8-9517-fca5be2f249d"),
    ("23867114531", "6800.76", "3d181124-e17f-4549-9664-7ed6a83a8ac2"),
    ("23866293285", "5001.5", "d5b7c9f8-d027-4630-abb7-d1c18e6859dd"),
    ("23866395303", "5001.5", "3a27b78e-f7e4-4340-a066-7de850ec6e0b"),
    ("23866234767", "5001.5", "737c28e2-daf1-49ea-8fe1-3b63c3772b8b"),
    ("23867398013", "29000.02", "2b14b486-e6ed-436f-b321-e52a471116ef"),
    ("23867073917", "5001.5", "0ea5a41d-6687-4ea5-8620-205714616cec"),
    ("23866416213", "5001.5", "0fcc97d8-8f2e-41e9-83f3-7012aa9049b9"),
]

SESSION_ATTRS = (
    "payplat_session",
    "gipay_session",
    "layerone_session",
    "patriotpay_session",
    "botonpay_session",
    "bitzone_session",
    "fairpay_session",
    "visionx_session",
    "expayone_session",
    "protocol_session",
    "syndicate_session",
    "plutus_session",
    "concored_session",
    "paymap_session",
    "playments_session",
    "astrum_session",
)

# success-ветка до сих пор early-return на Completed (повторный колбек глотается)
EARLY_RETURN_PSPS = frozenset({
    "layerone", "protocol", "plutus", "botonpay", "paymap", "concored",
    "playments", "fairpay", "expayone", "astrum", "syndicate",
})


def money(v):
    if v is None:
        return None
    return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)


def parse_amt(raw: str) -> Decimal:
    return money(str(raw).replace(" ", "").replace(",", ".").replace("$", ""))


def when(dt):
    return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S") if dt else "-"


def payload_dict(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def find_pay_in(hint: str, uid: str):
    for q in (uid, hint):
        q = (q or "").strip()
        if not q:
            continue
        m = UUID_RE.search(q)
        if m:
            try:
                u = uuid.UUID(m.group(0))
            except ValueError:
                u = None
            if u:
                pi = PayIn.objects.filter(pk=u).select_related(
                    "status", "merchant__user", "payment_system", "order__status"
                ).first()
                if pi:
                    return pi
                order = InOrder.objects.filter(pk=u).first()
                if order:
                    pi = PayIn.objects.filter(order=order).select_related(
                        "status", "merchant__user", "payment_system", "order__status"
                    ).first()
                    if pi:
                        return pi
        pi = PayIn.objects.filter(merchant_order_id=q).select_related(
            "status", "merchant__user", "payment_system", "order__status"
        ).first()
        if pi:
            return pi
        resolved = resolve_pay_in_from_message(q)
        if resolved and getattr(resolved, "pay_in", None):
            return PayIn.objects.filter(pk=resolved.pay_in.pk).select_related(
                "status", "merchant__user", "payment_system", "order__status"
            ).first()
    return None


def sessions_for(pay_in):
    found = []
    for attr in SESSION_ATTRS:
        sess = getattr(pay_in, attr, None)
        if sess is None:
            continue
        psp = attr.replace("_session", "")
        found.append((psp, sess))
    return found


def webhook_bodies(pay_in, sessions):
    bodies = []
    for psp, sess in sessions:
        last = payload_dict(getattr(sess, "last_webhook_payload", None))
        if last:
            bodies.append(("session.last", psp, last, getattr(sess, "updated_at", None)))
    traces = PayInTraceLog.objects.filter(
        pay_in=pay_in,
        direction__endswith="_webhook",
    ).order_by("-created_at")[:40]
    for t in traces:
        body = payload_dict(t.body)
        if not body:
            continue
        dir_name = (t.direction or "").replace("_webhook", "")
        bodies.append((f"trace.{t.direction}", dir_name, body, t.created_at))
    return bodies


def diagnose_body(order, expected, body):
    paid = parse_psp_webhook_paid_amount(body)
    paid_q = money(paid) if paid is not None else None
    allow = psp_success_webhook_allows_completed_recalc(body)
    cur = money(order.amount) if order else None
    exp = money(expected)
    reason = []
    if paid_q is None:
        reason.append("парсер не вытащил сумму из колбека")
    elif cur is not None and paid_q == cur:
        reason.append("в колбеке та же сумма, что уже на заявке")
    elif exp is not None and paid_q != exp:
        reason.append(f"сумма в колбеке {paid_q} != ожидаемой {exp}")
    if not allow:
        reason.append("провайдер не в whitelist completed-recalc")
    if order and order.status and order.status.name != "Completed":
        reason.append(f"статус заявки {order.status.name}, не Completed")
    if (
        order
        and order.status
        and order.status.name == "Completed"
        and allow
        and paid_q
        and cur
        and paid_q != cur
    ):
        reason.append("СЕЙЧАС код применил бы recalc")
    return paid_q, allow, "; ".join(reason) or "ok"


def run():
    print("missed PSP recalc diagnose  (read-only)\n")
    for hint, exp_raw, uid in CASES:
        expected = parse_amt(exp_raw)
        print("=" * 88)
        print(f"hint={hint}  uuid={uid}  expected={expected}")
        pay_in = find_pay_in(hint, uid)
        if pay_in is None:
            print("  NOT FOUND")
            continue
        order = pay_in.order
        merch = pay_in.merchant.user.username if pay_in.merchant_id else "-"
        print(
            f"  merchant={merch}  ps={getattr(pay_in.payment_system, 'name', None)}  "
            f"pay_in={pay_in.id}  payin_status={pay_in.status.name if pay_in.status else '-'}"
        )
        print(f"  merchant_order_id={pay_in.merchant_order_id}")
        if order is None:
            print("  NO InOrder")
            continue
        print(
            f"  order={order.id}  order_status={order.status.name if order.status else '-'}  "
            f"amount={order.amount}  usd={order.usd_amount}  "
            f"recalculated={order.recalculated}  recalc_amount={order.recalculated_amount}"
        )
        print(f"  created={when(order.creation_date)}  completed={when(order.completion_date)}")
        cur = money(order.amount)
        if cur == expected:
            print("  MATCH: текущая сумма уже равна ожидаемой")
        else:
            print(f"  GAP: current={cur}  expected={expected}  delta={money(expected - cur)}")

        sessions = sessions_for(pay_in)
        if not sessions:
            print("  PSP session: нет")
        for psp, sess in sessions:
            print(
                f"  PSP {psp}: last_state={getattr(sess, 'last_notified_state', None) or getattr(sess, 'last_notified_status', None)}  "
                f"updated={when(getattr(sess, 'updated_at', None))}"
            )
            if psp in EARLY_RETURN_PSPS:
                print("    VIEW: повторный success на Completed до сих пор early-return (колбек глотается)")

        bodies = webhook_bodies(pay_in, sessions)
        if not bodies:
            print("  CALLBACKS: нет last_webhook и нет *_webhook в trace — провайдер сумму не присылал (или мы не записали)")
            continue
        best = None
        print("  CALLBACKS:")
        for src, psp, body, ts in bodies:
            paid_q, allow, why = diagnose_body(order, expected, body)
            keys = ",".join(list(body.keys())[:12])
            inv = body.get("invoice") if isinstance(body.get("invoice"), dict) else {}
            extra = ""
            if inv:
                extra = f" invoice.status={inv.get('status')} invoice.amount={inv.get('amount')} sum={inv.get('sum')}"
            print(
                f"    {when(ts)}  {src:28}  parsed={paid_q}  allow_recalc={int(allow)}  {why}"
            )
            print(f"      keys={keys}{extra}")
            if paid_q is None:
                continue
            score = 0
            if paid_q == expected:
                score += 3
            if paid_q != cur:
                score += 1
            if allow:
                score += 1
            if best is None or score > best[0]:
                best = (score, paid_q, allow, why, psp)

        if best is None:
            print("  VERDICT: колбеки есть, сумму распарсить не смогли")
        elif best[1] == expected and best[1] != cur:
            if best[2]:
                print(
                    f"  VERDICT: провайдер прислал {best[1]}, мы не применили "
                    f"(whitelist ок — скорее глотание Completed / баг парсера в момент колбека). psp={best[4]}"
                )
            else:
                print(
                    f"  VERDICT: провайдер прислал {best[1]}, мы не применили: "
                    f"{best[4]} не в whitelist completed-recalc (или early-return во view)"
                )
        elif best[1] == cur:
            print(f"  VERDICT: в сохранённых колбеках нет суммы {expected}, только {best[1]} (=текущая)")
        else:
            print(f"  VERDICT: лучший parsed={best[1]} expected={expected} current={cur} | {best[3]}")


run()
