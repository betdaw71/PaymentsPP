"""Watch external USDT TRC-20 wallets (TronGrid) and credit trader balances.

Unlike crypto-service deposits (sweep + private key), this path only observes
incoming TRC-20 transfers and books a Deposit Transaction from Balance type=3.

Do NOT put watched addresses into cryptodb wallets — that would double-credit
if the sweep pipeline also processed them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

USDT_CONTRACT_DEFAULT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
Q2 = Decimal("0.01")


def _money(raw) -> Decimal:
    try:
        return Decimal(str(raw or 0)).quantize(Q2)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def parse_wallet_map(raw: str | None = None) -> list[tuple[str, str]]:
    """'addr:username,addr2:user2' → [(addr, username), …]."""
    text = (raw if raw is not None else getattr(settings, "TEAM_CRYPTO_DEPOSIT_WALLETS", "") or "").strip()
    out: list[tuple[str, str]] = []
    for part in text.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        address, username = part.split(":", 1)
        address = address.strip()
        username = username.strip()
        if address and username:
            out.append((address, username))
    return out


def fetch_trc20_incoming(address: str, *, min_timestamp_ms: int | None = None, limit: int = 50) -> list[dict]:
    """Incoming USDT TRC-20 transfers to `address` via TronGrid."""
    import requests

    contract = (getattr(settings, "USDT_TRC20_CONTRACT", None) or USDT_CONTRACT_DEFAULT).strip()
    headers = {}
    api_key = (getattr(settings, "TRONGRID_API_KEY", None) or "").strip()
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key

    params = {
        "only_to": "true",
        "limit": str(max(1, min(int(limit), 200))),
        "contract_address": contract,
    }
    if min_timestamp_ms is not None and min_timestamp_ms > 0:
        params["min_timestamp"] = str(int(min_timestamp_ms))

    response = requests.get(
        f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20",
        headers=headers,
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json() or {}
    rows = payload.get("data") or []
    return [row for row in rows if isinstance(row, dict)]


def _transfer_amount_usdt(row: dict) -> Decimal:
    raw = row.get("value")
    token = row.get("token_info") or {}
    try:
        decimals = int(token.get("decimals") if token.get("decimals") is not None else 6)
    except (TypeError, ValueError):
        decimals = 6
    try:
        base = Decimal(str(raw or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")
    if decimals < 0:
        decimals = 6
    amount = base / (Decimal(10) ** decimals)
    return _money(amount)


def _tx_id(row: dict) -> str:
    return str(row.get("transaction_id") or row.get("transactionId") or "").strip()


def ensure_watched_wallets_from_settings() -> int:
    """Upsert WatchedDepositWallet rows from TEAM_CRYPTO_DEPOSIT_WALLETS. Returns created count."""
    from basics.models import Trader
    from trade.models import Address, WatchedDepositWallet

    created = 0
    for address, username in parse_wallet_map():
        trader = (
            Trader.objects.select_related("balance_usdt", "user")
            .filter(user__username__iexact=username)
            .first()
        )
        if trader is None or trader.balance_usdt_id is None:
            logger.warning("team crypto wallet: trader %s not found or has no balance", username)
            continue
        wallet, was_created = WatchedDepositWallet.objects.get_or_create(
            address_public=address,
            defaults={
                "trader": trader,
                "enabled": True,
                "watch_from": timezone.now(),
            },
        )
        if was_created:
            created += 1
        elif wallet.trader_id != trader.id:
            wallet.trader = trader
            wallet.save(update_fields=["trader"])
        # Prefer this address in ЛК deposit_address (boss balance Address).
        Address.objects.update_or_create(
            address_public=address,
            defaults={"balance": trader.balance_usdt},
        )
    return created


def credit_incoming_for_wallet(wallet) -> dict:
    """Poll one watched wallet. Credits only transfers at/after wallet.watch_from."""
    from trade.models import CryptoDepositCredit, Transaction, TransactionType
    from basics.models import Balance

    stats = {"fetched": 0, "credited": 0, "skipped": 0, "errors": 0}
    if wallet is None or not wallet.enabled:
        return stats

    watch_from = wallet.watch_from or wallet.created_at or timezone.now()
    min_ms = int(watch_from.timestamp() * 1000)
    try:
        rows = fetch_trc20_incoming(wallet.address_public, min_timestamp_ms=min_ms)
    except Exception:
        logger.exception("tron grid poll failed for %s", wallet.address_public)
        stats["errors"] += 1
        return stats

    stats["fetched"] = len(rows)
    trader = wallet.trader
    if trader is None or trader.balance_usdt_id is None:
        logger.error("watched wallet %s has no trader balance", wallet.address_public)
        stats["errors"] += 1
        return stats

    chain = Balance.objects.filter(type=3).first()
    deposit_type = TransactionType.objects.filter(name="Deposit").first()
    if chain is None or deposit_type is None:
        logger.error("Balance type=3 or TransactionType Deposit missing")
        stats["errors"] += 1
        return stats

    for row in rows:
        tx_id = _tx_id(row)
        if not tx_id:
            stats["skipped"] += 1
            continue
        if CryptoDepositCredit.objects.filter(tx_id=tx_id).exists():
            stats["skipped"] += 1
            continue

        amount = _transfer_amount_usdt(row)
        to_addr = str(row.get("to") or "").strip()
        if to_addr and to_addr != wallet.address_public:
            stats["skipped"] += 1
            continue
        if amount <= 0:
            stats["skipped"] += 1
            continue

        ts_raw = row.get("block_timestamp") or row.get("block_ts")
        try:
            block_at = datetime.fromtimestamp(int(ts_raw) / 1000, tz=dt_timezone.utc) if ts_raw else None
        except (TypeError, ValueError, OSError):
            block_at = None
        if block_at is not None and block_at < watch_from:
            stats["skipped"] += 1
            continue

        try:
            with transaction.atomic():
                credit = CryptoDepositCredit.objects.create(
                    wallet=wallet,
                    tx_id=tx_id,
                    amount=amount,
                    from_address=str(row.get("from") or "")[:128],
                    block_at=block_at,
                    credited=False,
                    note="pending",
                )
                Transaction.create(
                    _from=chain,
                    _to=trader.balance_usdt,
                    _transaction_type=deposit_type,
                    value=amount,
                    _comment=f"Crypto deposit {tx_id[:16]}",
                )
                credit.credited = True
                credit.note = "credited"
                credit.save(update_fields=["credited", "note"])
            stats["credited"] += 1
            logger.info(
                "credited %s USDT to %s from tx %s",
                amount,
                trader.user.username,
                tx_id,
            )
        except Exception:
            logger.exception("failed to credit tx %s for %s", tx_id, wallet.address_public)
            stats["errors"] += 1

    wallet.last_polled_at = timezone.now()
    wallet.save(update_fields=["last_polled_at"])
    return stats


def poll_watched_crypto_deposits() -> dict:
    """Cron entry: ensure configured wallets exist, then credit new incoming USDT."""
    from trade.models import WatchedDepositWallet

    ensure_watched_wallets_from_settings()
    totals = {"wallets": 0, "fetched": 0, "credited": 0, "skipped": 0, "errors": 0}
    qs = WatchedDepositWallet.objects.filter(enabled=True).select_related(
        "trader", "trader__user", "trader__balance_usdt"
    )
    for wallet in qs:
        totals["wallets"] += 1
        part = credit_incoming_for_wallet(wallet)
        for key in ("fetched", "credited", "skipped", "errors"):
            totals[key] += part.get(key, 0)
    if totals["credited"] or totals["errors"]:
        logger.info("crypto deposit watch: %s", totals)
    return totals


def deposit_address_for_trader(trader) -> str:
    """Preferred deposit address: watched wallet for trader/boss, else Address on balance."""
    from trade.models import Address, WatchedDepositWallet

    if trader is None:
        return ""
    candidates = []
    candidates.append(trader.id)
    if getattr(trader, "boss_id", None):
        candidates.append(trader.boss_id)
    watched = (
        WatchedDepositWallet.objects.filter(enabled=True, trader_id__in=candidates)
        .order_by("created_at")
        .first()
    )
    if watched is not None:
        return watched.address_public or ""

    bal = None
    if trader.is_boss:
        bal = trader.balance_usdt
    elif trader.boss_id and trader.boss is not None:
        bal = trader.boss.balance_usdt
    if bal is None:
        return ""
    addr = bal.address.order_by("id").first()
    return (addr.address_public or "") if addr is not None else ""
