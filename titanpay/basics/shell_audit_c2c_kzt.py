"""Аудит MerchantSolution и TraderTeamRates на PaymentSystem C2C / валюта KZT.

Ничего не трогает, пока APPLY=1. C2CKZT и C2C других валют не смотрит.

За 7 дней (DAYS=7):
  KEEP     — был InOrder, OutOrder или PayIn
  DISABLE  — старых заявок нет за неделю, но история есть: status=0, строку не удаляем
             (InOrder.solution — CASCADE, удаление сотрёт заявки)
  DELETE   — заявок не было никогда
  SKIP_PSP — ставка виртуального PSP (payplat/astrum/…). Не трогаем без CLEAN_PSP=1
  PROTECT  — pandapay_local_kzt / pandapay_kz_local

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_audit_c2c_kzt.py

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_audit_c2c_kzt.py
"""
from __future__ import annotations

import os
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from basics.models import PaymentDetailsGroup, PaymentSystem, Trader, TraderTeamRates
from merchant.models import MerchantSolution
from payments.models import PayIn
from payments.psp_payin import psp_trader_usernames
from trade.models import InOrder, OutOrder

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
CLEAN_PSP = (os.environ.get("CLEAN_PSP") or "").strip().lower() in {"1", "true", "yes"}
DAYS = int(os.environ.get("DAYS") or "7")
PS_NAME = (os.environ.get("PS") or "C2C").strip()
PROTECTED = {
    p.strip().lower()
    for p in (os.environ.get("PROTECT") or "pandapay_local_kzt,pandapay_kz_local").split(",")
    if p.strip()
}


def _sym(ps) -> str:
    cur = getattr(ps, "currency", None)
    return (getattr(cur, "symbol", None) or "").upper()


def _merchant_name(sol: MerchantSolution) -> str:
    user = getattr(getattr(sol, "merchant", None), "user", None)
    return (getattr(user, "username", None) or "?")


since = timezone.now() - timedelta(days=DAYS)
psp_names = {n.lower() for n in psp_trader_usernames()}

print(f"=== C2C KZT audit  APPLY={int(APPLY)}  window={DAYS}d since={since.isoformat()} ===")
print(f"protected merchants: {sorted(PROTECTED)}")
print("PSP team rates are listed and left in place (CLEAN_PSP=1 to include them)")

systems = [
    ps
    for ps in PaymentSystem.objects.filter(name=PS_NAME).select_related("currency")
    if _sym(ps) == "KZT"
]
if not systems:
    print(f"NO PaymentSystem name={PS_NAME!r} currency=KZT")
    raise SystemExit(0)

for ps in systems:
    print(f"\n## PS {ps.name} {ps.id} currency=KZT rate={ps.usdt_exchange_rate}")
    sols = list(
        MerchantSolution.objects.filter(payment_system=ps)
        .select_related("merchant__user", "traffic")
        .order_by("merchant__user__username", "ftd")
    )
    print(f"\nmerchant solutions: {len(sols)}")
    for sol in sols:
        name = _merchant_name(sol)
        week_in = InOrder.objects.filter(solution=sol, creation_date__gte=since).count()
        week_out = OutOrder.objects.filter(solution=sol, creation_date__gte=since).count()
        life_in = InOrder.objects.filter(solution=sol).count()
        life_out = OutOrder.objects.filter(solution=sol).count()
        week_payin = PayIn.objects.filter(
            merchant=sol.merchant, payment_system=ps, created_at__gte=since
        ).count()
        traffic = week_in + week_out + week_payin
        traffic_name = getattr(getattr(sol, "traffic", None), "name", None) or "—"
        if name.lower() in PROTECTED:
            action = "PROTECT"
        elif traffic:
            action = "KEEP"
        elif life_in or life_out:
            action = "DISABLE"
        else:
            action = "DELETE"
        print(
            f"  {action:8} {name:24} ftd={str(sol.ftd):5} status={sol.status} "
            f"mdr_in={sol.mdr_in} traffic={traffic_name} "
            f"week in/out/payin={week_in}/{week_out}/{week_payin} "
            f"life in/out={life_in}/{life_out} id={sol.id}"
        )
        if not APPLY or action in {"KEEP", "PROTECT"}:
            continue
        with transaction.atomic():
            if action == "DISABLE":
                if sol.status != 0:
                    sol.status = 0
                    sol.save(update_fields=["status"])
                    print("           wrote status=0")
            elif action == "DELETE":
                sol.delete()
                print("           deleted (no orders)")

    rates = list(
        TraderTeamRates.objects.filter(payment_system=ps)
        .select_related("team")
        .order_by("team__name")
    )
    print(f"\ntrader team rates: {len(rates)}")
    for rate in rates:
        team = rate.team
        usernames = list(
            Trader.objects.filter(team=team).values_list("user__username", flat=True)
        )
        is_psp = any((u or "").lower() in psp_names for u in usernames)
        week = InOrder.objects.filter(
            solution__payment_system=ps,
            payment_details__group__trader__team=team,
            creation_date__gte=since,
        ).count() + OutOrder.objects.filter(
            solution__payment_system=ps,
            payment_details__group__trader__team=team,
            creation_date__gte=since,
        ).count()
        groups = PaymentDetailsGroup.objects.filter(trader__team=team, payment_system=ps)
        active_n = groups.filter(status=1).count()
        if is_psp and not CLEAN_PSP:
            action = "SKIP_PSP"
        elif week:
            action = "KEEP"
        else:
            action = "OFF"
        print(
            f"  {action:8} team={team.name:24} mdr_in={rate.mdr_in} mdr_out={rate.mdr_out} "
            f"week_orders={week} groups={groups.count()} status1={active_n} "
            f"traders={','.join(usernames) or '-'} id={rate.id}"
        )
        if not APPLY or action != "OFF":
            continue
        with transaction.atomic():
            n_in = groups.filter(in_active=True).update(in_active=False)
            n_out = groups.filter(out_active=True).update(out_active=False)
            rate.delete()
            print(f"           in_active off={n_in} out_active off={n_out} rate deleted")

print("\nDONE")
if not APPLY:
    print("Это был просмотр. APPLY=1 выключает только строки без трафика за окно.")
    print("Строки с историей заявок не удаляются. PSP-ставки не трогаются.")
