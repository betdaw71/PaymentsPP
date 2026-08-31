"""Полный audit-trail pay-in: тела запросов/ответов мерчанта, Protocol, колбеки."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from django.conf import settings

logger = logging.getLogger("payin.trace")

_routing_snap: ContextVar[dict | None] = ContextVar("payin_routing_snap", default=None)


def routing_instance() -> dict:
    import os
    import socket

    return {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }


def begin_routing_snap(extra: dict | None = None) -> dict:
    """Новый снимок решения роутинга на одну заявку (InOrder.create → trace)."""
    data: dict = {
        "instance": routing_instance(),
        "solution": extra or {},
        "queryset": None,
        "sort": None,
        "skipped": [],
        "chosen": None,
        "fallback_candidates": None,
    }
    _routing_snap.set(data)
    return data


def get_routing_snap() -> dict:
    cur = _routing_snap.get()
    if cur is None:
        return begin_routing_snap()
    return cur


def take_routing_snap() -> dict:
    cur = _routing_snap.get() or {}
    _routing_snap.set(None)
    return cur


def _balance_amount(trader):
    bal = getattr(trader, "balance_usdt", None)
    if bal is None:
        return None
    return bal.amount


def record_in_queryset(*, payment_system, traffic_type, amount, usd_amount, options_qs) -> None:
    """Почему группа в queryset / выпала. Баланс только логируем, фильтр не меняем."""
    from basics.models import PaymentDetailsGroup
    from payments.psp_payin import psp_routing_priority_for_trader, psp_trader_usernames
    from trade.routing.routeutils import get_teams_for_ps

    snap = get_routing_snap()
    psp_users = psp_trader_usernames()
    included_ids = set(options_qs.values_list("pk", flat=True))
    teams = get_teams_for_ps(payment_system)
    team_ids = set(teams.values_list("pk", flat=True))

    included_psp = []
    excluded_psp = []
    psp_groups = (
        PaymentDetailsGroup.objects.filter(
            payment_system=payment_system,
            trader__user__username__in=psp_users,
        )
        .select_related("trader", "trader__user", "trader__balance_usdt")
        .prefetch_related("allowed_traffic")
    )
    for group in psp_groups:
        trader = group.trader
        uname = trader.user.username if trader and trader.user else "?"
        bal = _balance_amount(trader)
        reasons = []
        if group.work_type != "by_card":
            reasons.append(f"work_type={group.work_type}")
        if group.status != 1:
            reasons.append(f"status={group.status}")
        if not group.in_active:
            reasons.append("in_active=False")
        if trader and trader.blocked:
            reasons.append("blocked")
        if bal is None:
            reasons.append("no_balance_row")
        elif bal < usd_amount:
            reasons.append(f"balance_usdt={bal} < need {usd_amount}")
        traffics = [t.name for t in group.allowed_traffic.all()]
        in_team = bool(trader and trader.team_id in team_ids)
        vol = group.current_volume or 0
        lim = group.limit_per_period
        over_limit = lim is not None and (vol + amount) > lim
        row = {
            "trader": uname,
            "group_id": str(group.id),
            "in_queryset": group.pk in included_ids,
            "balance_usdt": str(bal) if bal is not None else None,
            "need_usdt": str(usd_amount),
            "volume": str(vol),
            "limit_per_period": str(lim) if lim is not None else None,
            "over_group_limit": over_limit,
            "priority": psp_routing_priority_for_trader(trader),
            "in_team": in_team,
            "traffic": traffics,
            "skip": reasons,
        }
        if group.pk in included_ids:
            included_psp.append(row)
        else:
            excluded_psp.append(row)

    included_traders = []
    for group in options_qs.select_related("trader__user")[:30]:
        uname = group.trader.user.username if group.trader and group.trader.user else "?"
        included_traders.append(uname)

    snap["queryset"] = {
        "ps": payment_system.name if payment_system else None,
        "traffic": getattr(traffic_type, "name", None),
        "traffic_id": str(getattr(traffic_type, "id", "") or ""),
        "amount": str(amount),
        "need_usdt": str(usd_amount),
        "included_count": options_qs.count(),
        "included_traders": included_traders,
        "included_psp": included_psp,
        "excluded_psp": excluded_psp,
    }
    logger.info(
        "ROUTING_QS ps=%s amount=%s need_usdt=%s included=%s excluded_psp=%s",
        payment_system.name if payment_system else None,
        amount,
        usd_amount,
        included_traders[:12],
        [f"{row.get('trader')}:{row.get('skip') or 'in'}" for row in excluded_psp[:8]],
    )
    _log_preferred_psp_status(included_psp, excluded_psp, amount, usd_amount)


def _log_preferred_psp_status(included_psp, excluded_psp, amount, usd_amount) -> None:
    from payments.psp_payin import preferred_payin_psp_usernames

    by_name = {}
    for row in list(included_psp) + list(excluded_psp):
        by_name[(row.get("trader") or "").strip().lower()] = row
    for uname in preferred_payin_psp_usernames():
        row = by_name.get(uname.lower())
        label = "PAYPLAT" if "payplat" in uname.lower() else "GIPAY" if "gipay" in uname.lower() else uname.upper()
        if row is None:
            logger.warning(
                "%s_NO_SESSION reason=no_group_on_ps — группы нет, API не вызовется",
                label,
            )
            continue
        vol = row.get("volume")
        lim = row.get("limit_per_period")
        over = row.get("over_group_limit")
        if not row.get("in_queryset"):
            skip = row.get("skip") or []
            if any("balance_usdt" in str(s) for s in skip):
                why = (
                    f"не хватает баланса USDT (bal={row.get('balance_usdt')} < need {usd_amount})"
                )
            elif any("blocked" in str(s) or "status=" in str(s) for s in skip):
                why = f"группа выключена {skip}"
            else:
                why = str(skip)
            logger.warning(
                "%s_NO_SESSION reason=not_in_cascade %s vol=%s/%s — сессии не будет, API не вызываем",
                label,
                why,
                vol,
                lim,
            )
            continue
        if over:
            logger.info(
                "%s_STATUS in_cascade=yes group_limit vol=%s/%s amount=%s "
                "превышен limit_per_period, но PSP не режется по нему — WILL_CALL",
                label,
                vol,
                lim,
                amount,
            )
        else:
            logger.info(
                "%s_STATUS in_cascade=yes bal=%s vol=%s/%s — WILL_CALL",
                label,
                row.get("balance_usdt"),
                vol,
                lim,
            )


def record_in_sort_and_pick(*, sorted_groups, skipped: list, chosen_detail) -> None:
    from payments.psp_payin import is_psp_trader, psp_routing_priority_for_trader, share_metrics_for_groups

    snap = get_routing_snap()
    try:
        share_rows = share_metrics_for_groups(sorted_groups)
    except Exception:
        share_rows = {}
    sort_rows = []
    for i, group in enumerate(sorted_groups[:25], 1):
        trader = group.trader
        uname = trader.user.username if trader and getattr(trader, "user", None) else "?"
        share = share_rows.get((uname or "").strip().lower()) or {}
        sort_rows.append({
            "n": i,
            "trader": uname,
            "group_id": str(group.id),
            "psp": is_psp_trader(trader),
            "priority": psp_routing_priority_for_trader(trader),
            "volume": str(group.current_volume),
            "share_target": str(share["target"]) if share else None,
            "share_actual": str(share["actual"]) if share else None,
            "share_deficit": str(share["deficit"]) if share else None,
            "share_window_volume": str(share["volume"]) if share else None,
            "balance_usdt": str(_balance_amount(trader)) if trader else None,
        })
    snap["sort"] = sort_rows
    snap["skipped"] = skipped
    if chosen_detail is not None and chosen_detail.group:
        trader = chosen_detail.group.trader
        uname = trader.user.username if trader and getattr(trader, "user", None) else None
        share = share_rows.get((uname or "").strip().lower()) or {}
        snap["chosen"] = {
            "trader": uname,
            "group_id": str(chosen_detail.group_id),
            "payment_details_id": str(chosen_detail.id),
            "psp": is_psp_trader(trader),
            "priority": psp_routing_priority_for_trader(trader),
            "share_target": str(share["target"]) if share else None,
            "share_actual": str(share["actual"]) if share else None,
            "share_deficit": str(share["deficit"]) if share else None,
            "balance_usdt": str(_balance_amount(trader)) if trader else None,
        }
    else:
        snap["chosen"] = None
    logger.info(
        "ROUTING_PICK chosen=%s prio=%s skip=%s sort=%s",
        (snap.get("chosen") or {}).get("trader"),
        (snap.get("chosen") or {}).get("priority"),
        [f"{row.get('trader')}:{row.get('skip')}" for row in skipped[:8]],
        [row.get("trader") for row in sort_rows[:8]],
    )


class Direction:
    MERCHANT_REQUEST = "merchant_request"
    MERCHANT_RESPONSE = "merchant_response"
    ROUTING = "routing"
    PROTOCOL_OUT_REQUEST = "protocol_out_request"
    PROTOCOL_OUT_RESPONSE = "protocol_out_response"
    PROTOCOL_WEBHOOK = "protocol_webhook"
    PLAYMENTS_OUT_REQUEST = "playments_out_request"
    PLAYMENTS_OUT_RESPONSE = "playments_out_response"
    PLAYMENTS_WEBHOOK = "playments_webhook"
    CONCORDED_OUT_REQUEST = "concored_out_request"
    CONCORDED_OUT_RESPONSE = "concored_out_response"
    CONCORDED_WEBHOOK = "concored_webhook"
    PAYMAP_OUT_REQUEST = "paymap_out_request"
    PAYMAP_OUT_RESPONSE = "paymap_out_response"
    PAYMAP_WEBHOOK = "paymap_webhook"
    BITZONE_OUT_REQUEST = "bitzone_out_request"
    BITZONE_OUT_RESPONSE = "bitzone_out_response"
    BITZONE_WEBHOOK = "bitzone_webhook"
    PLUTUS_OUT_REQUEST = "plutus_out_request"
    PLUTUS_OUT_RESPONSE = "plutus_out_response"
    PLUTUS_WEBHOOK = "plutus_webhook"
    SYNDICATE_OUT_REQUEST = "syndicate_out_request"
    SYNDICATE_OUT_RESPONSE = "syndicate_out_response"
    SYNDICATE_WEBHOOK = "syndicate_webhook"
    BOTONPAY_OUT_REQUEST = "botonpay_out_request"
    BOTONPAY_OUT_RESPONSE = "botonpay_out_response"
    BOTONPAY_WEBHOOK = "botonpay_webhook"
    GIPAY_OUT_REQUEST = "gipay_out_request"
    GIPAY_OUT_RESPONSE = "gipay_out_response"
    GIPAY_WEBHOOK = "gipay_webhook"
    VISIONX_OUT_REQUEST = "visionx_out_request"
    VISIONX_OUT_RESPONSE = "visionx_out_response"
    VISIONX_WEBHOOK = "visionx_webhook"
    PAYPLAT_OUT_REQUEST = "payplat_out_request"
    PAYPLAT_OUT_RESPONSE = "payplat_out_response"
    PAYPLAT_WEBHOOK = "payplat_webhook"
    MERCHANT_CALLBACK = "merchant_callback"


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return str(value)[:8000]


def trace_log(
    *,
    direction: str,
    body: Any,
    pay_in=None,
    merchant=None,
    merchant_order_id: str | None = None,
    http_method: str = "",
    url: str = "",
    status_code: int | None = None,
    note: str = "",
) -> None:
    """Сохранить событие в БД и вывести в лог приложения (docker compose logs)."""
    from payments.models import PayInTraceLog

    if pay_in is not None:
        merchant_order_id = merchant_order_id or pay_in.merchant_order_id
        if merchant is None and pay_in.merchant_id:
            merchant = pay_in.merchant

    safe_body = _json_safe(body)
    entry = PayInTraceLog.objects.create(
        pay_in=pay_in,
        merchant=merchant,
        merchant_order_id=(merchant_order_id or "")[:255],
        direction=direction,
        http_method=(http_method or "")[:16],
        url=(url or "")[:512],
        status_code=status_code,
        body=safe_body if isinstance(safe_body, (dict, list)) else {"value": safe_body},
        note=(note or "")[:512],
    )

    pay_in_label = str(pay_in.id) if pay_in is not None else "-"
    merchant_label = merchant.user.username if merchant and getattr(merchant, "user", None) else "-"
    body_preview = json.dumps(safe_body, ensure_ascii=False, default=str)
    if len(body_preview) > 4000:
        body_preview = body_preview[:4000] + "…"

    line = (
        f"PAYIN_TRACE id={entry.id} direction={direction} pay_in={pay_in_label} "
        f"merchant={merchant_label} order={merchant_order_id or '-'} "
        f"http={http_method} url={url} status={status_code} note={note} body={body_preview}"
    )
    logger.info(line)

    if getattr(settings, "PAYIN_TRACE_PRINT", False):
        print(line, flush=True)

    return entry


def trace_routing_result(pay_in, in_order, *, note: str = "") -> None:
    trader = (
        in_order.payment_details.group.trader.user.username
        if in_order.payment_details is not None
        else None
    )
    body = {
        "instance": routing_instance(),
        "in_order_id": str(in_order.id),
        "in_order_status": in_order.status.name if in_order.status else None,
        "payment_details_id": str(in_order.payment_details_id) if in_order.payment_details_id else None,
        "trader": trader,
        "amount": str(in_order.amount),
        "payment_system": (
            in_order.solution.payment_system.name if in_order.solution and in_order.solution.payment_system else None
        ),
    }
    trace_log(
        pay_in=pay_in,
        direction=Direction.ROUTING,
        body=body,
        note=note or "after InOrder.create",
    )
    snap = take_routing_snap()
    if snap:
        trace_log(
            pay_in=pay_in,
            direction=Direction.ROUTING,
            body=snap,
            note="routing decision",
        )
        qs = snap.get("queryset") or {}
        sort_names = [row.get("trader") for row in (snap.get("sort") or [])[:8]]
        excluded = [
            f"{row.get('trader')}:{row.get('skip')}"
            for row in (qs.get("excluded_psp") or [])
        ]
        logger.info(
            "ROUTING_DECISION pay_in=%s chosen=%s ftd=%s sort=%s excluded_psp=%s skipped=%s",
            pay_in.id if pay_in is not None else "-",
            (snap.get("chosen") or {}).get("trader") or trader,
            (snap.get("solution") or {}).get("ftd"),
            sort_names,
            excluded,
            [f"{row.get('trader')}:{row.get('skip')}" for row in (snap.get("skipped") or [])[:8]],
        )


def wrap_merchant_payin_create(viewset, request, *args, **kwargs):
    """Обёртка для create() в PayIn viewsets: логирует request/response мерчанта."""
    from django.db import transaction
    from rest_framework import status
    from rest_framework.exceptions import ValidationError as DRFValidationError
    from rest_framework.response import Response

    from payments.psp_payin import get_payin_decline_payload

    merchant = request.user.merchant
    trace_log(
        merchant=merchant,
        merchant_order_id=str(request.data.get("merchant_order_id") or ""),
        direction=Direction.MERCHANT_REQUEST,
        body=request.data,
        http_method="POST",
        url=request.path,
        note="merchant create pay-in",
    )
    serializer = viewset.get_serializer(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            viewset.perform_create(serializer)
    except DRFValidationError as exc:
        trace_log(
            merchant=merchant,
            merchant_order_id=str(request.data.get("merchant_order_id") or ""),
            direction=Direction.MERCHANT_RESPONSE,
            body=exc.detail,
            http_method="POST",
            url=request.path,
            status_code=400,
            note="validation error",
        )
        raise

    pay_in = serializer.instance
    pay_in.refresh_from_db()
    decline_payload = get_payin_decline_payload(pay_in)
    if decline_payload is not None:
        trace_log(
            pay_in=pay_in,
            direction=Direction.MERCHANT_RESPONSE,
            body=decline_payload,
            http_method="POST",
            url=request.path,
            status_code=400,
            note="declined",
        )
        raise DRFValidationError(decline_payload)

    trace_log(
        pay_in=pay_in,
        direction=Direction.MERCHANT_RESPONSE,
        body=serializer.data,
        http_method="POST",
        url=request.path,
        status_code=201,
        note="create ok",
    )
    signature = merchant.api_keys.get(active=True).sign_data(serializer.data)
    headers = {"Signature": signature, "Content-Type": "application/json"}
    return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
