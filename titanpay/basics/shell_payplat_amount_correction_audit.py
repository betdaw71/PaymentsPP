"""
PayPlat: аудит заявок перед корректировкой сумм по чекам. НИЧЕГО НЕ МЕНЯЕТ.

Показывает по каждому merchant_order_id текущее состояние в нашей системе и,
если передан список корректных сумм, — дельту и её USDT-эквивалент.

Курс на заявке не хранится, поэтому «исторический» курс восстанавливается как
amount / usd_amount. Он важен: apply_psp_completed_recalc() считает новый
usd_amount по ТЕКУЩЕМУ курсу payment_system, и при сдвиге курса USDT-плечо
уедет сильнее, чем изменилась сумма в KZT.

Запуск (только просмотр текущего состояния):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py

С корректными суммами из файла (строки вида "23395587903 - 5004"):
  docker compose cp /root/amounts.txt app:/tmp/amounts.txt
  docker compose exec -T -e AMOUNTS_FILE=/tmp/amounts.txt app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py

Либо строкой:
  docker compose exec -T -e AMOUNTS="23395587903=5004,23395312345=7010" app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from payments.models import PayIn, PayplatPayInSession
from payments.payplat_client import payplat_webhook_paid_amount
from trade.models import InOrder

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

ORDER_IDS = [
    "23517063981", "23517072909", "23517062475", "23515799613", "23516076235",
    "23515798585", "23515418873", "23513810681", "23508459681", "23494104767",
    "23438470973", "23437770037", "23436840879", "23436855361", "23436488101",
    "23425338389", "23420413807", "23419938051", "23418834363", "23416457895",
    "23415840161", "23422395657", "23436258091", "23436067911", "23435931573",
    "23436254375", "23395231945", "23395909453", "23396245871", "23395929441",
    "23395535749", "23395312345", "23395749667", "23395587903",
]

LINE_RE = re.compile(r"^\s*(\d+)\s*[-=:,\s]\s*([\d]+(?:[.,]\d+)?)\s*$")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def load_corrected() -> dict[str, Decimal]:
    raw = ""
    path = (os.environ.get("AMOUNTS_FILE") or "").strip()
    if path:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = (os.environ.get("AMOUNTS") or "").strip().replace(",", "\n")

    out: dict[str, Decimal] = {}
    bad: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            bad.append(line.strip())
            continue
        out[m.group(1)] = q2(m.group(2).replace(",", "."))
    if bad:
        print(f"!! не разобраны строки списка сумм ({len(bad)}):")
        for line in bad[:10]:
            print(f"   {line!r}")
    return out


def resolve(order_id: str):
    """PayIn.merchant_order_id уникален; InOrder — нет, поэтому возвращаем все совпадения."""
    pay_ins = list(
        PayIn.objects.filter(merchant_order_id=order_id)
        .select_related("order", "merchant", "merchant__user", "status", "currency", "payment_system")
    )
    if pay_ins:
        return pay_ins
    orders = list(InOrder.objects.filter(merchant_order_id=order_id))
    return [o.pay_in.order_by("-created_at").first() or o for o in orders]


def describe(order: InOrder) -> dict:
    solution = order.solution
    ps = solution.payment_system
    group = order.payment_details.group if order.payment_details_id else None
    trader = group.trader if group else None
    team = trader.team if trader else None
    teamlead = team.teamlead if team else None

    usd = Decimal(str(order.usd_amount or 0))
    amount = Decimal(str(order.amount or 0))
    hist_rate = (amount / usd).quantize(Q4, rounding=ROUND_HALF_UP) if usd > 0 else None

    return {
        "status": order.status.name if order.status_id else "-",
        "merchant": solution.merchant.user.username,
        "ps": ps.name,
        "currency": ps.currency.symbol if ps.currency_id else "?",
        "cur_rate": Decimal(str(ps.get_rate() or 0)),
        "amount": amount,
        "usd": usd,
        "hist_rate": hist_rate,
        "merchant_fee": Decimal(str(order.merchant_fee or 0)),
        "trader_fee": Decimal(str(order.trader_fee or 0)),
        "trader": trader.user.username if trader else "-",
        "teamlead": teamlead.user.username if teamlead and teamlead.user_id else "-",
        "tl_pct": team.teamlead_percentage if team else None,
        "completed": order.completion_date,
        "recalculated": order.recalculated,
    }


def run() -> None:
    corrected = load_corrected()
    print(f"заявок в списке: {len(ORDER_IDS)}   корректных сумм передано: {len(corrected)}")
    print()

    rows: list[tuple[str, InOrder, dict, Decimal | None]] = []
    missing: list[str] = []
    dupes: list[str] = []

    for oid in ORDER_IDS:
        found = [x for x in resolve(oid) if x is not None]
        if not found:
            missing.append(oid)
            continue
        if len(found) > 1:
            dupes.append(oid)
        obj = found[0]
        order = obj.order if isinstance(obj, PayIn) else obj
        if order is None:
            missing.append(oid)
            continue
        rows.append((oid, order, describe(order), corrected.get(oid)))

    for oid, order, d, new_amount in rows:
        head = f"{oid}  [{d['status']}]  {d['merchant']}  {d['ps']}/{d['currency']}"
        print(head)
        print(f"   сейчас:   amount={d['amount']}  usd={d['usd']}  курс(ист.)={d['hist_rate']}  курс(тек.)={d['cur_rate']}")
        print(f"   комиссии: merchant_fee={d['merchant_fee']}  trader_fee={d['trader_fee']}  "
              f"trader={d['trader']}  teamlead={d['teamlead']} ({d['tl_pct']}%)")
        completed = d["completed"].astimezone(MSK).strftime("%Y-%m-%d %H:%M") if d["completed"] else "-"
        print(f"   completed={completed}  recalculated={d['recalculated']}")

        session = PayplatPayInSession.objects.filter(pay_in__order=order).first()
        if session:
            quote = payplat_webhook_paid_amount(session.last_webhook_payload or session.create_response or {})
            print(f"   payplat:  deal={session.provider_order_id or '-'}  quote_amount={quote}")
        else:
            print("   payplat:  сессии нет")

        if new_amount is not None:
            delta = q2(new_amount - d["amount"])
            usd_hist = q2(delta / d["hist_rate"]) if d["hist_rate"] else None
            usd_cur = q2(delta / d["cur_rate"]) if d["cur_rate"] else None
            print(f"   ПО ЧЕКУ:  {new_amount}   дельта={delta}  "
                  f"(USDT по ист. курсу {usd_hist} / по текущему {usd_cur})")
        print()

    print("=== СВОДКА ===")
    print(f"найдено:      {len(rows)}")
    if missing:
        print(f"НЕ НАЙДЕНО:   {len(missing)} → {', '.join(missing)}")
    if dupes:
        print(f"ДУБЛИ id:     {len(dupes)} → {', '.join(dupes)}")

    statuses = sorted({d["status"] for _, _, d, _ in rows})
    print(f"статусы:      {', '.join(statuses) or '-'}")
    print(f"мерчанты:     {', '.join(sorted({d['merchant'] for _, _, d, _ in rows})) or '-'}")
    print(f"трейдеры:     {', '.join(sorted({d['trader'] for _, _, d, _ in rows})) or '-'}")
    print(f"методы:       {', '.join(sorted({d['ps'] + '/' + d['currency'] for _, _, d, _ in rows})) or '-'}")
    print(f"уже recalculated: {sum(1 for _, _, d, _ in rows if d['recalculated'])}")

    rates = [d["hist_rate"] for _, _, d, _ in rows if d["hist_rate"]]
    if rates:
        print(f"ист. курс:    min={min(rates)}  max={max(rates)}")
    cur_rates = sorted({d["cur_rate"] for _, _, d, _ in rows})
    print(f"тек. курс:    {', '.join(str(r) for r in cur_rates) or '-'}")

    total_now = sum((d["amount"] for _, _, d, _ in rows), Decimal("0"))
    print(f"сумма сейчас: {q2(total_now)}")

    priced = [(d, new) for _, _, d, new in rows if new is not None]
    if priced:
        total_new = sum((new for _, new in priced), Decimal("0"))
        total_delta = q2(total_new - sum((d["amount"] for d, _ in priced), Decimal("0")))
        usd_hist = sum(
            ((new - d["amount"]) / d["hist_rate"] for d, new in priced if d["hist_rate"]),
            Decimal("0"),
        )
        up = sum(1 for d, new in priced if new > d["amount"])
        down = sum(1 for d, new in priced if new < d["amount"])
        same = sum(1 for d, new in priced if new == d["amount"])
        print(f"сумма по чекам: {q2(total_new)}  (передано {len(priced)} из {len(rows)})")
        print(f"ИТОГО ДЕЛЬТА:   {total_delta}  ≈ {q2(usd_hist)} USDT по историческим курсам")
        print(f"из них вверх={up}  вниз={down}  без изменений={same}")
        if len(priced) != len(rows):
            no_price = [oid for oid, _, _, new in rows if new is None]
            print(f"без корректной суммы: {', '.join(no_price)}")


run()
