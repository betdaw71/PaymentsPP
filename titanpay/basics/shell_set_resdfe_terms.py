"""Статика для живого трейдера resdfe: курс xe+4 + ставка in 4%.

1) MDR в БД (TraderTeamRates) — этот скрипт.
2) Курс xe+4 — PSP_XE_MARKUP_BY_TRADER в .env / settings, потом restart app.

  # dry-run
  docker compose exec -T -e TRADER=resdfe app python manage.py shell \\
    < titanpay/basics/shell_set_resdfe_terms.py

  # записать mdr=4%
  docker compose exec -T -e TRADER=resdfe -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_set_resdfe_terms.py

После APPLY поправь .env (если ещё нет) и перезапусти:
  PSP_XE_MARKUP_BY_TRADER=…,"resdfe":"1.04"…
  docker compose up -d app
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

from django.conf import settings

from basics.models import PaymentDetailsGroup, Trader, TraderTeamRates
from payments.dual_fx import quote_dual_fx, psp_fx_markup_for_trader
from trade.routing.ps_names import kzt_c2c_bank_ps_names

TRADER = (os.environ.get("TRADER") or "resdfe").strip()
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
TARGET_MDR = Decimal((os.environ.get("MDR_IN") or "4").strip())
TARGET_XE = Decimal((os.environ.get("XE_MARKUP") or "1.04").strip())

# Ставка нужна на merchant PS (C2C/C2CKZT — оттуда берётся fee) и на bank-PS групп.
PS_NAMES = {"C2C", "C2CKZT"} | set(kzt_c2c_bank_ps_names())

trader = Trader.objects.select_related("user", "team").filter(user__username=TRADER).first()
if trader is None:
    print(f"FAIL: trader {TRADER!r} not found")
    raise SystemExit(1)
if trader.team_id is None:
    print(f"FAIL: trader {TRADER!r} has no team")
    raise SystemExit(1)

print(f"trader={TRADER} team={trader.team.name} APPLY={APPLY}")
print(f"target: xe markup={TARGET_XE} (xe+{(TARGET_XE - 1) * 100}%)  mdr_in={TARGET_MDR}%")
print(f"PS scope: {sorted(PS_NAMES)}")

# --- FX config ---
raw = getattr(settings, "PSP_XE_MARKUP_BY_TRADER", None) or ""
try:
    fx_map = json.loads(str(raw)) if not isinstance(raw, dict) else raw
except Exception:
    fx_map = {}
configured = fx_map.get(TRADER) or fx_map.get(TRADER.lower())
print(f"PSP_XE_MARKUP_BY_TRADER[{TRADER}] = {configured!r}")
live_markup = psp_fx_markup_for_trader(trader, fallback=Decimal("1.05"))
print(f"effective psp_fx_markup_for_trader = {live_markup}")
if Decimal(str(configured or live_markup)) != TARGET_XE:
    print(
        f"  ! курс НЕ xe+4 в рантайме. Добавь в .env и restart app:\n"
        f'    PSP_XE_MARKUP_BY_TRADER=…,"{TRADER}":"{TARGET_XE}"…'
    )
else:
    print("  FX ok (xe+4 в settings)")

# sample quote on first active group / C2CKZT
g = (
    PaymentDetailsGroup.objects.filter(trader=trader, status=1)
    .select_related("payment_system")
    .first()
)
ps = g.payment_system if g else None
if ps is None:
    from basics.models import PaymentSystem

    ps = PaymentSystem.objects.filter(name="C2CKZT").first()
if ps is not None:
    for merch in ("melbet", "mostbet", "pandapay"):
        q = quote_dual_fx(
            amount=Decimal("5000"), payment_system=ps, trader=trader, merchant=merch
        )
        print(
            f"  quote {merch}: merchant_rate={q.merchant_rate} "
            f"trader_rate={q.psp_rate} psp_markup={q.psp_markup}"
        )

# --- MDR ---
rows = TraderTeamRates.objects.filter(team=trader.team).select_related(
    "payment_system", "payment_system__currency"
)
touched = 0
for row in rows:
    ps = row.payment_system
    if ps is None or ps.name not in PS_NAMES:
        continue
    cur = ps.currency.symbol if ps.currency_id else "?"
    if cur != "KZT":
        continue
    touched += 1
    if row.mdr_in != TARGET_MDR:
        print(f"  mdr {ps.name}: {row.mdr_in}% → {TARGET_MDR}%")
        if APPLY:
            row.mdr_in = TARGET_MDR
            row.save(update_fields=["mdr_in"])
    else:
        print(f"  mdr {ps.name}: {row.mdr_in}% (ok)")

# create missing rates for active groups / C2CKZT
from basics.models import PaymentSystem, Currency

kzt = Currency.objects.filter(symbol="KZT").first()
need_ps = set(
    PaymentDetailsGroup.objects.filter(trader=trader)
    .exclude(payment_system__isnull=True)
    .values_list("payment_system__name", flat=True)
)
need_ps |= {"C2C", "C2CKZT"}
existing_names = {
    r.payment_system.name
    for r in rows
    if r.payment_system_id and r.payment_system.name in PS_NAMES
}
for name in sorted(need_ps):
    if name not in PS_NAMES or name in existing_names:
        continue
    ps_obj = PaymentSystem.objects.filter(name=name, currency=kzt).first()
    if ps_obj is None:
        print(f"  ! PS {name!r} missing — skip create rate")
        continue
    print(f"  + create mdr {name}: {TARGET_MDR}%")
    if APPLY:
        TraderTeamRates.objects.create(
            team=trader.team,
            payment_system=ps_obj,
            mdr_in=TARGET_MDR,
            mdr_out=Decimal("2.5"),
        )
        touched += 1

if touched == 0:
    print("  ! no KZT team rates matched — check team/PS")

print("DONE")
