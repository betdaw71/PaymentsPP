"""Низкочувствительный сторож реквизитов живых трейдеров.

Выключает карту только когда она сама по себе не платит, а соседние карты того же
трейдера и остальные карты того же мерчанта в том же окне платят. Спам мерчанта
(клиент с несколькими заявками и нулём оплат) из оценки вычитается. Если на этой
же карте другой мерчант получает оплаты, карта не трогается: просел поток, не реквизит.

Пороги высокие специально. Одно плохое утро или мёртвая целиком команда карту не снимут.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("In Progress", "Pending")


@dataclass(frozen=True)
class GuardConfig:
    min_issued: int = 25
    max_pct: Decimal = Decimal("5")
    half_min_issued: int = 8
    half_max_pct: Decimal = Decimal("10")
    clean_min_issued: int = 12
    clean_max_pct: Decimal = Decimal("5")
    peer_min_issued: int = 20
    peer_min_cards: int = 2
    peer_min_pct: Decimal = Decimal("15")
    merchant_min_issued: int = 25
    merchant_min_pct: Decimal = Decimal("12")
    other_merchant_min_issued: int = 8
    other_merchant_save_pct: Decimal = Decimal("15")
    other_merchant_save_ok: int = 3
    spam_client_min: int = 5


@dataclass(frozen=True)
class Sample:
    detail_id: str
    trader: str
    merchant: str
    client: str
    success: bool
    recent: bool
    active: bool
    group_id: str
    label: str


@dataclass(frozen=True)
class BlockDecision:
    detail_id: str
    group_id: str
    trader: str
    merchant: str
    label: str
    raw_issued: int
    raw_ok: int
    clean_issued: int
    clean_ok: int
    peer_issued: int
    peer_ok: int
    merchant_issued: int
    merchant_ok: int


def _pct_at_most(ok: int, issued: int, max_pct: Decimal) -> bool:
    if issued <= 0:
        return False
    return Decimal(ok) * Decimal(100) <= Decimal(max_pct) * Decimal(issued)


def _pct_at_least(ok: int, issued: int, min_pct: Decimal) -> bool:
    if issued <= 0:
        return False
    return Decimal(ok) * Decimal(100) >= Decimal(min_pct) * Decimal(issued)


def _spam_clients(samples: list[Sample], cfg: GuardConfig) -> set[tuple[str, str]]:
    totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for sample in samples:
        client = sample.client or ""
        if not client or client.startswith("row:"):
            continue
        box = totals[(sample.merchant, client)]
        box[0] += 1
        if sample.success:
            box[1] += 1
    return {
        key
        for key, (issued, ok) in totals.items()
        if issued >= cfg.spam_client_min and ok == 0
    }


def _is_spam(sample: Sample, spam: set[tuple[str, str]]) -> bool:
    return (sample.merchant, sample.client) in spam


def judge_detail(
    detail_id: str,
    samples: list[Sample],
    cfg: GuardConfig,
    spam: set[tuple[str, str]],
) -> BlockDecision | str:
    """'block' decision or a skip reason."""
    mine = [s for s in samples if s.detail_id == detail_id]
    if not mine or not any(s.active for s in mine):
        return "inactive"
    counts: dict[str, int] = defaultdict(int)
    for sample in mine:
        counts[sample.merchant] += 1
    dominant = max(counts, key=lambda name: (counts[name], name))
    dom = [s for s in mine if s.merchant == dominant]
    raw_ok = sum(1 for s in dom if s.success)
    raw_issued = len(dom)
    if raw_issued < cfg.min_issued:
        return "thin"
    if not _pct_at_most(raw_ok, raw_issued, cfg.max_pct):
        return "rate"
    for recent in (False, True):
        half = [s for s in dom if s.recent is recent]
        half_ok = sum(1 for s in half if s.success)
        if len(half) < cfg.half_min_issued:
            return "half-thin"
        if not _pct_at_most(half_ok, len(half), cfg.half_max_pct):
            return "half-paid"
    clean = [s for s in dom if not _is_spam(s, spam)]
    clean_ok = sum(1 for s in clean if s.success)
    if len(clean) < cfg.clean_min_issued:
        return "spam"
    if not _pct_at_most(clean_ok, len(clean), cfg.clean_max_pct):
        return "clean-paid"

    by_other: dict[str, list[Sample]] = defaultdict(list)
    for sample in mine:
        if sample.merchant == dominant or _is_spam(sample, spam):
            continue
        by_other[sample.merchant].append(sample)
    for deals in by_other.values():
        ok = sum(1 for s in deals if s.success)
        if ok >= cfg.other_merchant_save_ok:
            return "other-merchant"
        if len(deals) >= cfg.other_merchant_min_issued and _pct_at_least(
            ok, len(deals), cfg.other_merchant_save_pct
        ):
            return "other-merchant"

    trader = mine[0].trader
    peers = [
        s
        for s in samples
        if s.trader == trader
        and s.detail_id != detail_id
        and s.merchant == dominant
        and not _is_spam(s, spam)
    ]
    peer_cards = {s.detail_id for s in peers}
    peer_ok = sum(1 for s in peers if s.success)
    if len(peer_cards) < cfg.peer_min_cards or len(peers) < cfg.peer_min_issued:
        return "no-peers"
    if not _pct_at_least(peer_ok, len(peers), cfg.peer_min_pct):
        return "peers-low"

    others = [
        s
        for s in samples
        if s.merchant == dominant and s.detail_id != detail_id and not _is_spam(s, spam)
    ]
    merch_ok = sum(1 for s in others if s.success)
    if len(others) < cfg.merchant_min_issued:
        return "merchant-thin"
    if not _pct_at_least(merch_ok, len(others), cfg.merchant_min_pct):
        return "merchant-low"

    return BlockDecision(
        detail_id=detail_id,
        group_id=mine[0].group_id,
        trader=trader,
        merchant=dominant,
        label=mine[0].label,
        raw_issued=raw_issued,
        raw_ok=raw_ok,
        clean_issued=len(clean),
        clean_ok=clean_ok,
        peer_issued=len(peers),
        peer_ok=peer_ok,
        merchant_issued=len(others),
        merchant_ok=merch_ok,
    )


def decide_blocks(samples: list[Sample], cfg: GuardConfig | None = None) -> list[BlockDecision]:
    cfg = cfg or GuardConfig()
    spam = _spam_clients(samples, cfg)
    detail_ids = []
    seen = set()
    for sample in samples:
        if sample.detail_id in seen:
            continue
        seen.add(sample.detail_id)
        detail_ids.append(sample.detail_id)
    blocks: list[BlockDecision] = []
    for detail_id in detail_ids:
        verdict = judge_detail(detail_id, samples, cfg, spam)
        if isinstance(verdict, BlockDecision):
            blocks.append(verdict)
    return blocks


def guard_config_from_settings() -> GuardConfig:
    from django.conf import settings

    def _int(name: str, default: int) -> int:
        try:
            return int(getattr(settings, name, default))
        except (TypeError, ValueError):
            return default

    def _dec(name: str, default: str) -> Decimal:
        try:
            return Decimal(str(getattr(settings, name, default)))
        except Exception:
            return Decimal(default)

    return GuardConfig(
        min_issued=_int("REQ_CONV_GUARD_MIN_ISSUED", 25),
        max_pct=_dec("REQ_CONV_GUARD_MAX_PCT", "5"),
        half_min_issued=_int("REQ_CONV_GUARD_HALF_MIN_ISSUED", 8),
        half_max_pct=_dec("REQ_CONV_GUARD_HALF_MAX_PCT", "10"),
        clean_min_issued=_int("REQ_CONV_GUARD_CLEAN_MIN_ISSUED", 12),
        clean_max_pct=_dec("REQ_CONV_GUARD_CLEAN_MAX_PCT", "5"),
        peer_min_issued=_int("REQ_CONV_GUARD_PEER_MIN_ISSUED", 20),
        peer_min_cards=_int("REQ_CONV_GUARD_PEER_MIN_CARDS", 2),
        peer_min_pct=_dec("REQ_CONV_GUARD_PEER_MIN_PCT", "15"),
        merchant_min_issued=_int("REQ_CONV_GUARD_MERCHANT_MIN_ISSUED", 25),
        merchant_min_pct=_dec("REQ_CONV_GUARD_MERCHANT_MIN_PCT", "12"),
        other_merchant_min_issued=_int("REQ_CONV_GUARD_OTHER_MERCHANT_MIN_ISSUED", 8),
        other_merchant_save_pct=_dec("REQ_CONV_GUARD_OTHER_MERCHANT_SAVE_PCT", "15"),
        other_merchant_save_ok=_int("REQ_CONV_GUARD_OTHER_MERCHANT_SAVE_OK", 3),
        spam_client_min=_int("REQ_CONV_GUARD_SPAM_CLIENT_MIN", 5),
    )


def guard_enabled() -> bool:
    from django.conf import settings

    raw = getattr(settings, "REQ_CONV_GUARD_ENABLED", "1")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _mask(card: str) -> str:
    digits = "".join(ch for ch in (card or "") if ch.isdigit())
    if len(digits) >= 4:
        return "*" + digits[-4:]
    return "noreq"


def load_samples(*, now=None, window_hours: int | None = None) -> list[Sample]:
    from django.conf import settings

    from payments.models import PayIn
    from payments.psp_payin import psp_trader_usernames

    if window_hours is None:
        try:
            window_hours = int(getattr(settings, "REQ_CONV_GUARD_WINDOW_H", 72))
        except (TypeError, ValueError):
            window_hours = 72
    window_hours = max(24, min(24 * 14, window_hours))
    now = now or timezone.now()
    since = now - timedelta(hours=window_hours)
    mid = since + (now - since) / 2
    psp = {name.lower() for name in psp_trader_usernames() if name}
    samples: list[Sample] = []
    qs = (
        PayIn.objects.filter(created_at__gte=since)
        .exclude(status__name="Declined")
        .exclude(status__name__in=OPEN_STATUSES)
        .values_list(
            "id",
            "created_at",
            "status__name",
            "client__client_id",
            "merchant__user__username",
            "order__payment_details_id",
            "order__payment_details__status",
            "order__payment_details__card_number",
            "order__payment_details__group_id",
            "order__payment_details__group__status",
            "order__payment_details__group__owner",
            "order__payment_details__group__trader__user__username",
        )
    )
    for (
        payin_id,
        created,
        status,
        client_ext,
        merchant,
        detail_id,
        detail_status,
        card,
        group_id,
        group_status,
        owner,
        trader,
    ) in qs.iterator(chunk_size=500):
        trader_name = (trader or "").strip()
        if not detail_id or not trader_name or trader_name.lower() in psp:
            continue
        ext = (client_ext or "").strip()
        if not ext:
            ext = f"row:{payin_id}"
        owner_s = (owner or "").strip()
        label = f"{trader_name} {_mask(card or '')} {owner_s[:18]}".strip()
        samples.append(
            Sample(
                detail_id=str(detail_id),
                trader=trader_name,
                merchant=(merchant or "").strip() or "-",
                client=ext,
                success=(status == "Success"),
                recent=created >= mid,
                active=(detail_status == 1 and group_status == 1),
                group_id=str(group_id or ""),
                label=label,
            )
        )
    return samples


def _alert(decision: BlockDecision, window_hours: int) -> None:
    from payments.admin_alerts import notify_with_cooldown

    raw_pct = (Decimal(decision.raw_ok) * Decimal(100) / Decimal(decision.raw_issued)).quantize(Decimal("0.1"))
    text = (
        "Реквизит выключен: конверсия карты ниже рабочих реквизитов\n"
        f"{decision.label}\n"
        f"Мерчант {decision.merchant}: {decision.raw_ok}/{decision.raw_issued} ({raw_pct}%) за {window_hours}ч\n"
        f"Без спам-клиентов: {decision.clean_ok}/{decision.clean_issued}\n"
        f"Другие карты трейдера: {decision.peer_ok}/{decision.peer_issued}\n"
        f"Другие карты мерчанта: {decision.merchant_ok}/{decision.merchant_issued}\n"
        "Обе половины окна тоже пустые. Карта снята с выдачи."
    )
    notify_with_cooldown(f"req_guard:{decision.detail_id}", text, 24 * 3600)


def apply_blocks(decisions: list[BlockDecision], *, window_hours: int = 72) -> int:
    from django.db import transaction

    from basics.models import PaymentDetails, PaymentDetailsGroup

    applied: list[BlockDecision] = []
    with transaction.atomic():
        for decision in decisions:
            updated = PaymentDetails.objects.filter(id=decision.detail_id, status=1).update(status=0)
            if not updated:
                continue
            if decision.group_id and not PaymentDetails.objects.filter(
                group_id=decision.group_id, status=1
            ).exists():
                PaymentDetailsGroup.objects.filter(id=decision.group_id, status=1).update(status=3)
            applied.append(decision)
    for decision in applied:
        logger.info(
            "requisite guard off %s merchant=%s raw=%s/%s peers=%s/%s",
            decision.label,
            decision.merchant,
            decision.raw_ok,
            decision.raw_issued,
            decision.peer_ok,
            decision.peer_issued,
        )
        try:
            _alert(decision, window_hours)
        except Exception:
            logger.exception("requisite guard alert failed for %s", decision.detail_id)
    return len(applied)


def run_requisite_guard() -> int:
    if not guard_enabled():
        return 0
    from django.conf import settings

    try:
        window_hours = int(getattr(settings, "REQ_CONV_GUARD_WINDOW_H", 72))
    except (TypeError, ValueError):
        window_hours = 72
    samples = load_samples(window_hours=window_hours)
    decisions = decide_blocks(samples, guard_config_from_settings())
    blocked = apply_blocks(decisions, window_hours=window_hours)
    logger.info("requisite guard scanned_details=%s blocked=%s", len({s.detail_id for s in samples}), blocked)
    return blocked


def maybe_run_requisite_guard() -> None:
    """Не чаще раза в полчаса. Вызывается из минутного крона."""
    if not guard_enabled():
        return
    from django.conf import settings
    from django.core.cache import cache

    try:
        interval = int(getattr(settings, "REQ_CONV_GUARD_INTERVAL_SEC", 1800))
    except (TypeError, ValueError):
        interval = 1800
    interval = max(300, interval)
    try:
        if not cache.add("req_conv_guard_lock", 1, timeout=interval):
            return
    except Exception:
        logger.exception("requisite guard cache lock failed")
        if timezone.now().minute % 30 != 0:
            return
    try:
        run_requisite_guard()
    except Exception:
        logger.exception("requisite guard failed")
        try:
            cache.delete("req_conv_guard_lock")
        except Exception:
            pass
