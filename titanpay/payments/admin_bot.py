"""Inbound commands on the admin-alert Telegram bot: balances and expenses."""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from payments.admin_alerts import _bot_token, _chat_id, send_admin_alert

logger = logging.getLogger(__name__)
OFFSET_KEY = "admin_bot:update_offset"

HELP = (
    "Касса / балансы:\n"
    "касса\n"
    "обнови баланс провайдера payplat1 на 1234.56\n"
    "обнови баланс мерча mostbet на 2800\n"
    "пополни провайдера payplat1 100 комментарий\n"
    "пополни мерча mostbet 100 комментарий\n"
    "списать провайдера payplat1 50 комментарий\n"
    "списать мерча mostbet 50 комментарий\n"
    "расход 40 хостинг\n"
    "/help"
)


def _amount(raw: str) -> Decimal:
    return Decimal(str(raw).replace(",", ".").replace(" ", "")).quantize(Decimal("0.01"))


def parse_command(text: str) -> dict | None:
    if not text:
        return None
    raw = text.strip()
    low = raw.lower()
    if low in ("/help", "help", "помощь"):
        return {"op": "help"}
    if low in ("касса", "/касса", "cash"):
        return {"op": "cash"}
    m = re.match(
        r"^(?:обнови\s+баланс|обновить\s+баланс)\s+(провайдера|мерча|мерчанта)\s+(\S+)\s+на\s+([-\d.,]+)\s*$",
        raw,
        re.I,
    )
    if m:
        kind = "trader" if m.group(1).lower().startswith("провайд") else "merchant"
        return {"op": "set", "kind": kind, "username": m.group(2), "amount": _amount(m.group(3))}
    m = re.match(
        r"^(пополни|списать)\s+(провайдера|мерча|мерчанта)\s+(\S+)\s+([-\d.,]+)(?:\s+(.+))?$",
        raw,
        re.I,
    )
    if m:
        sign = 1 if m.group(1).lower().startswith("пополн") else -1
        kind = "trader" if m.group(2).lower().startswith("провайд") else "merchant"
        comment = (m.group(5) or "").strip() or "admin telegram"
        return {
            "op": "delta",
            "kind": kind,
            "username": m.group(3),
            "amount": _amount(m.group(4)) * sign,
            "comment": comment,
        }
    m = re.match(r"^расход\s+([-\d.,]+)\s+(.+)$", raw, re.I)
    if m:
        return {"op": "expense", "amount": _amount(m.group(1)), "comment": m.group(2).strip()}
    return None


def _merchant_usdt(username: str):
    from merchant.models import Merchant

    m = Merchant.objects.select_related("user", "balance").filter(user__username__iexact=username).first()
    if m is None or m.balance_id is None:
        raise ValueError(f"мерч {username} не найден или без USDT баланса")
    return m, m.balance


def _trader_usdt(username: str):
    from basics.models import Trader

    t = Trader.objects.select_related("user", "balance_usdt").filter(user__username__iexact=username).first()
    if t is None or t.balance_usdt_id is None:
        raise ValueError(f"провайдер/трейдер {username} не найден")
    return t, t.balance_usdt


def _move(balance, delta: Decimal, comment: str):
    from basics.models import Balance
    from trade.models import Transaction, TransactionType

    if delta == 0:
        return
    chain = Balance.objects.get(type=3)
    if delta > 0:
        Transaction.create(
            _from=chain,
            _to=balance,
            value=delta,
            _transaction_type=TransactionType.objects.get(name="Deposit"),
            _comment=comment,
        )
    else:
        Transaction.create(
            _from=balance,
            _to=chain,
            value=-delta,
            _transaction_type=TransactionType.objects.get(name="Charge"),
            _comment=comment,
        )


def handle_command(cmd: dict) -> str:
    if cmd["op"] == "help":
        return HELP
    if cmd["op"] == "cash":
        from basics.cash_register import format_telegram

        return format_telegram()
    if cmd["op"] == "expense":
        from basics.models import PlatformExpense

        if cmd["amount"] <= 0:
            return "сумма расхода должна быть > 0"
        PlatformExpense.objects.create(amount=cmd["amount"], comment=cmd["comment"][:256], source="telegram")
        return f"расход {cmd['amount']} USDT записан: {cmd['comment'][:80]}"
    if cmd["kind"] == "merchant":
        obj, bal = _merchant_usdt(cmd["username"])
        label = f"мерч {obj.user.username}"
    else:
        obj, bal = _trader_usdt(cmd["username"])
        label = f"провайдер {obj.user.username}"
    before = Decimal(str(bal.amount))
    with transaction.atomic():
        if cmd["op"] == "set":
            delta = cmd["amount"] - before
            _move(bal, delta, f"admin set {label} to {cmd['amount']}")
        else:
            _move(bal, cmd["amount"], f"admin {cmd['comment']}"[:256])
        bal.refresh_from_db()
    return f"{label}: {before} → {bal.amount} USDT"


def poll_admin_bot() -> int:
    token = _bot_token()
    allowed = _chat_id()
    if not token or not allowed:
        return 0
    offset = cache.get(OFFSET_KEY) or 0
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"timeout": 0, "offset": offset, "allowed_updates": ["message"]},
            timeout=20,
        )
        payload = response.json()
    except Exception as exc:
        logger.error("admin bot getUpdates failed: %s", exc)
        return 0
    if not payload.get("ok"):
        logger.error("admin bot getUpdates rejected: %s", payload)
        return 0
    handled = 0
    last_id = offset
    for upd in payload.get("result") or []:
        last_id = max(last_id, int(upd.get("update_id", 0)) + 1)
        msg = upd.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id") or "")
        if chat != str(allowed):
            continue
        text = msg.get("text") or ""
        try:
            cmd = parse_command(text)
            if cmd is None:
                continue
            reply = handle_command(cmd)
        except (InvalidOperation, ValueError) as exc:
            reply = f"ошибка: {exc}"
        except Exception:
            logger.exception("admin bot command failed: %s", text)
            reply = "ошибка выполнения"
        send_admin_alert(reply)
        handled += 1
    if last_id != offset:
        cache.set(OFFSET_KEY, last_id, timeout=60 * 60 * 24 * 30)
    return handled
