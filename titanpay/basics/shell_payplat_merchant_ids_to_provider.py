"""
Melbet merchant_order_id → PayPlat order_id (то, что провайдер ищет у себя).

Список сапорта в AMOUNTS_FILE / AMOUNTS, формат как обычно:
  23566296459 - 10000,06

Печатает:
  1) таблицу merchant → payplat order_id
  2) готовый список для провайдера:  {order_id} - {сумма}

Запуск:
  docker compose cp /root/amounts.txt app:/tmp/amounts.txt
  docker compose exec -T -e AMOUNTS_FILE=/tmp/amounts.txt app \\
    python manage.py shell < titanpay/basics/shell_payplat_merchant_ids_to_provider.py
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, ROUND_HALF_UP

from payments.models import PayIn, PayplatPayInSession
from trade.models import InOrder

Q2 = Decimal("0.01")
ID_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
NUM_RE = re.compile(r"\d{1,9}(?:[.,]\d{1,2})?")


def q2(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def fmt_amount(v: Decimal) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def load_rows() -> list[tuple[str, Decimal | None]]:
    path = (os.environ.get("AMOUNTS_FILE") or "").strip()
    if path:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = os.environ.get("AMOUNTS") or ""

    text = re.sub(r"\s+", " ", raw)
    matches = list(ID_RE.finditer(text))
    rows: list[tuple[str, Decimal | None]] = []
    seen: set[str] = set()
    for idx, match in enumerate(matches):
        oid = match.group(0)
        if oid in seen:
            continue
        seen.add(oid)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        values = [q2(n.replace(",", ".")) for n in NUM_RE.findall(text[match.end():end])]
        rows.append((oid, values[0] if values else None))
    return rows


def resolve_pay_in(merchant_order_id: str) -> PayIn | None:
    pay_in = (
        PayIn.objects.filter(merchant_order_id=merchant_order_id)
        .select_related("order", "status")
        .order_by("-created_at")
        .first()
    )
    if pay_in is not None:
        return pay_in
    order = InOrder.objects.filter(merchant_order_id=merchant_order_id).order_by("-creation_date").first()
    if order is None:
        return None
    return order.pay_in.order_by("-created_at").first()


def deal_id(session: PayplatPayInSession | None) -> str:
    if session is None:
        return ""
    if (session.provider_order_id or "").strip():
        return str(session.provider_order_id).strip()
    for blob in (session.create_response, session.last_webhook_payload):
        if not isinstance(blob, dict):
            continue
        for key in ("order_id", "deal_id", "id"):
            val = blob.get(key)
            if val not in (None, ""):
                return str(val)
    return ""


def run():
    rows = load_rows()
    if not rows:
        print("Список пуст. Передай AMOUNTS_FILE или AMOUNTS.")
        return

    print("=== MAP merchant_order_id → PayPlat order_id ===")
    print(f"{'merchant':<14} {'payplat':<14} {'amount':<12} status")
    mapped: list[tuple[str, Decimal | None]] = []
    missing: list[str] = []
    no_deal: list[str] = []

    for merchant_id, amount in rows:
        pay_in = resolve_pay_in(merchant_id)
        if pay_in is None:
            missing.append(merchant_id)
            print(f"{merchant_id:<14} {'-':<14} {fmt_amount(amount) if amount is not None else '-':<12} NOT FOUND")
            continue
        session = PayplatPayInSession.objects.filter(pay_in=pay_in).first()
        pid = deal_id(session)
        status = pay_in.status.name if pay_in.status_id else "-"
        amt = fmt_amount(amount) if amount is not None else "-"
        if not pid:
            no_deal.append(merchant_id)
            print(f"{merchant_id:<14} {'-':<14} {amt:<12} {status}  (нет PayPlat order_id, shop_internal={pay_in.id})")
            continue
        print(f"{merchant_id:<14} {pid:<14} {amt:<12} {status}")
        mapped.append((pid, amount))

    print()
    print("=== ДЛЯ ПРОВАЙДЕРА (вставить как есть) ===")
    for pid, amount in mapped:
        if amount is None:
            print(pid)
        else:
            print(f"{pid} - {fmt_amount(amount)}")

    print()
    print("=== СВОДКА ===")
    print(f"в списке: {len(rows)}  с PayPlat order_id: {len(mapped)}")
    if missing:
        print(f"НЕ НАЙДЕНО у нас: {len(missing)} → {', '.join(missing)}")
    if no_deal:
        print(f"нет PayPlat order_id: {len(no_deal)} → {', '.join(no_deal)}")


run()
