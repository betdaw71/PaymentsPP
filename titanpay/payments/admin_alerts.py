"""Telegram-уведомления админу о балансах, payout, невыдаче PayPlat и низкой конверсии."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

LATCH_TTL = 60 * 60 * 24 * 90
CACHE_PREFIX = "admin_alert:"


def _dec(value, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
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


def notify_with_cooldown(key: str, text: str, cooldown_sec: int) -> bool:
    """Повтор не чаще cooldown_sec, пока проблема актуальна."""
    cache_key = f"{CACHE_PREFIX}cd:{key}"
    if cache.get(cache_key):
        return False
    if not send_admin_alert(text):
        return False
    cache.set(cache_key, 1, timeout=max(60, int(cooldown_sec)))
    return True


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
    melbet_max = _dec(getattr(settings, "ADMIN_ALERT_MELBET_KZT_MAX", -1_500_000), Decimal("-1500000"))
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
            "melbet_kzt_high",
            melbet_bal > melbet_max,
            (
                f"Melbet: KZT баланс {melbet_bal:.2f} ₸ выше {melbet_max:.0f} ₸.\n"
                "Нужно вывести / снизить баланс."
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


def _payplat_usernames() -> set[str]:
    from payments.payplat_client import payplat_trader_username

    names = {payplat_trader_username().strip().lower(), "payplat1"}
    return {n for n in names if n}


def note_payplat_issuance_failure(pay_in, *, reason: str | None = None) -> None:
    """Учесть отказ PayPlat выдать реквизит; при пачке отказов — алерт в Telegram."""
    window = _int(getattr(settings, "ADMIN_ALERT_PAYPLAT_FAIL_WINDOW_SEC", 300), 300)
    burst = _int(getattr(settings, "ADMIN_ALERT_PAYPLAT_FAIL_BURST", 5), 5)
    cooldown = _int(getattr(settings, "ADMIN_ALERT_PAYPLAT_COOLDOWN_SEC", 600), 600)
    if burst <= 0 or window <= 0:
        return

    bucket_key = f"{CACHE_PREFIX}payplat_fail_ts"
    now = time.time()
    stamps = cache.get(bucket_key) or []
    if not isinstance(stamps, list):
        stamps = []
    stamps = [float(ts) for ts in stamps if now - float(ts) <= window]
    stamps.append(now)
    cache.set(bucket_key, stamps, timeout=window + 60)

    if len(stamps) < burst:
        return

    merchant = getattr(getattr(pay_in, "merchant", None), "user", None)
    mname = getattr(merchant, "username", None) or "—"
    ps = getattr(getattr(pay_in, "payment_system", None), "name", None) or "—"
    amount = getattr(pay_in, "amount", None)
    why = (reason or "no_requisite").strip()[:120]
    text = (
        f"⚠ PayPlat: серия невыдач ({len(stamps)} за {window}с)\n"
        f"Порог: {burst} отказов\n"
        f"Последний: merchant={mname} ps={ps} amount={amount}\n"
        f"pay_in={getattr(pay_in, 'id', None)}\n"
        f"reason={why}\n"
        "Проверь каскад / баланс PayPlat / лимиты."
    )
    notify_with_cooldown("payplat_issuance_burst", text, cooldown)


def check_merchant_conversion_alerts() -> None:
    """Низкая issued→Success конверсия по мерчантам за скользящее окно."""
    from payments.models import PayIn

    window_min = _int(getattr(settings, "ADMIN_ALERT_CONV_WINDOW_MIN", 15), 15)
    min_created = _int(getattr(settings, "ADMIN_ALERT_CONV_MIN_CREATED", 20), 20)
    min_pct = _dec(getattr(settings, "ADMIN_ALERT_CONV_ISSUED_PCT_MIN", 15), Decimal("15"))
    cooldown = _int(getattr(settings, "ADMIN_ALERT_CONV_COOLDOWN_SEC", 900), 900)
    raw_merchants = str(getattr(settings, "ADMIN_ALERT_CONV_MERCHANTS", "melbet,mostbet") or "")
    merchants = [p.strip() for p in raw_merchants.split(",") if p.strip()]
    if window_min <= 0 or min_created <= 0:
        return

    from collections import defaultdict

    since = timezone.now() - timedelta(minutes=window_min)
    qs = PayIn.objects.filter(created_at__gte=since)
    if merchants:
        qs = qs.filter(merchant__user__username__in=merchants)

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"created": 0, "declined": 0, "success": 0})
    for pay in qs.select_related("status", "merchant__user").iterator(chunk_size=500):
        name = pay.merchant.user.username if pay.merchant_id and pay.merchant.user_id else ""
        if not name:
            continue
        cell = stats[name]
        cell["created"] += 1
        st = pay.status.name if pay.status_id else ""
        if st == "Declined":
            cell["declined"] += 1
        elif st == "Success":
            cell["success"] += 1

    for name, cell in stats.items():
        created = cell["created"]
        if created < min_created:
            continue
        issued = created - cell["declined"]
        if issued <= 0:
            continue
        pct = (Decimal(cell["success"]) * Decimal("100") / Decimal(issued)).quantize(Decimal("0.01"))
        if pct >= min_pct:
            continue
        text = (
            f"⚠ Низкая конверсия {name}\n"
            f"Окно: последние {window_min} мин\n"
            f"create={created}  issued={issued}  success={cell['success']}\n"
            f"iss→ok={pct}%  (порог {min_pct}%)\n"
            "Проверь выдачу PSP / каскад / дашборд."
        )
        notify_with_cooldown(f"conv_low:{name}", text, cooldown)


def check_ops_health_alerts() -> None:
    """Периодические ops-алерты (конверсия). PayPlat burst — event-driven."""
    try:
        check_merchant_conversion_alerts()
    except Exception as exc:
        logger.error("conversion alerts failed: %s", exc)
