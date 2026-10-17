"""
PayPlat: аудит заявок перед корректировкой сумм по чекам. НИЧЕГО НЕ МЕНЯЕТ.

Показывает по каждому merchant_order_id текущее состояние в нашей системе и,
если передан список корректных сумм, — дельту и её USDT-эквивалент.

Курс на заявке не хранится, поэтому «исторический» курс восстанавливается как
amount / usd_amount. Он важен: apply_psp_completed_recalc() считает новый
usd_amount по ТЕКУЩЕМУ курсу payment_system, и при сдвиге курса USDT-плечо
уедет сильнее, чем изменилась сумма в KZT.

У melbet на C2CKZT расчёты в тенге (uses_melbet_kzt_settlement): плечо мерчанта
идёт blockchain → balance_kzt и от курса не зависит вовсе, а от курса зависят
только списание с payplat1, trader_fee и доля тимлида. Поэтому дельты по двум
плечам считаются и показываются отдельно.

Ещё melbet-специфика: amount probe при неудачном роутинге создаёт заявку на
близкую сумму (±20/50/100 от запрошенной). Если сумма подменялась, скрипт
покажет строку PROBE — тогда «корректная сумма по чеку» может быть просто
изначальным запросом мерчанта.

Формат списка сумм — как присылает сапорт, одной строкой или в столбик:
  23395938275 - 5000,85 23396613645 - 5000,85 23395921711 - 12504,43
Десятичный разделитель — запятая или точка. Если на один заказ пришло два чека
(«1 чек X 2 чек Y»), заявка попадает в НЕОДНОЗНАЧНЫЕ и не корректируется.

Запуск (только текущее состояние заявок из DEFAULT_ORDER_IDS):
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py

Со списком сумм — аудит идёт ровно по тем заявкам, что есть в списке:
  docker compose cp /root/amounts.txt app:/tmp/amounts.txt
  docker compose exec -T -e AMOUNTS_FILE=/tmp/amounts.txt app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py

Либо строкой:
  docker compose exec -T -e AMOUNTS="23395587903 - 5004,50 23395312345 - 7010" app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_audit.py
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from merchant.kzt_settlement import merchant_available_balance, uses_melbet_kzt_settlement
from payments.models import PayIn, PayInTraceLog, PayplatPayInSession
from payments.payplat_client import payplat_webhook_paid_amount
from trade.models import InOrder

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

# Первый список от мерчанта (34 заявки). Используется, если суммы не переданы.
DEFAULT_ORDER_IDS = [
    "23517063981", "23517072909", "23517062475", "23515799613", "23516076235",
    "23515798585", "23515418873", "23513810681", "23508459681", "23494104767",
    "23438470973", "23437770037", "23436840879", "23436855361", "23436488101",
    "23425338389", "23420413807", "23419938051", "23418834363", "23416457895",
    "23415840161", "23422395657", "23436258091", "23436067911", "23435931573",
    "23436254375", "23395231945", "23395909453", "23396245871", "23395929441",
    "23395535749", "23395312345", "23395749667", "23395587903",
]

ID_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
NUM_RE = re.compile(r"\d{1,9}(?:[.,]\d{1,2})?")
RECEIPT_IDX_RE = re.compile(r"\b\d\s*чек\b", re.IGNORECASE)


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def load_corrected() -> tuple[dict[str, Decimal], list[str]]:
    """Разбор списка сапорта: id, затем ровно одна сумма до следующего id."""
    path = (os.environ.get("AMOUNTS_FILE") or "").strip()
    if path:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = os.environ.get("AMOUNTS") or ""

    text = re.sub(r"\s+", " ", raw)
    matches = list(ID_RE.finditer(text))
    out: dict[str, Decimal] = {}
    ambiguous: list[str] = []

    for idx, match in enumerate(matches):
        order_id = match.group(0)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        segment = RECEIPT_IDX_RE.sub(" ", text[match.end():end])
        values = [q2(n.replace(",", ".")) for n in NUM_RE.findall(segment)]
        if len(values) == 1 and values[0] > 0:
            out[order_id] = values[0]
        else:
            ambiguous.append(f"{order_id}: {text[match.end():end].strip()}")
    return out, ambiguous


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


def amount_probe(order_id: str) -> tuple[Decimal, Decimal] | None:
    """melbet probe: при неудачном роутинге заявка создаётся на близкую сумму (±20/50/100)."""
    log = (
        PayInTraceLog.objects.filter(merchant_order_id=order_id, direction="routing", body__amount_probe=True)
        .order_by("-created_at")
        .first()
    )
    if log is None:
        return None
    body = log.body or {}
    requested, allocated = body.get("requested_amount"), body.get("allocated_amount")
    if requested is None or allocated is None:
        return None
    return q2(requested), q2(allocated)


def describe(order: InOrder) -> dict:
    solution = order.solution
    ps = solution.payment_system
    group = order.payment_details.group if order.payment_details_id else None
    trader = group.trader if group else None
    team = trader.team if trader else None
    teamlead = team.teamlead if team else None

    usd = Decimal(str(order.usd_amount or 0))
    amount = Decimal(str(order.amount or 0))
    fee = Decimal(str(order.merchant_fee or 0))
    hist_rate = (amount / usd).quantize(Q4, rounding=ROUND_HALF_UP) if usd > 0 else None

    return {
        "status": order.status.name if order.status_id else "-",
        "merchant": solution.merchant.user.username,
        "merchant_obj": solution.merchant,
        "kzt_settlement": uses_melbet_kzt_settlement(solution.merchant, ps),
        "credit": (amount - fee).quantize(Q2),
        "fee_pct": (fee / amount * Decimal(100)).quantize(Q2) if amount > 0 else Decimal(0),
        "ps": ps.name,
        "currency": ps.currency.symbol if ps.currency_id else "?",
        "cur_rate": Decimal(str(ps.get_rate() or 0)),
        "amount": amount,
        "usd": usd,
        "hist_rate": hist_rate,
        "merchant_fee": fee,
        "trader_fee": Decimal(str(order.trader_fee or 0)),
        "trader": trader.user.username if trader else "-",
        "teamlead": teamlead.user.username if teamlead and teamlead.user_id else "-",
        "tl_pct": team.teamlead_percentage if team else None,
        "completed": order.completion_date,
        "recalculated": order.recalculated,
        "probe": amount_probe(order.merchant_order_id),
    }


def run() -> None:
    corrected, ambiguous = load_corrected()
    order_ids = list(corrected.keys()) if corrected else list(DEFAULT_ORDER_IDS)
    print(f"заявок к проверке: {len(order_ids)}   сумм разобрано: {len(corrected)}")
    if ambiguous:
        print(f"НЕОДНОЗНАЧНЫЕ (не корректировать, разобрать руками): {len(ambiguous)}")
        for line in ambiguous:
            print(f"  {line}")
    if corrected:
        overlap = sorted(set(DEFAULT_ORDER_IDS) & set(corrected))
        print(f"пересечение с первым списком из 34: {len(overlap)}"
              + (f" → {', '.join(overlap)}" if overlap else ""))
    print()

    rows: list[tuple[str, InOrder, dict, Decimal | None]] = []
    missing: list[str] = []
    dupes: list[str] = []

    for oid in order_ids:
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
        settlement = f"KZT (blockchain → balance_kzt), зачислено {d['credit']}" if d["kzt_settlement"] else "USDT"
        print(f"{oid}  [{d['status']}]  {d['merchant']}  {d['ps']}/{d['currency']}")
        print(f"   сейчас:   amount={d['amount']}  usd={d['usd']}  курс(ист.)={d['hist_rate']}  курс(тек.)={d['cur_rate']}")
        print(f"   комиссии: merchant_fee={d['merchant_fee']} ({d['fee_pct']}%)  trader_fee={d['trader_fee']}  "
              f"trader={d['trader']}  teamlead={d['teamlead']} ({d['tl_pct']}%)")
        print(f"   расчёт:   {settlement}")
        if d["probe"] is not None:
            requested, allocated = d["probe"]
            print(f"   PROBE:    мерчант просил {requested}, создали на {allocated}")
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
                  f"(USDT с payplat1 по ист. курсу {usd_hist} / по текущему {usd_cur})")
            if d["kzt_settlement"]:
                new_fee = q2(new_amount * d["fee_pct"] / Decimal(100))
                print(f"   мерчанту: {q2(new_amount - new_fee - d['credit']):+} KZT "
                      f"(новая комиссия {new_fee})")
        print()

    print("=== СВОДКА ===")
    print(f"найдено:      {len(rows)}")
    if missing:
        print(f"НЕ НАЙДЕНО:   {len(missing)} → {', '.join(missing)}")
    if dupes:
        print(f"ДУБЛИ id:     {len(dupes)} → {', '.join(dupes)}")

    from collections import Counter

    status_counts = Counter(d["status"] for _, _, d, _ in rows)
    trader_counts = Counter(d["trader"] for _, _, d, _ in rows)
    print(
        "статусы:      "
        + (", ".join(f"{name}={cnt}" for name, cnt in sorted(status_counts.items())) or "-")
    )
    print(f"мерчанты:     {', '.join(sorted({d['merchant'] for _, _, d, _ in rows})) or '-'}")
    print(
        "трейдеры:     "
        + (", ".join(f"{name}={cnt}" for name, cnt in sorted(trader_counts.items())) or "-")
    )
    print(f"методы:       {', '.join(sorted({d['ps'] + '/' + d['currency'] for _, _, d, _ in rows})) or '-'}")

    already = [oid for oid, _, d, _ in rows if d["recalculated"]]
    print(f"уже recalculated: {len(already)}" + (f" → {', '.join(already)}" if already else ""))

    probed = [(oid, d["probe"]) for oid, _, d, _ in rows if d["probe"] is not None]
    if probed:
        print(f"PROBE (сумма менялась при создании): {len(probed)}")
        for oid, (requested, allocated) in probed:
            print(f"  {oid}: просили {requested} → создали {allocated}")

    rates = [d["hist_rate"] for _, _, d, _ in rows if d["hist_rate"]]
    if rates:
        print(f"ист. курс:    min={min(rates)}  max={max(rates)}")
    print(f"тек. курс:    {', '.join(str(r) for r in sorted({d['cur_rate'] for _, _, d, _ in rows})) or '-'}")
    print(f"сумма сейчас: {q2(sum((d['amount'] for _, _, d, _ in rows), Decimal('0')))}")

    kzt_rows = [d for _, _, d, _ in rows if d["kzt_settlement"]]
    if kzt_rows:
        merchant = kzt_rows[0]["merchant_obj"]
        balance = merchant_available_balance(merchant)
        print(f"balance_kzt {merchant.user.username}: {q2(balance.amount)} KZT "
              f"(уход в минус разрешён, balance_allows_negative_ledger)")

    priced = [(d, new) for _, _, d, new in rows if new is not None]
    if not priced:
        return

    total_new = sum((new for _, new in priced), Decimal("0"))
    total_delta = q2(total_new - sum((d["amount"] for d, _ in priced), Decimal("0")))
    usd_hist = sum(
        ((new - d["amount"]) / d["hist_rate"] for d, new in priced if d["hist_rate"]),
        Decimal("0"),
    )
    credit_delta = sum(
        (new - q2(new * d["fee_pct"] / Decimal(100)) - d["credit"] for d, new in priced),
        Decimal("0"),
    )
    up = sum(1 for d, new in priced if new > d["amount"])
    down = sum(1 for d, new in priced if new < d["amount"])
    same = sum(1 for d, new in priced if new == d["amount"])

    print(f"сумма по чекам: {q2(total_new)}  (сопоставлено {len(priced)} из {len(rows)})")
    print(f"ИТОГО ДЕЛЬТА:   {total_delta} KZT   вверх={up}  вниз={down}  без изменений={same}")
    print(f"  плечо payplat1: {q2(usd_hist)} USDT по историческим курсам")
    print(f"  плечо мерчанта: {q2(credit_delta)} KZT (за вычетом комиссии)")

    biggest = sorted(priced, key=lambda pair: abs(pair[1] - pair[0]["amount"]), reverse=True)[:10]
    print("наибольшие дельты:")
    for d, new in biggest:
        print(f"  {d['amount']} → {new}  ({q2(new - d['amount']):+} KZT)")


run()
