"""
Сверка «тетради» с системной кассой.

Тетрадь считает снимок остатков (A−L), а не дневной NET.
Дневные +70$ — маржа сделок; она оседает в aggregator (type=2) и/или
размазывается по строкам Melbet/Mostbet/мерчи/кошелёк — не обязана
поднять итог «Касса» на +70.

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_reconcile_notebook_cash.py
"""
from __future__ import annotations

from decimal import Decimal

from basics.cash_register import (
    c2ckzt_usdt_rate,
    deposit_from_psp_names,
    kzt_to_usd,
    money,
    prepaid_to_psp_names,
    snapshot,
)
from basics.models import Balance, Trader
from merchant.models import Merchant


def _trader(name: str):
    return (
        Trader.objects.filter(user__username__iexact=name)
        .select_related("user", "balance_usdt", "frozen_balance_usdt")
        .first()
    )


def _avail(t) -> Decimal:
    if t is None or not t.balance_usdt_id:
        return Decimal("0.00")
    return money(t.balance_usdt.amount)


def main() -> None:
    snap = snapshot()
    rate = c2ckzt_usdt_rate()

    print("=" * 72)
    print("ПОЧЕМУ +70$/ДЕНЬ НЕ ВИДНО В ТЕТРАДИ / КАССЕ")
    print("=" * 72)
    print(
        f"Система: Касса A−L={snap['cash']}  день NET={snap['pnl']['day']['net']}  "
        f"месяц NET={snap['pnl']['month']['net']}"
    )
    print(f"Aggregator type=2 (маржа, НЕ в тетради) = {snap['memo']['platform_aggregator']}")
    print()
    print("Формула тетради ≈ сумма «наших» остатков − сумма «долгов».")
    print("Формула дня = MDR+FX − комиссии. Это РАЗНЫЕ вещи.")
    print("Если за день NET=+80, а Melbet receivable −50 и долг pandapay +40 —")
    print("итог тетради может остаться −300…−350 как вчера.")

    # Notebook-style rows from system (17.11 mapping)
    melbet = Merchant.objects.filter(user__username__iexact="melbet").select_related(
        "balance_kzt", "balance_kgs"
    ).first()
    mostbet = Merchant.objects.filter(user__username__iexact="mostbet").select_related(
        "balance", "frozen_balance"
    ).first()

    melbet_kzt = money(melbet.balance_kzt.amount) if melbet and melbet.balance_kzt_id else Decimal("0")
    melbet_usd = money(-kzt_to_usd(melbet_kzt, rate=rate)) if melbet_kzt < 0 else Decimal("0")

    mb_av = money(mostbet.balance.amount) if mostbet and mostbet.balance_id else Decimal("0")
    mb_fr = money(mostbet.frozen_balance.amount) if mostbet and mostbet.frozen_balance_id else Decimal("0")
    mb_rr = money(mostbet.rolling_reserve) if mostbet else Decimal("0")
    # notebook "Mostbet" as receivable when available < rolling
    mb_net = money(mb_av + mb_fr - mb_rr)
    mostbet_recv = money(-mb_net) if mb_net < 0 else Decimal("0")
    mostbet_liab = mb_net if mb_net > 0 else Decimal("0")

    wallets = Decimal("0")
    print("\n--- Активы (как в тетради) ---")
    for row in snap["assets"].get("wallets") or []:
        v = money(row["available"])
        wallets += v
        print(f"  TronLink/{row['username']}: {v}")
    print(f"  TronLink SUM: {wallets}   (тетрадь 17.11: 3156)")

    assets = wallets
    for name, note in (
        ("gipay1", "Gipay"),
        ("patriot1", "Patriot"),
        ("visionx1", "VisionX"),
        ("bitzone1", "BitZone"),
        ("astrum_kzt", "Astrum"),
    ):
        t = _trader(name)
        held = money(abs(_avail(t))) if name in prepaid_to_psp_names() else money(0)
        # prepaid: abs(neg LK)
        a = _avail(t)
        held = money(abs(a)) if a < 0 else (a if a > 0 and name in prepaid_to_psp_names() else money(abs(a) if a != 0 and name in prepaid_to_psp_names() else 0))
        if name in prepaid_to_psp_names():
            held = money(abs(a + (money(t.frozen_balance_usdt.amount) if t and t.frozen_balance_usdt_id else 0)))
        print(f"  {note} ({name}): LK={a} → в кассе-актив {held}")
        assets += held

    print(f"  MELBET receivable: {melbet_usd}  (тетрадь ~2812; KZT={melbet_kzt} @ {rate})")
    assets += melbet_usd
    print(f"  Mostbet receivable: {mostbet_recv}  (тетрадь ~4633; LK av={mb_av} rr={mb_rr})")
    assets += mostbet_recv

    print(f"  SUM assets≈ {money(assets)}")

    print("\n--- Пассивы (как в тетради) ---")
    liab = Decimal("0")
    for mname in ("aggrepay", "pandapay", "alemkredit"):
        m = Merchant.objects.filter(user__username__iexact=mname).select_related(
            "balance", "frozen_balance"
        ).first()
        if not m:
            continue
        n = money(_avail_m(m) + _frozen_m(m))
        if n > 0:
            print(f"  {mname}: {n}")
            liab += n
    for name in sorted(deposit_from_psp_names()):
        t = _trader(name)
        a = _avail(t)
        if a > 0:
            print(f"  {name} deposit owed: {a}")
            liab += a
    # resdfe
    for row in snap["liabilities"].get("traders_owed") or []:
        print(f"  trader owed {row['username']}: {row['net']}")
        liab += money(row["net"])
    for row in snap["liabilities"].get("agents") or []:
        n = money(row["available"]) + money(row.get("frozen") or 0)
        if n:
            print(f"  agent {row['username']}: {n}")
            liab += n
    for row in snap["liabilities"].get("teamleads") or []:
        n = money(row["available"]) + money(row.get("frozen") or 0)
        if n:
            print(f"  TL {row['username']}: {n}")
            liab += n
    if mostbet_liab > 0:
        print(f"  mostbet we owe: {mostbet_liab}")
        liab += mostbet_liab

    print(f"  SUM liabilities≈ {money(liab)}")
    print(f"\n  A−L ≈ {money(assets - liab)}   system cash={snap['cash']}")
    print(f"  тетрадь 17.11: 11328−11684=−356")

    print("\n=== Почему дни с NET≈70 не двигают тетрадь на +70 ===")
    print("  1) NET — это комиссия, не рост TronLink. Деньги клиентов крутятся в PSP/мерчах.")
    print("  2) Маржа физически на Balance type=2 (~325k) — в тетрадь НЕ пишешь.")
    print("  3) За те же дни у тебя в тетради: ЗП, долги (Артём), выводы Mostbet, команда —")
    print("     это прямые минусы к ликвидности, часто >> 70$/день.")
    print("  4) Melbet/Mostbet/Patriot строки скачут на сотни–тысячи; NET 70 тонет в шуме.")
    print("  5) Итог тетради 12–17.11 держится около −300…−650 — это уровень кассового")
    print("     разрыва ликвидности, а не P&L. P&L смотри «день/месяц» или прирост aggregator.")

    print("\n=== Что вести в тетради отдельно ===")
    print("  Касса (A−L)     — ликвидность / разрыв")
    print("  День NET        — из UI «Сегодня»")
    print("  Δ Aggregator    — куда реально села маржа")
    print("  Не смешивать в одну строку «заработал 70 → касса должна +70»")


def _avail_m(m) -> Decimal:
    return money(m.balance.amount) if m.balance_id else Decimal("0")


def _frozen_m(m) -> Decimal:
    return money(m.frozen_balance.amount) if m.frozen_balance_id else Decimal("0")


main()
