"""
Вчерашние колбеки PatriotPay / VisionX: какие статусы/суммы приходили и почему
перерасчёт не применился.

Только чтение.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_analyze_patriot_visionx_recalc_cbs.py

  docker compose exec -T -e DATE=2026-10-06 app python manage.py shell \\
    < titanpay/basics/shell_analyze_patriot_visionx_recalc_cbs.py
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayInTraceLog
from payments.psp_payin import (
    parse_psp_webhook_paid_amount,
    psp_success_webhook_allows_completed_recalc,
)

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
LIMIT_DETAIL = int(os.environ.get("LIMIT") or "40")


def money(v):
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(Q2, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


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


def when(dt):
    if not dt:
        return "-"
    if getattr(dt, "tzinfo", None):
        return dt.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def day_bounds():
    raw = (os.environ.get("DATE") or "").strip()
    now = timezone.now().astimezone(MSK)
    if raw:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    else:
        day = (now - timedelta(days=1)).date()
    start = datetime.combine(day, time.min, tzinfo=MSK)
    end = start + timedelta(days=1)
    return day, start, end


def invoice_of(body: dict) -> dict:
    inv = body.get("invoice")
    return inv if isinstance(inv, dict) else {}


def classify_event(body: dict, order_amount, order_status: str, recalculated: bool):
    inv = invoice_of(body)
    st = (inv.get("status") or body.get("status") or "-")
    paid = money(parse_psp_webhook_paid_amount(body))
    try:
        allow = bool(psp_success_webhook_allows_completed_recalc(body))
    except Exception as exc:  # noqa: BLE001
        allow = False
        allow_err = f"{type(exc).__name__}: {exc}"
    else:
        allow_err = ""
    cur = money(order_amount)
    reason = []
    if paid is None:
        reason.append("сумму не распарсили")
    elif cur is not None and paid == cur:
        reason.append("сумма = текущая на заявке")
    elif cur is not None and paid != cur:
        reason.append(f"сумма {paid} != текущая {cur}")
    if not allow:
        reason.append("не success-recalc (dispute/new/canceled или whitelist)")
    if order_status == "Completed" and allow and paid and cur and paid != cur:
        if recalculated and cur == paid:
            reason.append("уже применён")
        else:
            reason.append("СЕЙЧАС код применил бы recalc")
    if allow_err:
        reason.append(allow_err)
    return str(st), paid, allow, "; ".join(reason) or "ok"


def dump_sum(inv: dict) -> str:
    if not inv:
        return ""
    return (
        f" invoice.status={inv.get('status')} amount={inv.get('amount')} "
        f"sum={inv.get('sum')}"
    )


def analyze(label: str, direction: str, start, end):
    print("=" * 100)
    print(f"{label}  direction={direction}")
    traces = list(
        PayInTraceLog.objects.filter(direction=direction, created_at__gte=start, created_at__lt=end)
        .select_related(
            "pay_in",
            "pay_in__status",
            "pay_in__order",
            "pay_in__order__status",
            "pay_in__merchant__user",
        )
        .order_by("created_at")
    )
    print(f"  webhook traces за день: {len(traces)}")
    if not traces:
        print("  Нет записанных колбеков — либо провайдер не слал, либо 404/403 до trace (unknown_order / bad token).")
        print("  Смотри docker compose logs app | grep -i patriotpay\\|visionx  за вчера.")
        return

    status_hist = Counter()
    by_payin = defaultdict(list)
    no_payin = 0
    for t in traces:
        body = payload_dict(t.body)
        inv = invoice_of(body)
        st = str(inv.get("status") or body.get("status") or "-")
        status_hist[st] += 1
        pay_in = t.pay_in
        if pay_in is None:
            no_payin += 1
            continue
        order = pay_in.order
        ost = order.status.name if order and order.status else "-"
        recalc = bool(order.recalculated) if order else False
        st2, paid, allow, why = classify_event(
            body, order.amount if order else None, ost, recalc
        )
        by_payin[str(pay_in.id)].append(
            {
                "ts": t.created_at,
                "status": st2,
                "paid": paid,
                "allow": allow,
                "why": why,
                "note": t.note,
                "body": body,
                "pay_in": pay_in,
                "order": order,
            }
        )

    print(f"  invoice.status: {dict(status_hist)}")
    print(f"  traces без pay_in: {no_payin}")
    print(f"  уникальных PayIn: {len(by_payin)}")

    missed = []
    same_repeat = []
    no_new_amount = []
    applied = []
    for pid, events in by_payin.items():
        pay_in = events[0]["pay_in"]
        order = events[0]["order"]
        success_amts = [e["paid"] for e in events if e["allow"] and e["paid"] is not None]
        uniq = []
        for a in success_amts:
            if a not in uniq:
                uniq.append(a)
        cur = money(order.amount) if order else None
        ost = order.status.name if order and order.status else "-"
        rec = bool(order.recalculated) if order else False
        would = [e for e in events if "СЕЙЧАС код применил бы recalc" in e["why"]]
        if rec:
            applied.append((pid, events, uniq))
        elif would:
            missed.append((pid, events, uniq))
        elif len(uniq) <= 1 and len(success_amts) >= 2:
            same_repeat.append((pid, events, uniq))
        elif ost == "Completed" and success_amts:
            no_new_amount.append((pid, events, uniq))

    print("\n  Итог по заявкам:")
    print(f"    recalc уже стоит на заявке: {len(applied)}")
    print(f"    MISSED — в CB другая сумма, сейчас бы применили: {len(missed)}")
    print(f"    повторный paid с ТОЙ ЖЕ суммой: {len(same_repeat)}")
    print(f"    completed, success CB есть, новой суммы нет: {len(no_new_amount)}")

    def show(title, rows):
        print(f"\n  --- {title} (до {LIMIT_DETAIL}) ---")
        if not rows:
            print("    нет")
            return
        for pid, events, uniq in rows[:LIMIT_DETAIL]:
            pay_in = events[0]["pay_in"]
            order = events[0]["order"]
            merch = pay_in.merchant.user.username if pay_in.merchant_id else "-"
            print(
                f"    {when(events[0]['ts'])}  pay_in={pid}  moid={pay_in.merchant_order_id}  "
                f"merchant={merch}  order={order.status.name if order and order.status else '-'}  "
                f"amount={order.amount if order else '-'}  recalc={getattr(order, 'recalculated', None)}  "
                f"uniq_success_amts={uniq}"
            )
            for e in events:
                inv = invoice_of(e["body"])
                print(
                    f"      {when(e['ts'])}  parsed={e['paid']}  allow={int(e['allow'])}  "
                    f"{e['why']}{dump_sum(inv)}"
                )

    show("MISSED (провайдер прислал другую сумму, мы не применили)", missed)
    show("повторный paid без новой суммы (провайдер не прислал перерасчёт в теле)", same_repeat[:LIMIT_DETAIL])

    # короткие примеры dispute/new — часто сумма та же
    print("\n  --- примеры не-success статусов (первые 8) ---")
    n = 0
    for t in traces:
        body = payload_dict(t.body)
        inv = invoice_of(body)
        st = str(inv.get("status") or "")
        if st.lower() in {"paid", "success", "completed", "finished"}:
            continue
        paid = money(parse_psp_webhook_paid_amount(body))
        print(
            f"    {when(t.created_at)}  pay_in={t.pay_in_id}  status={st}  parsed={paid}{dump_sum(inv)}"
        )
        n += 1
        if n >= 8:
            break
    if n == 0:
        print("    нет")


day, start, end = day_bounds()
print("PatriotPay / VisionX recalc CB analyze  (read-only)")
print(f"  day={day.isoformat()}  {start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} {MSK.key}\n")

analyze("PatriotPay", "patriotpay_webhook", start, end)
analyze("VisionX", "visionx_webhook", start, end)

print("\n" + "=" * 100)
print("Как читать:")
print("  MISSED = в сохранённом paid/success сумма != заявке → это мы не обработали.")
print("  повторный paid с той же суммой = провайдер не прислал новую цифру (спор с тем же sum.amount).")
print("  404 unknown_order в этот скрипт не попадает — ищем в логах контейнера.")
print("APPLY нет.")
