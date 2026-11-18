"""Привязать TRC-20 кошелёк resdfe1 и один раз прогнать watcher.

Адрес: TJtxY4nnixqBGMf1PMqFokH8HirHxH7eXC

  # в .env (и перезапуск app/worker):
  # CASH_REGISTER_OWED_TO_TRADERS=resdfe,resdfe1
  # TEAM_CRYPTO_DEPOSIT_WALLETS=TTr5G2wrtchVEF4DfMRbNZZeZppHxyyWyL:resdfe,TJtxY4nnixqBGMf1PMqFokH8HirHxH7eXC:resdfe1

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_ensure_resdfe1_deposit_wallet.py

  # poll + credit только НОВЫХ входящих (watch_from=сейчас при первом poll)
  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_ensure_resdfe1_deposit_wallet.py
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
USERNAME = (os.environ.get("TRADER") or "resdfe1").strip() or "resdfe1"
ADDR = (os.environ.get("ADDR") or "TJtxY4nnixqBGMf1PMqFokH8HirHxH7eXC").strip()

print("TEAM_CRYPTO_DEPOSIT_WALLETS =", getattr(settings, "TEAM_CRYPTO_DEPOSIT_WALLETS", ""))
print("CASH_REGISTER_OWED_TO_TRADERS =", getattr(settings, "CASH_REGISTER_OWED_TO_TRADERS", ""))
created = ensure_watched_wallets_from_settings()
print(f"ensure_watched_wallets created={created}")

trader = (
    Trader.objects.filter(user__username__iexact=USERNAME)
    .select_related("user", "balance_usdt", "team")
    .first()
)
if trader is None:
    print(f"ERROR: trader {USERNAME} not found")
else:
    print(
        f"{USERNAME} balance={trader.balance_usdt.amount if trader.balance_usdt_id else None} "
        f"team={trader.team.name if trader.team_id else None} "
        f"deposit_address={deposit_address_for_trader(trader)}"
    )

wallet = (
    WatchedDepositWallet.objects.filter(address_public=ADDR)
    .select_related("trader__user")
    .first()
)
if wallet:
    print(
        f"wallet enabled={wallet.enabled} watch_from={wallet.watch_from} "
        f"last_polled={wallet.last_polled_at} trader={wallet.trader.user.username}"
    )
    print(f"credits logged: {CryptoDepositCredit.objects.filter(wallet=wallet).count()}")
else:
    print(
        "wallet row missing — добавь в .env TEAM_CRYPTO_DEPOSIT_WALLETS "
        f"...{ADDR}:{USERNAME} и перезапусти app/worker, затем снова этот shell"
    )

if APPLY:
    if wallet and wallet.last_polled_at is None:
        wallet.watch_from = timezone.now()
        wallet.save(update_fields=["watch_from"])
        print(f"watch_from reset to {wallet.watch_from} (skip historical / уже ручной top-up)")
    stats = poll_watched_crypto_deposits()
    print("poll:", stats)
    if trader is not None and trader.balance_usdt_id:
        trader.balance_usdt.refresh_from_db()
        print(f"{USERNAME} balance now={trader.balance_usdt.amount}")
else:
    print("DRY-RUN — APPLY=1 чтобы poll + credit новых входящих")

print("DONE")
