"""Telegram-уведомления админу о балансах мерчантов, payout и выводах."""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

LATCH_TTL = 60 * 60 * 24 * 90
CACHE_PREFIX = "admin_alert:"


def _dec(value, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _bot_token() -> str:
    return (
        getattr(settings, "ADMIN_ALERT_BOT_TOKEN", "")
        or getattr(settings, "APPEAL_TELEGRAM_BOT_TOKEN", "")
        or ""
    )


def _chat_id() -> str:
    return str(getattr(settings, "ADMIN_ALERT_CHAT_ID", "") or "").strip()


def send_admin_alert(text: str) -> bool:
    token = _bot_token()
    chat_id = _chat_id()
    if not token or not chat_id or not text:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        payload = response.json()
    except Exception as exc:
        logger.error("admin alert telegram failed: %s", exc)
        return False
    if not payload.get("ok"):
        logger.error("admin alert telegram rejected: %s", payload)
        return False
    return True


def notify_threshold_once(key: str, active: bool, text: str) -> bool:
    """Отправить текст один раз, пока условие истинно; сброс когда условие ложно."""
    cache_key = f"{CACHE_PREFIX}{key}"
    already = bool(cache.get(cache_key))
    if active:
        if already:
            return False
        if not send_admin_alert(text):
            return False
        cache.set(cache_key, 1, timeout=LATCH_TTL)
        return True
    if already:
        cache.delete(cache_key)
    return False


def _merchant(username: str):
    from merchant.models import Merchant

    return (
        Merchant.objects.select_related("user", "balance", "balance_kzt")
        .filter(user__username__iexact=username)
        .first()
    )


def _usdt(merchant) -> Decimal | None:
    if merchant is None or merchant.balance_id is None:
        return None
    return Decimal(str(merchant.balance.amount))


def _kzt(merchant) -> Decimal | None:
    if merchant is None or merchant.balance_kzt_id is None:
        return None
    return Decimal(str(merchant.balance_kzt.amount))


def check_merchant_balance_alerts() -> None:
    panda_max = _dec(getattr(settings, "ADMIN_ALERT_PANDAPAY_MAX", 2800), Decimal("2800"))
    aggre_max = _dec(getattr(settings, "ADMIN_ALERT_AGGREPAY_MAX", 4000), Decimal("4000"))
    melbet_min = _dec(getattr(settings, "ADMIN_ALERT_MELBET_KZT_MIN", 1_500_000), Decimal("1500000"))
    mostbet_min = _dec(getattr(settings, "ADMIN_ALERT_MOSTBET_MIN", 1000), Decimal("1000"))

    panda = _merchant(getattr(settings, "ADMIN_ALERT_PANDAPAY_USER", "pandapay"))
    panda_bal = _usdt(panda)
    if panda_bal is not None:
        notify_threshold_once(
            "pandapay_usdt_high",
            panda_bal > panda_max,
            (
                f"Panda Pay: баланс {panda_bal:.2f} USDT выше {panda_max:.0f}.\n"
                "Нужно вывести / снизить баланс."
            ),
        )

    aggre = _merchant(getattr(settings, "ADMIN_ALERT_AGGREPAY_USER", "aggrepay"))
    aggre_bal = _usdt(aggre)
    if aggre_bal is not None:
        notify_threshold_once(
            "aggrepay_usdt_high",
            aggre_bal > aggre_max,
            (
                f"Aggrepay: баланс {aggre_bal:.2f} USDT выше {aggre_max:.0f}.\n"
                "Нужно вывести / снизить баланс."
            ),
        )

    melbet = _merchant(getattr(settings, "ADMIN_ALERT_MELBET_USER", "melbet"))
    melbet_bal = _kzt(melbet)
    if melbet_bal is not None:
        notify_threshold_once(
            "melbet_kzt_low",
            melbet_bal < melbet_min,
            (
                f"Melbet: KZT баланс {melbet_bal:.2f} ₸ меньше {melbet_min:.0f} ₸.\n"
                "Нужно пополнить тенге."
            ),
        )

    mostbet = _merchant(getattr(settings, "ADMIN_ALERT_MOSTBET_USER", "mostbet"))
    mostbet_bal = _usdt(mostbet)
    if mostbet_bal is not None:
        notify_threshold_once(
            "mostbet_usdt_low",
            mostbet_bal < mostbet_min,
            (
                f"Mostbet: баланс {mostbet_bal:.2f} USDT меньше {mostbet_min:.0f}.\n"
                "Нужно пополнить."
            ),
        )


def notify_payout_created(pay_out) -> None:
    merchant = getattr(pay_out, "merchant", None)
    username = getattr(getattr(merchant, "user", None), "username", None) or "—"
    amount = getattr(pay_out, "amount", None)
    currency = getattr(getattr(pay_out, "currency", None), "symbol", None) or ""
    ps = getattr(getattr(pay_out, "payment_system", None), "name", None) or "—"
    moid = getattr(pay_out, "merchant_order_id", None) or "—"
    send_admin_alert(
        "Payout создан\n"
        f"Мерчант: {username}\n"
        f"Сумма: {amount} {currency}\n"
        f"Метод: {ps}\n"
        f"merchant_order_id: {moid}\n"
        f"id: {pay_out.id}"
    )


def notify_withdrawal_created(request) -> None:
    from merchant.models import Merchant

    user = getattr(request, "from_user", None)
    if user is None or not Merchant.objects.filter(user_id=user.id).exists():
        return
    username = getattr(user, "username", None) or "—"
    send_admin_alert(
        "Заявка на вывод средств\n"
        f"Мерчант: {username}\n"
        f"Сумма: {request.amount} USDT\n"
        f"Адрес: {request.address_to}\n"
        f"id: {request.id}"
    )


def on_payout_saved(sender, instance, created, **kwargs):
    if not created:
        return

    def _send():
        try:
            notify_payout_created(instance)
        except Exception as exc:
            logger.error("admin alert payout failed: %s", exc)

    transaction.on_commit(_send)
