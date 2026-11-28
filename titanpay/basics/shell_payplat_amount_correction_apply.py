"""
PayPlat/PSP: план и (опционально) применение корректировок сумм по чекам.

По умолчанию DRY_RUN=1 — только план, деньги не двигает.
APPLY=1 — применяет ТОЛЬКО Completed (через apply_psp_completed_recalc).
Остальные статусы (Arbitrage / Expired / Money sent by user) всегда только в плане:
их надо закрывать отдельно (complete_from_psp_success / арбитраж).

Важно про курс:
  apply_psp_completed_recalc считает USDT по ТЕКУЩЕМУ курсу payment_system.
  Плечо melbet KZT (blockchain → balance_kzt) от курса не зависит.
  Плечо PSP-трейдера (payplat1 и т.п.) — зависит; при сдвиге курса USDT-дельта
  уедет относительно «исторической» из аудита.

Фильтры env:
  AMOUNTS_FILE / AMOUNTS — список сапорта (как в audit)
  DRY_RUN=1 (default) | APPLY=1
  ONLY_STATUS=Completed (default для APPLY; для плана можно ALL)
  ONLY_TRADER=payplat1 (опционально)
  SKIP_RECALCULATED=1 (default)
  MAX_ABS_DELTA=20000 — пропуск слишком больших |дельт| (0 = без лимита)
  INCLUDE_SAME=0 — не трогать заявки, где сумма уже равна чеку

Запуск плана:
  docker compose cp /root/amounts_2026-09-15.txt app:/tmp/amounts.txt
  docker compose exec -T -e AMOUNTS_FILE=/tmp/amounts.txt app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_apply.py

Применить только Completed (после ревью плана):
  docker compose exec -T \\
    -e AMOUNTS_FILE=/tmp/amounts.txt -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_payplat_amount_correction_apply.py
"""
from __future__ import annotations

import os
import re
import traceback
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from payments.models import PayIn
from trade.models import InOrder

Q2 = Decimal("0.01")
ID_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
NUM_RE = re.compile(r"\d{1,9}(?:[.,]\d{1,2})?")
RECEIPT_IDX_RE = re.compile(r"\b\d\s*чек\b", re.IGNORECASE)


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def load_corrected() -> tuple[dict[str, Decimal], list[str]]:
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


def resolve_order(order_id: str) -> InOrder | None:
    pay_in = (
        PayIn.objects.filter(merchant_order_id=order_id)
        .select_related(
            "order",
            "order__status",
            "order__solution__merchant__user",
            "order__solution__payment_system",
            "order__payment_details__group__trader__user",
        )
        .order_by("-created_at")
        .first()
    )
    if pay_in is not None and pay_in.order_id:
        return pay_in.order
    return (
        InOrder.objects.filter(merchant_order_id=order_id)
        .select_related(
            "status",
            "solution__merchant__user",
            "solution__payment_system",
            "payment_details__group__trader__user",
        )
        .order_by("-creation_date")
        .first()
    )


def apply_path_for(status: str) -> str:
    if status == "Completed":
        return "apply_psp_completed_recalc"
    if status in {"Expired", "Cancelled"}:
        return "complete_from_psp_success (paid + complete)"
    if status in {"Arbitrage", "Money sent by user", "New"}:
        return "complete_from_psp_success / recalculate"
    if status == "Recalculation":
        return "support_recalculate"
    return "MANUAL"


