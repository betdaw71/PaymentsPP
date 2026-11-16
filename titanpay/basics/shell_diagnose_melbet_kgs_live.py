"""
Проверка живых реквизитов Melbet local KGS (выдача pay-in / готовность out).

  TRADERS=resdfe,resdfe1 \\
  docker compose exec -T -e TRADERS app \\
    python manage.py shell < titanpay/basics/shell_diagnose_melbet_kgs_live.py
"""
from __future__ import annotations

import os
from datetime import timedelta

from django.utils import timezone

from basics.models import PaymentDetails, PaymentDetailsGroup, Trader, TraderTeamRates
from merchant.models import MerchantSolution
from payments.psp_payin import psp_trader_usernames
from trade.models import InOrder, OutOrder

TRADERS = [
    u.strip()
    for u in (os.environ.get("TRADERS") or "resdfe,resdfe1").split(",")
    if u.strip()
]
PS_NAMES = ("QRKGS", "C2CKGS", "PHONEKGS")
OPEN_IN = ("New", "Money sent by user", "Arbitrage", "Recalculation")


def _ok_detail(ps_name: str, d: PaymentDetails) -> tuple[bool, str]:
    name = ps_name.upper()
    phone = (d.phone or "").strip()
    card = (d.card_number or "").strip()
    qr = (d.qr_payload or "").strip()
    bank = (d.bank_name or "").strip()
    if d.status != 1:
        return False, f"status={d.status}"
    if name == "PHONEKGS":
        if not phone:
            return False, "no phone"
        if not bank:
            return False, "phone ok but bank_name empty"
        return True, f"phone={phone} bank={bank}"
    if name == "C2CKGS":
        if not card:
            return False, "no card"
        if not bank:
            return False, "card ok but bank_name empty"
        return True, f"card=…{card[-4:]} bank={bank}"
    if name == "QRKGS":
        if not qr and not phone:
            return False, "no qr_payload/phone"
        return True, f"qr={'yes' if qr else 'no'} phone={phone or '-'} bank={bank or '-'}"
    return bool(phone or card or qr), "ok"


def main() -> None:
    psp = psp_trader_usernames()
    print("=== Melbet KGS live requisites ===")
    print(f"traders={TRADERS}  psp_blocklist_hit={[u for u in TRADERS if u in psp]}")

    for uname in TRADERS:
        trader = Trader.objects.select_related("user", "team", "balance_usdt").filter(
            user__username__iexact=uname
        ).first()
        if trader is None:
            print(f"\n! {uname}: NOT FOUND")
            continue
        bal = trader.balance_usdt.amount if trader.balance_usdt_id else None
        print(
            f"\n## {uname} team={trader.team.name if trader.team_id else None} "
            f"manual={trader.manual_mode} blocked={trader.blocked} usdt={bal}"
        )
        for ps_name in PS_NAMES:
            rates = None
            if trader.team_id:
                rates = TraderTeamRates.objects.filter(
                    team=trader.team, payment_system__name=ps_name
                ).first()
            groups = list(
                PaymentDetailsGroup.objects.filter(
                    trader=trader, payment_system__name=ps_name
                ).select_related("payment_system", "currency")
            )
            print(
                f"  {ps_name}: groups={len(groups)} "
                f"mdr_in={rates.mdr_in if rates else '-'} mdr_out={rates.mdr_out if rates else '-'}"
            )
            if not groups:
                print("    ! нет группы — в ЛК создайте QRKGS/PHONEKGS/C2CKGS")
                continue
            for g in groups:
                traffic = [t.name for t in g.allowed_traffic.all()]
                print(
                    f"    group {g.id} status={g.status} in={g.in_active} out={g.out_active} "
                    f"cur={g.currency.symbol if g.currency_id else '?'} "
                    f"vol={g.current_volume}/{g.limit_per_period} "
                    f"in_lim=[{g.min_amount_in}..{g.max_amount_in}] "
                    f"traffic={traffic} live={g.auto_live}"
                )
                if g.status != 1:
                    print("      ! status!=1 (нужен Active=1)")
                if not g.in_active:
                    print("      ! in_active=False — pay-in не возьмёт")
                details = PaymentDetails.objects.filter(group=g).order_by("status", "-creation_date")
                ready = 0
                for d in details:
                    ok, note = _ok_detail(ps_name, d)
                    ready += int(ok)
                    print(f"      detail {d.id} status={d.status} {'OK' if ok else 'BAD'} {note}")
                open_in = InOrder.objects.filter(
                    payment_details__group=g, status__name__in=OPEN_IN
                ).count()
                print(f"      ready_details={ready} open_in_orders={open_in}")
                if ready == 0:
                    print("      ! нет валидного реквизита для выдачи")

    print("\n=== Melbet merchant solutions KGS ===")
    sols = (
        MerchantSolution.objects.filter(
            merchant__user__username__iexact="melbet",
            payment_system__name__in=PS_NAMES,
            status=1,
        )
        .select_related("payment_system")
        .order_by("payment_system__name", "ftd")
    )
    for s in sols:
        print(
            f"  {s.payment_system.name} ftd={s.ftd} mdr_in={s.mdr_in} "
            f"lim_in=[{s.min_limit_in}..{s.max_limit_in}] "
            f"lim_out=[{s.min_limit_out}..{s.max_limit_out}] traffic={s.traffic}"
        )

    print("\n=== recent Melbet KGS pay-ins (12h) ===")
    since = timezone.now() - timedelta(hours=12)
    recent = (
        InOrder.objects.filter(
            solution__merchant__user__username__iexact="melbet",
            solution__payment_system__name__in=PS_NAMES,
            creation_date__gte=since,
        )
        .select_related("status", "solution__payment_system", "payment_details__group__trader__user")
        .order_by("-creation_date")[:20]
    )
    if not recent:
        print("  (none)")
    for o in recent:
        tr = "-"
        if o.payment_details_id and o.payment_details.group_id and o.payment_details.group.trader_id:
            tr = o.payment_details.group.trader.user.username
        print(
            f"  {o.merchant_order_id} {o.solution.payment_system.name} "
            f"{o.amount} status={o.status.name if o.status_id else None} trader={tr}"
        )

    print("\n=== recent Melbet KGS pay-outs (12h) ===")
    outs = (
        OutOrder.objects.filter(
            solution__merchant__user__username__iexact="melbet",
            solution__payment_system__name__in=PS_NAMES,
            creation_date__gte=since,
        )
        .select_related("status", "solution__payment_system", "payment_details__group__trader__user")
        .order_by("-creation_date")[:20]
    )
    if not outs:
        print("  (none)")
    for o in outs:
        tr = "-"
        if o.payment_details_id and o.payment_details.group_id and o.payment_details.group.trader_id:
            tr = o.payment_details.group.trader.user.username
        print(
            f"  {o.merchant_order_id} {o.solution.payment_system.name} "
            f"{o.amount} status={o.status.name if o.status_id else None} trader={tr}"
        )


main()
