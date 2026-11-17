"""
Комплексная диагностика: почему «день/месяц плюс», а «касса» стоит или минусует.

Касса A−L ≠ дневной NET. NET оседает на Balance type=2 (aggregator) — memo, не A−L.

  DAYS=3 \\
  docker compose exec -T -e DAYS app \\
    python manage.py shell < titanpay/basics/shell_diagnose_cash_leak_theory.py
"""
from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from basics.cash_register import (
    MSK,
    _period_pnl,
    deposit_from_psp_names,
    money,
    moscow_bounds,
    prepaid_to_psp_names,
    snapshot,
)
from basics.models import Balance, Trader
from merchant.models import Merchant
from trade.models import InOrder, OutOrder, Transaction

DAYS = int(os.environ.get("DAYS") or "3")


def main() -> None:
    now = timezone.now().astimezone(MSK)
    current, day_start, month_start = moscow_bounds(now)
    snap = snapshot(now=now)

    print("=" * 72)
    print("ТЕОРИЯ УТЕЧКИ / РАСХОЖДЕНИЯ КАССЫ")
    print("=" * 72)
    print(f"as_of={snap['as_of']}")
    print(f"КАССА (A−L) = {snap['cash']}")
    print(f"  assets={snap['assets']['total']}  liabilities={snap['liabilities']['total']}")
    print(f"ДЕНЬ NET = {snap['pnl']['day']['net']}   МЕСЯЦ NET = {snap['pnl']['month']['net']}")
    print(f"memo.platform_aggregator (type=2) = {snap['memo']['platform_aggregator']}")
    print()
    print("★ ГЛАВНОЕ: дневной/месячный NET НЕ входит в цифру «Касса».")
    print("  Сделки кладут маржу на Balance type=2 (aggregator).")
    print("  Касса = кошельки+PSP prepaid+receivables − мерчи−депозиты PSP−долг трейдерам…")
    print("  Поэтому несколько дней подряд «день +N» при почти плоской кассе — ожидаемо.")

    print("\n=== 1) Куда делся NET за последние N дней (по Completed) ===")
    window_start = day_start - timedelta(days=DAYS - 1)
    for i in range(DAYS):
        d0 = window_start + timedelta(days=i)
        d1 = d0 + timedelta(days=1)
        p = _period_pnl(d0, d1)
        print(
            f"  {d0.date()} NET={p['net']}  "
            f"in={p['orders_in']} out={p['orders_out']}  "
            f"MDR={p['payin_mdr']}+{p['payout_mdr']} FX={p['payin_fx']} "
            f"trader/PSP={p['trader_fee']} agent={p['agent_fee']} exp={p['expenses']}"
        )

    agg = Balance.objects.filter(type=2).first()
    print(f"\n=== 2) Aggregator type=2 now={money(agg.amount if agg else 0)} ===")
    since = timezone.now() - timedelta(days=DAYS)
    if agg:
        from django.db.models import Sum

        inn = money(
            Transaction.objects.filter(to_balance=agg, creation_date__gte=since).aggregate(
                s=Sum("value")
            )["s"]
            or 0
        )
        out = money(
            Transaction.objects.filter(from_balance=agg, creation_date__gte=since).aggregate(
                s=Sum("value")
            )["s"]
            or 0
        )
        print(f"  last {DAYS}d flows: INTO agg={inn}  OUT OF agg={out}  net_flow={money(inn - out)}")
        print("  (это физическое движение маржи; касса A−L его не показывает)")

    print("\n=== 3) Структура активов (что реально двигает кассу) ===")
    print(f"  wallets sum={snap['assets']['wallet_total']}")
    for w in snap["assets"].get("wallets") or []:
        print(f"    {w.get('username')}: {w.get('available')}  {w.get('address')}")
    print(f"  prepaid PSP={snap['assets']['psp_total']}  names={sorted(prepaid_to_psp_names())}")
    for r in snap["assets"].get("psp") or []:
        print(f"    {r['username']}: held={r.get('held')} LK={r.get('available')}")
    print(f"  receivables={snap['assets']['receivables_total']}")
    for r in snap["assets"].get("receivables") or []:
        print(
            f"    {r['username']} {r.get('kind')}: net={r.get('net')} "
            f"kzt={r.get('kzt')} rate={r.get('rate')}"
        )

    print("\n=== 4) Структура пассивов ===")
    print(f"  merchants={snap['liabilities']['merchants_total']}")
    for r in snap["liabilities"].get("merchants") or []:
        print(f"    {r['username']}: net={r.get('net')}")
    print(f"  deposit PSP={snap['liabilities'].get('psp_deposits_total')} names={sorted(deposit_from_psp_names())}")
    for r in snap["liabilities"].get("psp_deposits") or []:
        print(f"    {r['username']}: {r.get('net')}")
    print(f"  traders owed={snap['liabilities'].get('traders_owed_total')}")
    for r in snap["liabilities"].get("traders_owed") or []:
        print(
            f"    {r['username']}: net={r.get('net')} bal={r.get('balance_owed')} "
            f"ins={r.get('insurance_owed')} topups_day={r.get('topups_day')}"
        )
    print(f"  agents={snap['liabilities']['agents_total']}  teamleads={snap['liabilities']['teamleads_total']}")

    print("\n=== 5) Известные дыры / ложные активы ===")
    # patriot drift hint
    for uname in sorted(prepaid_to_psp_names() | deposit_from_psp_names()):
        t = Trader.objects.filter(user__username__iexact=uname).select_related(
            "balance_usdt", "frozen_balance_usdt", "user"
        ).first()
        if not t:
            print(f"  {uname}: нет в ЛК")
            continue
        a = money(t.balance_usdt.amount if t.balance_usdt_id else 0)
        f = money(t.frozen_balance_usdt.amount if t.frozen_balance_usdt_id else 0)
        role = "prepaid-asset" if uname in prepaid_to_psp_names() else "deposit-liability"
        print(f"  {uname} [{role}]: avail={a} frozen={f}")

    melbet = (
        Merchant.objects.filter(user__username__iexact="melbet")
        .select_related("balance_kzt", "balance_kgs", "balance")
        .first()
    )
    if melbet:
        print(
            f"  melbet USDT={money(melbet.balance.amount if melbet.balance_id else 0)} "
            f"KZT={money(melbet.balance_kzt.amount if melbet.balance_kzt_id else 0)} "
            f"KGS={money(melbet.balance_kgs.amount if melbet.balance_kgs_id else 0)}"
        )
        print("  (в кассу receivable только минусовой KZT→USDT; KGS не входит)")

    print("\n=== 6) Гипотезы (ранжировано) ===")
    print("  H1 NET≠Касса: прибыль дня в aggregator, не в A−L — касса «стоит» при плюсовом дне.")
    print("  H2 Ложный prepaid: ЛК PSP (patriot/gipay/…) ≠ сайт → assets завышены/застыли.")
    print("  H3 Receivable Melbet/Mostbet ест плюс: рост долга мерчу/падение receivable")
    print("     компенсирует рост кошельков → касса flat или минус.")
    print("  H4 Долг resdfe: пополнения на watched wallet → +asset и +liability почти в ноль.")
    print("  H5 Deposit PSP (payplat/prochub/layerone): рост пассива при несинхронном ЛК.")
    print("  H6 Кошелёк TronGrid 429/не тот адрес → wallet_total занижен.")
    print("  H7 Astrum: раньше не был в prepaid; KZT сайта всё ещё не в формуле.")

    print("\n=== 7) Что пришли точечно (для сверки) ===")
    print("  Напишите одним блоком фактические остатки СЕЙЧАС:")
    print("  - TronLink platform TEPKpVs… USDT=")
    print("  - TronLink resdfe TTr5G2… USDT=")
    print("  - gipay сайт USDT=")
    print("  - patriot сайт USDT=")
    print("  - visionx / bitzone / layerone сайт USDT=")
    print("  - astrum сайт (KZT и/или USDT)=")
    print("  - payplat / prochub остаток депозита=")
    print("  - mostbet: available / rolling в ЛК или у них=")
    print("  - сколько по вашему «должно быть кассы» vs что в UI")
    print("  - были ли крупные выводы/пополнения кошелька за 3 дня (суммы)")


main()
