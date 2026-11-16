"""
Диагностика входящего USDT TRC-20 по хешу транзакции (watched wallet → balance_usdt).

Пример (resdfe):
  docker compose exec -T \\
    -e TX=7277adb99354cef42ea3e7e063b45efa142a826e6e8487d661793b28da83e570 \\
    -e TRADER=resdfe \\
    app python manage.py shell < titanpay/basics/shell_diagnose_crypto_deposit_tx.py

  # если tx на наш кошелёк, после watch_from, ещё не credited — зачислить:
  docker compose exec -T -e TX=... -e TRADER=resdfe -e APPLY=1 \\
    app python manage.py shell < titanpay/basics/shell_diagnose_crypto_deposit_tx.py
"""
from __future__ import annotations

import os
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from basics.models import Balance, Trader
from trade.crypto_deposit_watch import (
    USDT_CONTRACT_DEFAULT,
    _money,
    credit_incoming_for_wallet,
    deposit_address_for_trader,
    ensure_watched_wallets_from_settings,
)
from trade.models import CryptoDepositCredit, Transaction, TransactionType, WatchedDepositWallet

TX = (os.environ.get("TX") or os.environ.get("TXID") or os.environ.get("HASH") or "").strip()
TRADER = (os.environ.get("TRADER") or "resdfe").strip() or "resdfe"
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}
USDT_CONTRACT = (getattr(settings, "USDT_TRC20_CONTRACT", None) or USDT_CONTRACT_DEFAULT).strip()


def _headers() -> dict:
    headers = {}
    api_key = (getattr(settings, "TRONGRID_API_KEY", None) or "").strip()
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    return headers


def _msk(dt) -> str:
    if dt is None:
        return "-"
    try:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:  # noqa: BLE001
        return str(dt)


