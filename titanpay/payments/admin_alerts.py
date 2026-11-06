"""Telegram-уведомления админу: балансы, payout, PayPlat, конверсия (мерч/PSP/рек), апелляции."""
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


def _appeal_closure_stats(since, until, merchants: list[str]) -> dict[str, dict[str, int]]:
    """Success за [since, until) и сколько из них закрыты через approved-апелляцию."""
    from collections import defaultdict

    from appeals.models import PayInAppeal, PayInAppealStatus
    from payments.models import PayIn

    qs = PayIn.objects.filter(
        status__name="Success",
        updated_at__gte=since,
        updated_at__lt=until,
    ).select_related("merchant__user")
    if merchants:
        qs = qs.filter(merchant__user__username__in=merchants)

    rows = [(p.id, p.merchant.user.username if p.merchant_id and p.merchant.user_id else "") for p in qs.iterator(chunk_size=500)]
    pay_ids = [pid for pid, _ in rows]
    approved_ids = set(
        PayInAppeal.objects.filter(
            pay_in_id__in=pay_ids,
            status=PayInAppealStatus.APPROVED,
        )
        .values_list("pay_in_id", flat=True)
        .distinct()
    ) if pay_ids else set()

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "appeal_ok": 0})
    for pid, name in rows:
        if not name:
            continue
        cell = stats[name]
        cell["success"] += 1
        if pid in approved_ids:
            cell["appeal_ok"] += 1
    return stats


def check_appeal_closure_alerts() -> None:
    """Рост доли Success, закрытых через одобренную апелляцию (апелляционное закрытие)."""
    window_min = _int(getattr(settings, "ADMIN_ALERT_APPEAL_WINDOW_MIN", 60), 60)
    min_success = _int(getattr(settings, "ADMIN_ALERT_APPEAL_MIN_SUCCESS", 8), 8)
    min_appeal = _int(getattr(settings, "ADMIN_ALERT_APPEAL_MIN_APPROVED", 2), 2)
    max_pct = _dec(getattr(settings, "ADMIN_ALERT_APPEAL_PCT_MAX", 20), Decimal("20"))
    growth_pp = _dec(getattr(settings, "ADMIN_ALERT_APPEAL_GROWTH_PP", 10), Decimal("10"))
    cooldown = _int(getattr(settings, "ADMIN_ALERT_APPEAL_COOLDOWN_SEC", 1800), 1800)
    raw_merchants = str(
        getattr(settings, "ADMIN_ALERT_APPEAL_MERCHANTS", "melbet,mostbet") or ""
    )
    merchants = [p.strip() for p in raw_merchants.split(",") if p.strip()]
    if window_min <= 0 or min_success <= 0:
        return

    now = timezone.now()
    cur_since = now - timedelta(minutes=window_min)
    prev_since = cur_since - timedelta(minutes=window_min)

    current = _appeal_closure_stats(cur_since, now, merchants)
    previous = _appeal_closure_stats(prev_since, cur_since, merchants)

    for name, cell in current.items():
        success = cell["success"]
        appeal_ok = cell["appeal_ok"]
        if success < min_success or appeal_ok < min_appeal:
            continue
        pct = (Decimal(appeal_ok) * Decimal("100") / Decimal(success)).quantize(Decimal("0.01"))

        prev = previous.get(name) or {"success": 0, "appeal_ok": 0}
        prev_success = prev["success"]
        prev_pct = None
        if prev_success >= min_success:
            prev_pct = (
                Decimal(prev["appeal_ok"]) * Decimal("100") / Decimal(prev_success)
            ).quantize(Decimal("0.01"))

        high = pct >= max_pct
        grew = prev_pct is not None and (pct - prev_pct) >= growth_pp
        if not high and not grew:
            continue

        reasons = []
        if high:
            reasons.append(f"≥ порога {max_pct}%")
        if grew:
            reasons.append(f"рост +{(pct - prev_pct):.2f} п.п. (порог +{growth_pp})")
        prev_line = (
            f"Пред. окно: appeal={prev['appeal_ok']}/{prev_success} = {prev_pct}%\n"
            if prev_pct is not None
            else "Пред. окно: мало Success для сравнения\n"
        )
        text = (
            f"⚠ Рост апелляционного закрытия {name}\n"
            f"Окно: последние {window_min} мин\n"
            f"Success={success}  через апелляцию={appeal_ok}  "
            f"appeal%= {pct}%\n"
            f"{prev_line}"
            f"Триггер: {', '.join(reasons)}\n"
            "Проверь качество реквизитов / чеки / дашборд."
        )
        notify_with_cooldown(f"appeal_closure_high:{name}", text, cooldown)


