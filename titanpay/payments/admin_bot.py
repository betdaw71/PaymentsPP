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
    "/lookup <ID заявки>\n"
    "Перерасчёт заявки приходит сюда кнопками Подтвердить / Отклонить.\n"
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
    lookup = re.match(r"^/lookup(?:@\w+)?(?:\s+([\s\S]+))?$", raw, re.I)
    if lookup:
        query = (lookup.group(1) or "").strip()
        if not query:
            return {"op": "lookup_help"}
        return {"op": "lookup", "query": query}
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


def _format_lookup(query: str) -> str:
    from appeals.id_resolve import resolve_pay_in_from_message
    from appeals.views import _collect_deal_ids

    resolved = resolve_pay_in_from_message(query)
    if not resolved.ok or resolved.pay_in is None:
        return resolved.error_message or "Заявка не найдена."
    data = _collect_deal_ids(resolved.pay_in)
    lines = ["Все ID по сделке"]
    labels = (
        ("pay_in_id", "PayIn"),
        ("in_order_id", "InOrder"),
        ("merchant_order_id", "Merchant order"),
        ("status", "PayIn status"),
        ("in_order_status", "InOrder status"),
        ("amount", "Amount"),
        ("merchant", "Merchant"),
        ("trader", "Trader"),
    )
    for key, label in labels:
        val = data.get(key)
        if val:
            lines.append(f"{label}: {val}")
    for key, val in data.items():
        if key.endswith("_external_id") and val:
            lines.append(f"{key}: {val}")
        elif key.endswith("_provider_id") and val:
            lines.append(f"{key}: {val}")
    return "\n".join(lines)


def handle_command(cmd: dict) -> str:
    if cmd["op"] == "help":
        return HELP
    if cmd["op"] == "lookup_help":
        return "Использование: /lookup <ID заявки>"
    if cmd["op"] == "lookup":
        return _format_lookup(cmd["query"])
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


def _handle_recalc_callback(callback: dict, allowed_chat: str) -> bool:
    from payments.recalc_confirm import (
        answer_callback,
        apply_recalc_decision,
        edit_admin_message,
        parse_recalc_callback,
    )

    callback_id = str(callback.get("id") or "")
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    parsed = parse_recalc_callback(callback.get("data") or "")
    if parsed is None:
        return False
    if chat_id != str(allowed_chat):
        answer_callback(callback_id, "Нет доступа")
        return False
    side, order_id, approve = parsed
    try:
        result = apply_recalc_decision(side, order_id, approve)
    except Exception:
        logger.exception("recalc confirm failed order=%s", order_id)
        result = "Ошибка выполнения"
    answer_callback(callback_id, result)
    original = message.get("text") or ""
    edit_admin_message(chat_id, message.get("message_id"), f"{original}\n\nИтог: {result}")
    return True


def poll_admin_bot() -> int:
    token = _bot_token()
    allowed = _chat_id()
    if not token or not allowed:
        return 0
    offset = cache.get(OFFSET_KEY) or 0
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"timeout": 0, "offset": offset, "allowed_updates": ["message", "callback_query"]},
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
        callback = upd.get("callback_query")
        if callback:
            if _handle_recalc_callback(callback, allowed):
                handled += 1
            continue
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