def run() -> None:
    corrected, ambiguous = load_corrected()
    if not corrected and not ambiguous:
        print("ERROR: передайте AMOUNTS_FILE или AMOUNTS")
        return

    apply = env_flag("APPLY", False)
    dry_run = not apply
    only_status = (os.environ.get("ONLY_STATUS") or ("Completed" if apply else "ALL")).strip()
    only_trader = (os.environ.get("ONLY_TRADER") or "").strip()
    skip_recalculated = env_flag("SKIP_RECALCULATED", True)
    include_same = env_flag("INCLUDE_SAME", False)
    max_abs_delta = q2(os.environ.get("MAX_ABS_DELTA") or "0")

    print(
        f"mode={'APPLY' if apply else 'DRY_RUN'}  "
        f"ONLY_STATUS={only_status or 'ALL'}  "
        f"ONLY_TRADER={only_trader or '-'}  "
        f"SKIP_RECALCULATED={int(skip_recalculated)}  "
        f"MAX_ABS_DELTA={max_abs_delta or 'off'}  "
        f"сумм={len(corrected)}"
    )
    if ambiguous:
        print(f"НЕОДНОЗНАЧНЫЕ (пропуск): {len(ambiguous)}")
        for line in ambiguous:
            print(f"  {line}")
    if apply:
        print("APPLY ограничен Completed → apply_psp_completed_recalc; остальные статусы не трогаем.")
    print()

    buckets: dict[str, list] = defaultdict(list)
    missing: list[str] = []
    skipped: list[tuple[str, str]] = []
    planned: list[tuple[str, InOrder, Decimal, Decimal]] = []

    for oid, new_amount in corrected.items():
        order = resolve_order(oid)
        if order is None:
            missing.append(oid)
            continue

        status = order.status.name if order.status_id else "-"
        trader = "-"
        if order.payment_details_id and order.payment_details.group_id:
            trader_obj = order.payment_details.group.trader
            trader = trader_obj.user.username if trader_obj and trader_obj.user_id else "-"

        old_amount = q2(order.amount)
        delta = q2(new_amount - old_amount)
        buckets[status].append((oid, old_amount, new_amount, delta, trader))

        reason = None
        if only_status.upper() != "ALL" and status != only_status:
            reason = f"status={status} (фильтр {only_status})"
        elif only_trader and trader != only_trader:
            reason = f"trader={trader} (фильтр {only_trader})"
        elif skip_recalculated and order.recalculated:
            reason = "уже recalculated"
        elif not include_same and delta == 0:
            reason = "сумма уже равна чеку"
        elif max_abs_delta > 0 and abs(delta) > max_abs_delta:
            reason = f"|дельта|={abs(delta)} > MAX_ABS_DELTA={max_abs_delta}"
        elif apply and status != "Completed":
            reason = f"APPLY только Completed, сейчас {status}"

        if reason:
            skipped.append((oid, reason))
            continue
        planned.append((oid, order, old_amount, new_amount))

    print("=== ПО СТАТУСАМ ===")
    for status, items in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        total_delta = q2(sum((delta for _, _, _, delta, _ in items), Decimal("0")))
        traders = Counter(trader for *_, trader in items)
        print(
            f"{status}: {len(items)}  дельта={total_delta:+} KZT  "
            f"путь={apply_path_for(status)}  "
            f"трейдеры={dict(traders)}"
        )
        for oid, old, new, delta, trader in sorted(items, key=lambda x: abs(x[3]), reverse=True)[:5]:
            print(f"  {oid}  {old} → {new}  ({delta:+} KZT)  trader={trader}")
        if len(items) > 5:
            print(f"  … ещё {len(items) - 5}")
    print()

    if missing:
        print(f"НЕ НАЙДЕНО: {len(missing)} → {', '.join(missing)}")
    print(f"в плане: {len(planned)}   пропущено: {len(skipped)}")
    if skipped:
        skip_reasons = Counter(r for _, r in skipped)
        print("причины пропуска:")
        for reason, cnt in skip_reasons.most_common():
            print(f"  {cnt}× {reason}")

    if not planned:
        print("нечего делать")
        return

    plan_delta = q2(sum((new - old for _, _, old, new in planned), Decimal("0")))
    print(f"план дельта KZT: {plan_delta:+}  по {len(planned)} заявкам")
    print()

    ok = err = 0
    for oid, order, old_amount, new_amount in planned:
        delta = q2(new_amount - old_amount)
        status = order.status.name if order.status_id else "-"
        line = f"{oid}  [{status}]  {old_amount} → {new_amount}  ({delta:+} KZT)"
        if dry_run:
            print(f"DRY  {line}  → {apply_path_for(status)}")
            ok += 1
            continue
        try:
            with transaction.atomic():
                changed = order.apply_psp_completed_recalc(new_amount)
            order.refresh_from_db()
            print(
                f"OK   {line}  changed={changed}  "
                f"now={q2(order.amount)} recalculated={order.recalculated}"
            )
            ok += 1
        except Exception as exc:
            err += 1
            print(f"ERR  {line}  {exc}")
            traceback.print_exc()

    print()
    print(f"=== ИТОГ {'DRY_RUN' if dry_run else 'APPLY'} ===")
    print(f"ok={ok}  err={err}")
    if dry_run:
        print("Чтобы применить Completed: APPLY=1 (и при необходимости ONLY_TRADER / MAX_ABS_DELTA)")


run()
