"""
Конверсия по банкам выданных реквизитов и по PSP — после cutoff.

Банк = то же поле bank, что уходит мерчу (requisite_for_payin),
не PS группы (у PSP группа часто C2CKZT/C2C).

  docker compose exec -T -e DAYS=14 -e CUTOFF=2026-11-07 -e MIN_AMOUNT=5000 \\
    app python manage.py shell < titanpay/basics/shell_requisite_bank_conversion.py

  MERCHANTS=all|mostbet,melbet
  SIDE=after|before|both   (default after)
  MIN_ISSUED=15
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn
from payments.psp_payin import requisite_for_payin
from payments.utils import translate_bank

MSK = ZoneInfo("Europe/Moscow")
DAYS = int(os.environ.get("DAYS") or "14")
CUTOFF_RAW = (os.environ.get("CUTOFF") or "2026-11-07").strip()
MERCHANTS_RAW = (os.environ.get("MERCHANTS") or "all").strip()
SIDE = (os.environ.get("SIDE") or "after").strip().lower()
MIN_AMOUNT = Decimal(str(os.environ.get("MIN_AMOUNT") or "5000"))
MIN_ISSUED = int(os.environ.get("MIN_ISSUED") or "15")
Q2 = Decimal("0.01")

cutoff = datetime.strptime(CUTOFF_RAW, "%Y-%m-%d").replace(tzinfo=MSK)
now = timezone.now().astimezone(MSK)
since = now - timedelta(days=DAYS)


def pct(n, d):
    if not d:
        return None
    return (Decimal(n) * Decimal(100) / Decimal(d)).quantize(Q2, rounding=ROUND_HALF_UP)


def pct_s(n, d):
    p = pct(n, d)
    return f"{p}%" if p is not None else "n/a"


def provider_of(pay) -> str:
    order = getattr(pay, "order", None)
    if order is None or not getattr(order, "payment_details_id", None):
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username or "(no_trader)"
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def bank_of(pay) -> str:
    """Имя банка из выдачи мерчу (PSP create_response), иначе PS группы."""
    try:
        req = requisite_for_payin(pay) or {}
        bank = str(req.get("bank") or req.get("bankName") or "").strip()
        if bank:
            return bank
    except Exception:  # noqa: BLE001
        pass
    order = getattr(pay, "order", None)
    if order is None or not getattr(order, "payment_details_id", None):
        return "(no_bank)"
    try:
        ps = order.payment_details.group.payment_system
        name = (ps.name if ps else "") or ""
        return (translate_bank(name) or name or "(no_bank)").strip()
    except Exception:  # noqa: BLE001
        return "(no_bank)"


qs = (
    PayIn.objects.filter(created_at__gte=since)
    .select_related(
        "status",
        "merchant__user",
        "order__payment_details__group__trader__user",
        "order__payment_details__group__payment_system",
    )
)
want_all = MERCHANTS_RAW.lower() in {"", "all", "*"}
if not want_all:
    qs = qs.filter(merchant__user__username__in=[p.strip() for p in MERCHANTS_RAW.split(",") if p.strip()])

pays = list(qs.iterator(chunk_size=1000))


def side_of(pay) -> str:
    return "after" if pay.created_at.astimezone(MSK) >= cutoff else "before"


def report(label: str, subset: list):
    subset = [p for p in subset if Decimal(str(p.amount or 0)) >= MIN_AMOUNT]
    by_bank = defaultdict(lambda: {"c": 0, "d": 0, "ok": 0})
    by_psp = defaultdict(lambda: {"c": 0, "d": 0, "ok": 0})
    by_bank_psp = defaultdict(lambda: {"c": 0, "d": 0, "ok": 0})

    for p in subset:
        st = p.status.name if p.status_id else ""
        bank = bank_of(p)
        psp = provider_of(p)
        for cell in (by_bank[bank], by_psp[psp], by_bank_psp[(bank, psp)]):
            cell["c"] += 1
            if st == "Declined":
                cell["d"] += 1
            elif st == "Success":
                cell["ok"] += 1

    print(f"\n{'=' * 78}\n{label}  n={len(subset)}  min_amount≥{MIN_AMOUNT}  min_issued={MIN_ISSUED}\n{'=' * 78}")

    def rows_from(mapping, key_fmt=str):
        out = []
        for k, c in mapping.items():
            iss = c["c"] - c["d"]
            if iss < MIN_ISSUED:
                continue
            out.append((key_fmt(k), c["c"], iss, c["ok"], pct(c["ok"], iss)))
        out.sort(key=lambda r: (r[4] is None, -(r[4] or 0), -r[2]))
        return out

    bank_rows = rows_from(by_bank)
    print("\nBANKS issued to merchant  (best → worst by iss→ok)")
    print(f"  {'bank':28} {'create':>7} {'iss':>6} {'ok':>5} {'iss→ok':>8}")
    for name, c, iss, ok, _p in bank_rows:
        print(f"  {name:28} {c:7} {iss:6} {ok:5} {pct_s(ok, iss):>8}")
    if bank_rows:
        best = bank_rows[0]
        worst = bank_rows[-1]
        print(f"  BEST:  {best[0]}  iss→ok={pct_s(best[3], best[2])}  iss={best[2]}")
        print(f"  WORST: {worst[0]}  iss→ok={pct_s(worst[3], worst[2])}  iss={worst[2]}")

    print("\nPSP traders")
    print(f"  {'psp':16} {'create':>7} {'iss':>6} {'ok':>5} {'iss→ok':>8}")
    for name, c, iss, ok, _p in rows_from(by_psp):
        print(f"  {name:16} {c:7} {iss:6} {ok:5} {pct_s(ok, iss):>8}")

    print("\nBANK × PSP (weak cells — кандидаты на письмо провайдеру, iss→ok<25%)")
    weak = []
    for (bank, psp), c in by_bank_psp.items():
        iss = c["c"] - c["d"]
        if iss < MIN_ISSUED:
            continue
        rate = pct(c["ok"], iss)
        if rate is not None and rate < Decimal("25"):
            weak.append((bank, psp, iss, c["ok"], rate))
    weak.sort(key=lambda x: (x[4], -x[2]))
    if not weak:
        print("  (нет ячеек iss≥MIN и iss→ok<25%)")
    for bank, psp, iss, ok, rate in weak[:30]:
        print(f"  {bank:22} × {psp:12}  iss={iss:4} ok={ok:3} iss→ok={rate}%")


sides = []
if SIDE in {"before", "both"}:
    sides.append(("BEFORE " + cutoff.date().isoformat(), [p for p in pays if side_of(p) == "before"]))
if SIDE in {"after", "both"}:
    sides.append(("AFTER " + cutoff.date().isoformat(), [p for p in pays if side_of(p) == "after"]))

print(f"Requisite/bank conversion  DAYS={DAYS} CUTOFF={cutoff.date()} MERCHANTS={MERCHANTS_RAW} SIDE={SIDE}")
for label, subset in sides:
    by_m = defaultdict(list)
    for p in subset:
        if p.merchant_id and p.merchant.user_id:
            by_m[p.merchant.user.username].append(p)
    report(f"ALL {label}", subset)
    for mname in sorted(by_m.keys(), key=lambda n: -len(by_m[n])):
        if len(by_m[mname]) < 20:
            continue
        report(f"{mname} {label}", by_m[mname])

print("\nDONE")
