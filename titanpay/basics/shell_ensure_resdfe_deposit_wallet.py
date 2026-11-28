"""Привязать TRC-20 кошелёк команды resdfe и один раз прогнать watcher.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_ensure_resdfe_deposit_wallet.py

  # сразу зачислить (после migrate)
  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_ensure_resdfe_deposit_wallet.py
"""
from __future__ import annotations

import os

from django.conf import settings
from django.utils import timezone

from basics.models import Trader
from trade.crypto_deposit_watch import (
    deposit_address_for_trader,
    ensure_watched_wallets_from_settings,
    poll_watched_crypto_deposits,
)
from trade.models import CryptoDepositCredit, WatchedDepositWallet

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
ADDR = "TTr5G2wrtchVEF4DfMRbNZZeZppHxyyWyL"

print("TEAM_CRYPTO_DEPOSIT_WALLETS =", getattr(settings, "TEAM_CRYPTO_DEPOSIT_WALLETS", ""))
created = ensure_watched_wallets_from_settings()
print(f"ensure_watched_wallets created={created}")

trader = Trader.objects.filter(user__username__iexact="resdfe").select_related("user", "balance_usdt").first()
if trader is None:
    print("ERROR: trader resdfe not found")
else:
    print(
        f"resdfe balance={trader.balance_usdt.amount if trader.balance_usdt_id else None} "
        f"deposit_address={deposit_address_for_trader(trader)}"
    )

wallet = WatchedDepositWallet.objects.filter(address_public=ADDR).select_related("trader__user").first()
if wallet:
    print(
        f"wallet enabled={wallet.enabled} watch_from={wallet.watch_from} "
        f"last_polled={wallet.last_polled_at} trader={wallet.trader.user.username}"
    )
    print(f"credits logged: {CryptoDepositCredit.objects.filter(wallet=wallet).count()}")
else:
    print("wallet row missing — check TEAM_CRYPTO_DEPOSIT_WALLETS / trader exists")

if APPLY:
    # Не зачислять историю до деплоя: watch_from = сейчас, если ещё не поллили.
    if wallet and wallet.last_polled_at is None:
        wallet.watch_from = timezone.now()
        wallet.save(update_fields=["watch_from"])
        print(f"watch_from reset to {wallet.watch_from} (skip historical)")
    stats = poll_watched_crypto_deposits()
    print("poll:", stats)
    if trader is not None:
        trader.balance_usdt.refresh_from_db()
        print(f"resdfe balance now={trader.balance_usdt.amount}")
else:
    print("DRY-RUN — APPLY=1 чтобы poll + credit новых входящих")

print("DONE")