def _amount_from_value(raw, decimals: int = 6) -> Decimal:
    try:
        base = Decimal(str(raw or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")
    return _money(base / (Decimal(10) ** max(0, decimals)))


def fetch_tx_info(tx_id: str) -> dict | None:
    """TronGrid wallet/gettransactioninfobyid."""
    try:
        response = requests.post(
            "https://api.trongrid.io/wallet/gettransactioninfobyid",
            json={"value": tx_id},
            headers=_headers(),
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json() or {}
        return payload if isinstance(payload, dict) and payload else None
    except Exception as exc:  # noqa: BLE001
        print(f"gettransactioninfobyid failed: {exc}")
        return None


def fetch_tx(tx_id: str) -> dict | None:
    try:
        response = requests.post(
            "https://api.trongrid.io/wallet/gettransactionbyid",
            json={"value": tx_id},
            headers=_headers(),
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json() or {}
        return payload if isinstance(payload, dict) and payload else None
    except Exception as exc:  # noqa: BLE001
        print(f"gettransactionbyid failed: {exc}")
        return None


def fetch_trc20_by_tx(tx_id: str) -> list[dict]:
    """Find TRC-20 transfer rows for this tx via events / account scan helpers."""
    rows: list[dict] = []
    # 1) events endpoint
    try:
        response = requests.get(
            f"https://api.trongrid.io/v1/transactions/{tx_id}/events",
            headers=_headers(),
            timeout=25,
        )
        if response.ok:
            for ev in (response.json() or {}).get("data") or []:
                if not isinstance(ev, dict):
                    continue
                if (ev.get("event_name") or "").lower() != "transfer":
                    continue
                result = ev.get("result") or {}
                contract = str(ev.get("contract_address") or "").strip()
                # events sometimes return hex contract; keep as-is for print
                to_addr = str(result.get("to") or result.get("1") or "").strip()
                from_addr = str(result.get("from") or result.get("0") or "").strip()
                value = result.get("value") or result.get("2")
                rows.append(
                    {
                        "source": "events",
                        "transaction_id": tx_id,
                        "contract_address": contract,
                        "from": from_addr,
                        "to": to_addr,
                        "value": value,
                        "token_info": {"decimals": 6, "symbol": "USDT?"},
                        "block_timestamp": ev.get("block_timestamp"),
                        "raw_event": ev.get("event_name"),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        print(f"events fetch failed: {exc}")

    # 2) if we know expected wallets, scan their recent trc20 list
    return rows


def scan_wallet_for_tx(address: str, tx_id: str, *, limit: int = 200) -> dict | None:
    try:
        response = requests.get(
            f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20",
            headers=_headers(),
            params={
                "limit": str(limit),
                "contract_address": USDT_CONTRACT,
            },
            timeout=25,
        )
        response.raise_for_status()
        for row in (response.json() or {}).get("data") or []:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("transaction_id") or row.get("transactionId") or "").strip()
            if rid.lower() == tx_id.lower():
                row = dict(row)
                row["source"] = "account_trc20"
                return row
    except Exception as exc:  # noqa: BLE001
        print(f"account trc20 scan failed for {address}: {exc}")
    return None


def base58_hint_from_hex(hex_addr: str) -> str:
    """Best-effort: TronGrid events often give 41-prefixed hex; leave printable."""
    h = (hex_addr or "").strip()
    if h.startswith("41") and len(h) == 42:
        return f"hex:{h}"
    return h


print("=" * 88)
print("CRYPTO DEPOSIT TX DIAGNOSE")
print(f"  TX={TX or '(empty)'}")
print(f"  TRADER={TRADER}  APPLY={int(APPLY)}")
print(f"  USDT_CONTRACT={USDT_CONTRACT}")
print(f"  TEAM_CRYPTO_DEPOSIT_WALLETS={getattr(settings, 'TEAM_CRYPTO_DEPOSIT_WALLETS', '')}")
print(f"  TRONGRID_API_KEY set={bool((getattr(settings, 'TRONGRID_API_KEY', None) or '').strip())}")
print("=" * 88)

if not TX:
    raise SystemExit("Set TX=<tron_txid>")

tx_norm = TX.lower().removeprefix("0x")
if len(tx_norm) != 64:
    print(f"WARN: unusual tx length={len(tx_norm)} (expect 64 hex)")

ensure_watched_wallets_from_settings()

trader = (
    Trader.objects.filter(user__username__iexact=TRADER)
    .select_related("user", "balance_usdt")
    .first()
)
if trader is None:
    raise SystemExit(f"trader {TRADER!r} not found")

bal = trader.balance_usdt
print(
    f"\n--- Trader {trader.user.username} ---\n"
    f"  balance_usdt={bal.amount if bal else None}  "
    f"frozen={getattr(trader, 'frozen_balance_usdt', None)}\n"
    f"  deposit_address_for_trader={deposit_address_for_trader(trader)}"
)

wallets = list(
    WatchedDepositWallet.objects.filter(trader=trader)
    .select_related("trader__user")
    .order_by("created_at")
)
# also wallets that map to this username via address on any trader
all_watched = list(WatchedDepositWallet.objects.select_related("trader__user").all())
print(f"\n--- WatchedDepositWallet for trader: n={len(wallets)} ---")
if not wallets:
    print("  NONE — watcher cannot credit this trader")
for w in wallets:
    print(
        f"  {w.address_public}\n"
        f"    enabled={w.enabled} watch_from={_msk(w.watch_from)} "
        f"last_polled={_msk(w.last_polled_at)} created={_msk(w.created_at)}"
    )

credit = CryptoDepositCredit.objects.filter(tx_id__iexact=tx_norm).select_related(
    "wallet", "wallet__trader__user"
).first()
if credit is None:
    credit = CryptoDepositCredit.objects.filter(tx_id__iexact=TX).select_related(
        "wallet", "wallet__trader__user"
    ).first()

print("\n--- CryptoDepositCredit by tx ---")
if credit is None:
    print("  NOT FOUND — ещё не зачисляли / не видели этот tx")
else:
    print(
        f"  id={credit.id}\n"
        f"  wallet={credit.wallet.address_public} → {credit.wallet.trader.user.username}\n"
        f"  amount={credit.amount} credited={credit.credited} note={credit.note!r}\n"
        f"  from={credit.from_address} block_at={_msk(credit.block_at)} "
        f"created={_msk(credit.created_at)}"
    )

# ledger comments mentioning tx
tx_prefix = tx_norm[:16]
ledger = list(
    Transaction.objects.filter(comment__icontains=tx_prefix)
    .select_related("transaction_type")
    .order_by("-created_at")[:10]
)
print(f"\n--- Ledger Transaction comment~{tx_prefix!r}: n={len(ledger)} ---")
for t in ledger:
    print(
        f"  {_msk(t.created_at)}  type={getattr(t.transaction_type, 'name', '?')}  "
        f"value={t.value}  {t.comment!r}"
    )

print("\n--- TronGrid: transaction ---")
info = fetch_tx_info(tx_norm)
raw_tx = fetch_tx(tx_norm)
if info is None and raw_tx is None:
    print("  TX not found on TronGrid (wrong hash / not confirmed / API error)")
else:
    if info:
        print(
            f"  info id={info.get('id')} block={info.get('blockNumber')} "
            f"receipt={info.get('receipt')} fee={info.get('fee')} "
            f"contractResult={info.get('contractResult')}"
        )
        ts = info.get("blockTimeStamp")
        if ts:
            try:
                block_at = datetime.fromtimestamp(int(ts) / 1000, tz=dt_timezone.utc)
                print(f"  block_at={_msk(block_at)}")
            except (TypeError, ValueError, OSError):
                pass
    if raw_tx:
        ret = raw_tx.get("ret") or []
        print(f"  raw ret={ret}")
        contracts = ((raw_tx.get("raw_data") or {}).get("contract")) or []
        for c in contracts[:3]:
            print(f"  contract.type={c.get('type')} parameter.keys={list((c.get('parameter') or {}).get('value') or {})}")

print("\n--- TronGrid: TRC-20 Transfer for this tx ---")
trc_rows = fetch_trc20_by_tx(tx_norm)
found_on_wallets: list[tuple[WatchedDepositWallet, dict]] = []
for w in wallets or all_watched:
    hit = scan_wallet_for_tx(w.address_public, tx_norm)
    if hit:
        found_on_wallets.append((w, hit))
        trc_rows.append(hit)

if not trc_rows and not found_on_wallets:
    print("  No TRC-20 Transfer row found yet.")
    print("  Possible: not USDT TRC-20, wrong network, or not to our watched address.")
else:
    seen = set()
    for row in trc_rows:
        tid = str(row.get("transaction_id") or "")
        key = (tid, str(row.get("to")), str(row.get("value")), row.get("source"))
        if key in seen:
            continue
        seen.add(key)
        token = row.get("token_info") or {}
        decimals = int(token.get("decimals") if token.get("decimals") is not None else 6)
        amount = _amount_from_value(row.get("value"), decimals)
        to_addr = str(row.get("to") or "")
        from_addr = str(row.get("from") or "")
        contract = str(row.get("contract_address") or token.get("address") or "")
        print(
            f"  source={row.get('source')} amount≈{amount} "
            f"symbol={token.get('symbol') or '?'}\n"
            f"    from={base58_hint_from_hex(from_addr)}\n"
            f"    to  ={base58_hint_from_hex(to_addr)}\n"
            f"    contract={contract}"
        )

print("\n--- Verdict ---")
reasons: list[str] = []
ok_to_credit = False
target_wallet = None
target_row = None

if credit is not None and credit.credited:
    reasons.append("УЖЕ ЗАЧИСЛЕНО в CryptoDepositCredit (credited=True) — баланс должен был вырасти")
elif credit is not None and not credit.credited:
    reasons.append(f"Есть лог credit, но credited=False note={credit.note!r} — обрыв на зачислении")

if not wallets:
    reasons.append("Нет WatchedDepositWallet у трейдера — watcher некуда писать")

if found_on_wallets:
    target_wallet, target_row = found_on_wallets[0]
    token = target_row.get("token_info") or {}
    decimals = int(token.get("decimals") if token.get("decimals") is not None else 6)
    amount = _amount_from_value(target_row.get("value"), decimals)
    to_addr = str(target_row.get("to") or "").strip()
    ts_raw = target_row.get("block_timestamp")
    block_at = None
    try:
        if ts_raw:
            block_at = datetime.fromtimestamp(int(ts_raw) / 1000, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        block_at = None

    print(
        f"  MATCH wallet {target_wallet.address_public} amount={amount} "
        f"block_at={_msk(block_at)}"
    )
    if not target_wallet.enabled:
        reasons.append("wallet.enabled=False")
    if to_addr and to_addr != target_wallet.address_public:
        reasons.append(f"to={to_addr} != watched {target_wallet.address_public}")
    contract = str(token.get("address") or target_row.get("contract_address") or "")
    if contract and contract not in {USDT_CONTRACT, ""} and not contract.startswith("41"):
        # base58 contract mismatch
        if contract != USDT_CONTRACT:
            reasons.append(f"contract={contract} != USDT {USDT_CONTRACT} (не USDT?)")
    watch_from = target_wallet.watch_from
    if block_at is not None and watch_from is not None and block_at < watch_from:
        reasons.append(
            f"tx РАНЬШЕ watch_from: block={_msk(block_at)} < watch_from={_msk(watch_from)} "
            f"— watcher специально пропускает историю"
        )
    if credit is None and (not reasons or all("УЖЕ" not in r for r in reasons)):
        if target_wallet.enabled and amount > 0:
            if block_at is None or watch_from is None or block_at >= watch_from:
                ok_to_credit = True
                reasons.append("tx на watched-кошелёк, ещё не credited → можно APPLY=1")
            # else already added watch_from reason
else:
    # check if tx went to expected deposit address but not in recent 200
    expected = deposit_address_for_trader(trader)
    if expected:
        reasons.append(
            f"tx не найден в последних TRC-20 входящих на {expected} "
            f"(другой адрес / не USDT / слишком старый для лимита scan)"
        )
    else:
        reasons.append("deposit address пустой — проверьте TEAM_CRYPTO_DEPOSIT_WALLETS")

if info is None and raw_tx is None:
    reasons.append("TronGrid не знает tx — проверьте хеш на tronscan")

for i, r in enumerate(reasons, 1):
    print(f"  {i}. {r}")

if APPLY:
    print("\n--- APPLY ---")
    if credit is not None and credit.credited:
        print("skip: already credited")
    elif not found_on_wallets and target_wallet is None:
        # still try poll wallet — may pick up if within min_timestamp window
        if wallets:
            for w in wallets:
                stats = credit_incoming_for_wallet(w)
                print(f"poll {w.address_public}: {stats}")
        else:
            print("skip: no wallet to poll")
    else:
        w = target_wallet or wallets[0]
        # Force-credit this specific tx if present in chain row
        if target_row is not None and (credit is None or not credit.credited):
            token = target_row.get("token_info") or {}
            decimals = int(token.get("decimals") if token.get("decimals") is not None else 6)
            amount = _amount_from_value(target_row.get("value"), decimals)
            ts_raw = target_row.get("block_timestamp")
            try:
                block_at = (
                    datetime.fromtimestamp(int(ts_raw) / 1000, tz=dt_timezone.utc) if ts_raw else None
                )
            except (TypeError, ValueError, OSError):
                block_at = None
            chain = Balance.objects.filter(type=3).first()
            deposit_type = TransactionType.objects.filter(name="Deposit").first()
            if chain is None or deposit_type is None:
                print("ERROR: Balance type=3 or TransactionType Deposit missing")
            elif amount <= 0:
                print("ERROR: amount<=0")
            else:
                with db_transaction.atomic():
                    if credit is None:
                        credit = CryptoDepositCredit.objects.create(
                            wallet=w,
                            tx_id=tx_norm,
                            amount=amount,
                            from_address=str(target_row.get("from") or "")[:128],
                            block_at=block_at,
                            credited=False,
                            note="manual_diagnose",
                        )
                    if not credit.credited:
                        Transaction.create(
                            _from=chain,
                            _to=trader.balance_usdt,
                            _transaction_type=deposit_type,
                            value=amount,
                            _comment=f"Crypto deposit {tx_norm[:16]}",
                        )
                        credit.credited = True
                        credit.note = "credited_manual"
                        credit.amount = amount
                        credit.save(update_fields=["credited", "note", "amount"])
                        print(f"CREDITED {amount} USDT to {trader.user.username}")
        else:
            stats = credit_incoming_for_wallet(w)
            print(f"poll {w.address_public}: {stats}")
    trader.balance_usdt.refresh_from_db()
    print(f"balance_usdt now={trader.balance_usdt.amount}")
elif ok_to_credit:
    print("\nDRY-RUN — для зачисления:")
    print(
        f"  docker compose exec -T -e TX={tx_norm} -e TRADER={TRADER} -e APPLY=1 \\\n"
        f"    app python manage.py shell < titanpay/basics/shell_diagnose_crypto_deposit_tx.py"
    )
else:
    print("\nDRY-RUN — APPLY не предлагается автоматически (см. Verdict).")

print("\nDONE")
