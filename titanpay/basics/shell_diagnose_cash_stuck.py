"""
Почему «касса не двигается»: сверка A−L с живыми цифрами.

  EXPECT_WALLET=3156 EXPECT_GIPAY=151 EXPECT_PATRIOT=265 EXPECT_ASTRUM_KZT=146359 \\
  docker compose exec -T -e EXPECT_WALLET -e EXPECT_GIPAY -e EXPECT_PATRIOT -e EXPECT_ASTRUM_KZT app \\
    python manage.py shell < titanpay/basics/shell_diagnose_cash_stuck.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings

from basics.cash_register import (
    c2ckzt_usdt_rate,
    fetch_platform_wallet_usdt,
    kzt_to_usd,
    money,
    prepaid_to_psp_names,
    snapshot,
)
from basics.models import Trader
from merchant.models import Merchant


def _env_dec(name: str):
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    return money(raw)


def main() -> None:
    exp_wallet = _env_dec("EXPECT_WALLET")
    exp_gipay = _env_dec("EXPECT_GIPAY")
    exp_patriot = _env_dec("EXPECT_PATRIOT")
    exp_astrum = _env_dec("EXPECT_ASTRUM_KZT")

    print("=== CASH REGISTER SNAPSHOT (A−L) ===")
    snap = snapshot()
    print(f"cash={snap['cash']}  assets={snap['assets']['total']}  liabilities={snap['liabilities']['total']}")
    print(f"  wallet_total={snap['assets'].get('wallet_total')}  psp_prepaid={snap['assets'].get('psp_total')}")
    print(f"  receivables={snap['assets'].get('receivables_total')}")
    print(f"day.net={snap['pnl']['day']['net']}  month.net={snap['pnl']['month']['net']}")
    print(f"memo.platform_aggregator={snap.get('memo', {}).get('platform_aggregator')}")

    print("\n--- assets detail ---")
    for row in snap["assets"].get("wallets") or []:
        print(f"  wallet {row.get('address')} = {row.get('available')}")
    for row in snap["assets"].get("psp") or []:
        print(f"  prepaid PSP {row.get('username')}: avail={row.get('available')} frozen={row.get('frozen')} held={row.get('held')}")
    for row in snap["assets"].get("receivables") or []:
        print(
            f"  receivable {row.get('username')} kind={row.get('kind')} "
            f"net={row.get('net')} kzt={row.get('kzt')} kgs={row.get('kgs')} rate={row.get('rate')}"
        )

    print("\n--- liabilities (top) ---")
    for row in (snap["liabilities"].get("merchants") or [])[:8]:
        print(f"  merchant {row.get('username')} net={row.get('net')}")
    for row in snap["liabilities"].get("owed_traders") or []:
        print(f"  owed trader {row.get('username')} net={row.get('net')} topups_day={row.get('topups_day')}")
    for row in snap["liabilities"].get("psp_deposits") or []:
        print(f"  deposit PSP {row.get('username')} net={row.get('net')}")

    print("\n=== LIVE CHECK vs your numbers ===")
    prepaid = prepaid_to_psp_names()
    print(f"CASH_REGISTER_PREPAID_TO_PSP={sorted(prepaid)}")
    print(f"CASH_REGISTER_TRC20_WALLET={getattr(settings, 'CASH_REGISTER_TRC20_WALLET', '')!r}")

    # Не долбим TronGrid второй раз — берём из snapshot (там уже cache/retry).
    snap_wallet = money(snap["assets"].get("wallet_total") or 0)
    snap_addr = ""
    for row in snap["assets"].get("wallets") or []:
        snap_addr = row.get("address") or snap_addr
    print(f"wallet in cash snapshot: {snap_addr!r} → {snap_wallet}")
    wallet_usdt, wallet_addr = snap_wallet, snap_addr
    if exp_wallet is not None:
        diff = money(wallet_usdt - exp_wallet)
        print(f"  you said TronLink={exp_wallet}  delta={diff}")
        if abs(diff) > Decimal("1"):
            print(
                "  ! расхождение: проверь что TronLink = USDT TRC20 на "
                f"{getattr(settings, 'CASH_REGISTER_TRC20_WALLET', '')} "
                "(не другой кошелёк / не TRX / не суммa нескольких адресов)"
            )

    for uname, expect in (("gipay1", exp_gipay), ("patriot1", exp_patriot)):
        t = Trader.objects.select_related("user", "balance_usdt", "frozen_balance_usdt").filter(
            user__username__iexact=uname
        ).first()
        if t is None:
            print(f"{uname}: NOT FOUND in LK")
            continue
        avail = money(t.balance_usdt.amount if t.balance_usdt_id else 0)
        frozen = money(t.frozen_balance_usdt.amount if t.frozen_balance_usdt_id else 0)
        held = money(abs(avail + frozen))
        in_cash = uname in prepaid
        print(f"{uname}: LK avail={avail} frozen={frozen} held={held} in_prepaid_list={in_cash}")
        if expect is not None:
            print(f"  you said site/API={expect}  LK_held−expect={money(held - expect)}")
            if abs(held - expect) > Decimal("1"):
                print(
                    "  ! касса считает баланс PSP из ЛК трейдера, НЕ с сайта провайдера. "
                    "Пока ЛК не синхронизирован — цифра в кассе не двигается."
                )
                if uname == "patriot1" and held > expect + Decimal("100"):
                    print(
                        f"  !! MAIN DRIFT: patriot в кассе как актив {held}$, на сайте {expect}$. "
                        f"Лишние ~{money(held - expect)}$ раздувают assets и «замораживают» кассу."
                    )

    print("\n--- astrum ---")
    astrum_traders = list(
        Trader.objects.filter(user__username__icontains="astrum").select_related(
            "user", "balance_usdt", "frozen_balance_usdt"
        )
    )
    if not astrum_traders:
        print("  no trader username~astrum")
    for t in astrum_traders:
        avail = money(t.balance_usdt.amount if t.balance_usdt_id else 0)
        print(
            f"  trader {t.user.username}: usdt={avail} "
            f"in_prepaid={t.user.username in prepaid} "
            f"(KZT site balance NOT used in cash)"
        )
    if exp_astrum is not None:
        rate = c2ckzt_usdt_rate()
        print(f"  you said astrum={exp_astrum} KZT → ~{kzt_to_usd(exp_astrum, rate=rate)} USDT @ rate={rate}")
        print("  ! Astrum KZT по умолчанию НЕ входит в кассу A−L (нет в PREPAID_TO_PSP).")

    print("\n--- why cash can look flat for days ---")
    print("  1) «Касса» = assets−liabilities, не «день». День может быть +80, а A−L почти стоять.")
    print("  2) Крупный Melbet KZT receivable часто доминирует и двигается только с Melbet KZT сделками.")
    print("  3) gipay/patriot в кассе = ЛК трейдера; живой баланс на сайте провайдера сам не подтягивается.")
    print("  4) Кошелёк = TronGrid; при ошибке API → 0 и касса «ломается» вниз, не вверх.")
    print("  5) Astrum/KGS fiat не в формуле A−L.")


main()