def _provider_of(pay_in) -> str:
    order = getattr(pay_in, "order", None)
    if order is None or not getattr(order, "payment_details_id", None):
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username or "(no_trader)"
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def _requisite_fingerprint(pay_in) -> str:
    """Короткий ключ реквизита: card:*XXXX или phone / stub."""
    order = getattr(pay_in, "order", None)
    detail = getattr(order, "payment_details", None) if order is not None else None
    if detail is None:
        return "(none)"
    card = (getattr(detail, "card_number", None) or "").strip()
    digits = "".join(c for c in card if c.isdigit())
    if len(digits) >= 4:
        return f"card:*{digits[-4:]}"
    dep = (getattr(detail, "deposit_number", None) or "").strip()
    if dep:
        return f"dep:*{dep[-4:]}"
    return f"pd:{detail.id}"


def check_psp_merchant_conversion_alerts() -> None:
    """PSP с iss→ok сильно ниже средней конверсии того же мерчанта (или абсолютный пол)."""
    from collections import defaultdict

    from payments.models import PayIn

    window_min = _int(getattr(settings, "ADMIN_ALERT_PSP_CONV_WINDOW_MIN", 60), 60)
    min_issued = _int(getattr(settings, "ADMIN_ALERT_PSP_CONV_MIN_ISSUED", 8), 8)
    abs_min = _dec(getattr(settings, "ADMIN_ALERT_PSP_CONV_ABS_PCT_MIN", 10), Decimal("10"))
    drop_pp = _dec(getattr(settings, "ADMIN_ALERT_PSP_CONV_DROP_PP", 12), Decimal("12"))
    cooldown = _int(getattr(settings, "ADMIN_ALERT_PSP_CONV_COOLDOWN_SEC", 1200), 1200)
    raw_merchants = str(
        getattr(settings, "ADMIN_ALERT_CONV_MERCHANTS", "melbet,mostbet,pandapay,aggrepay") or ""
    )
    merchants = [p.strip() for p in raw_merchants.split(",") if p.strip()]
    if window_min <= 0 or min_issued <= 0:
        return

    since = timezone.now() - timedelta(minutes=window_min)
    qs = PayIn.objects.filter(created_at__gte=since).select_related(
        "status",
        "merchant__user",
        "order__payment_details__group__trader__user",
    )
    if merchants:
        qs = qs.filter(merchant__user__username__in=merchants)

    by_m: dict[str, dict[str, int]] = defaultdict(lambda: {"created": 0, "declined": 0, "success": 0})
    by_mp: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"created": 0, "declined": 0, "success": 0}
    )

    for pay in qs.iterator(chunk_size=400):
        mname = pay.merchant.user.username if pay.merchant_id and pay.merchant.user_id else ""
        if not mname:
            continue
        st = pay.status.name if pay.status_id else ""
        psp = _provider_of(pay)
        for cell in (by_m[mname], by_mp[(mname, psp)]):
            cell["created"] += 1
            if st == "Declined":
                cell["declined"] += 1
            elif st == "Success":
                cell["success"] += 1

    for (mname, psp), cell in by_mp.items():
        created = cell["created"]
        declined = cell["declined"]
        success = cell["success"]
        issued = created - declined
        if issued < min_issued:
            continue
        if psp in {"(no_req)", "(no_trader)"}:
            continue
        psp_pct = (Decimal(success) * Decimal("100") / Decimal(issued)).quantize(Decimal("0.01"))
        mcell = by_m[mname]
        m_issued = mcell["created"] - mcell["declined"]
        m_pct = (
            (Decimal(mcell["success"]) * Decimal("100") / Decimal(m_issued)).quantize(Decimal("0.01"))
            if m_issued > 0
            else Decimal("0")
        )
        below_abs = psp_pct < abs_min
        below_merchant = m_issued >= min_issued and psp_pct + drop_pp < m_pct
        if not below_abs and not below_merchant:
            continue
        reasons = []
        if below_abs:
            reasons.append(f"ниже абсолютного пола {abs_min}%")
        if below_merchant:
            reasons.append(f"ниже средней мерча на ≥{drop_pp} п.п.")
        text = (
            f"⚠ Низкая конверсия реквизитов PSP\n"
            f"Мерчант: {mname}  (средняя iss→ok={m_pct}%  issued={m_issued})\n"
            f"Провайдер: {psp}\n"
            f"Окно: {window_min} мин\n"
            f"У PSP: issued={issued}  success={success}  iss→ok={psp_pct}%\n"
            f"Триггер: {', '.join(reasons)}\n"
            "Проверь качество реквизитов / отключи PSP в каскаде."
        )
        notify_with_cooldown(f"psp_conv_low:{mname}:{psp}", text, cooldown)


