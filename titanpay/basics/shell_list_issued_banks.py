"""Уникальные bank из выдачи реквизитов мерчанту/клиенту за период.

Берёт то же поле bank, что уходит в payment_details (PSP create_response
или translate_bank с PS группы локального трейдера).

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_list_issued_banks.py
  DAYS=30 docker compose exec -T app env DAYS=30 python manage.py shell < titanpay/basics/shell_list_issued_banks.py
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from payments.models import PayIn
from payments.psp_payin import requisite_for_payin
from payments.utils import translate_bank

DAYS = int(os.environ.get("DAYS") or "30")


def _bank_from_payin(pay_in) -> str:
    req = requisite_for_payin(pay_in) or {}
    bank = str(req.get("bank") or req.get("bankName") or "").strip()
    if bank:
        return bank
    order = getattr(pay_in, "order", None)
    det = getattr(order, "payment_details", None) if order else None
    group = getattr(det, "group", None) if det else None
    ps = getattr(group, "payment_system", None) if group else None
    if ps and ps.name:
        return (translate_bank(ps.name) or "").strip()
    return ""


def run():
    since = timezone.now() - timedelta(days=DAYS)
    print(f"=== Issued bank names (last {DAYS}d, since {since:%Y-%m-%d %H:%M} UTC) ===")
    qs = (
        PayIn.objects.filter(created_at__gte=since)
        .select_related(
            "payment_system",
            "order__payment_details__group__payment_system",
            "merchant__user",
        )
        .order_by("created_at")
    )
    counts = Counter()
    empty = 0
    total = 0
    for pay_in in qs.iterator(chunk_size=500):
        total += 1
        bank = _bank_from_payin(pay_in)
        if bank:
            counts[bank] += 1
        else:
            empty += 1
    print(f"pay-ins: {total}  with bank: {sum(counts.values())}  empty/no details: {empty}")
    print(f"unique banks: {len(counts)}")
    print("")
    for name, n in counts.most_common():
        print(f"{n:7}  {name}")


run()