def check_requisite_conversion_alerts() -> None:
    """Реквизит (card fingerprint) с низкой iss→ok + провайдер и его конверсия в системе."""
    from collections import defaultdict

    from payments.models import PayIn

    window_h = _int(getattr(settings, "ADMIN_ALERT_REQ_CONV_WINDOW_H", 24), 24)
    min_issued = _int(getattr(settings, "ADMIN_ALERT_REQ_CONV_MIN_ISSUED", 6), 6)
    abs_min = _dec(getattr(settings, "ADMIN_ALERT_REQ_CONV_ABS_PCT_MIN", 8), Decimal("8"))
    cooldown = _int(getattr(settings, "ADMIN_ALERT_REQ_CONV_COOLDOWN_SEC", 3600), 3600)
    raw_merchants = str(
        getattr(settings, "ADMIN_ALERT_CONV_MERCHANTS", "melbet,mostbet,pandapay,aggrepay") or ""
    )
    merchants = [p.strip() for p in raw_merchants.split(",") if p.strip()]
    if window_h <= 0 or min_issued <= 0:
        return

    since = timezone.now() - timedelta(hours=window_h)
    qs = PayIn.objects.filter(created_at__gte=since).select_related(
        "status",
        "merchant__user",
        "order__payment_details__group__trader__user",
    )
    if merchants:
        qs = qs.filter(merchant__user__username__in=merchants)

    by_req: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"created": 0, "declined": 0, "success": 0, "merchants": set()}
    )
    by_psp: dict[str, dict[str, int]] = defaultdict(lambda: {"created": 0, "declined": 0, "success": 0})

    for pay in qs.iterator(chunk_size=400):
        st = pay.status.name if pay.status_id else ""
        psp = _provider_of(pay)
        fp = _requisite_fingerprint(pay)
        mname = pay.merchant.user.username if pay.merchant_id and pay.merchant.user_id else ""
        cell = by_req[(psp, fp)]
        cell["created"] += 1
        if mname:
            cell["merchants"].add(mname)
        if st == "Declined":
            cell["declined"] += 1
        elif st == "Success":
            cell["success"] += 1
        pcell = by_psp[psp]
        pcell["created"] += 1
        if st == "Declined":
            pcell["declined"] += 1
        elif st == "Success":
            pcell["success"] += 1

    for (psp, fp), cell in by_req.items():
        issued = cell["created"] - cell["declined"]
        if issued < min_issued or psp in {"(no_req)", "(no_trader)"}:
            continue
        req_pct = (Decimal(cell["success"]) * Decimal("100") / Decimal(issued)).quantize(Decimal("0.01"))
        if req_pct >= abs_min:
            continue
        pcell = by_psp[psp]
        p_issued = pcell["created"] - pcell["declined"]
        psp_pct = (
            (Decimal(pcell["success"]) * Decimal("100") / Decimal(p_issued)).quantize(Decimal("0.01"))
            if p_issued > 0
            else Decimal("0")
        )
        merch_s = ",".join(sorted(cell["merchants"])[:5]) or "—"
        text = (
            f"⚠ Реквизит с низкой конверсией\n"
            f"Реквизит: {fp}\n"
            f"Провайдер: {psp}  (его iss→ok за {window_h}ч = {psp_pct}%  issued={p_issued})\n"
            f"По реквизиту: issued={issued}  success={cell['success']}  iss→ok={req_pct}%\n"
            f"Мерчанты: {merch_s}\n"
            f"Порог реквизита: {abs_min}%\n"
            "Имеет смысл исключить реквизит / снизить долю PSP."
        )
        notify_with_cooldown(f"req_conv_low:{psp}:{fp}", text, cooldown)


def check_ops_health_alerts() -> None:
    """Периодические ops-алерты (конверсия, PSP×мерч, реквизиты, апелляции)."""
    try:
        check_merchant_conversion_alerts()
    except Exception as exc:
        logger.error("conversion alerts failed: %s", exc)
    try:
        check_psp_merchant_conversion_alerts()
    except Exception as exc:
        logger.error("psp×merchant conversion alerts failed: %s", exc)
    try:
        check_requisite_conversion_alerts()
    except Exception as exc:
        logger.error("requisite conversion alerts failed: %s", exc)
    try:
        check_appeal_closure_alerts()
    except Exception as exc:
        logger.error("appeal closure alerts failed: %s", exc)
