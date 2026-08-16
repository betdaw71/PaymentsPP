"""Общие хелперы PSP (FairPay, ExpayOne, Protocol) для pay-in."""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def decline_payin(pay_in: Any, *, send_callback: bool = True) -> None:
    """Declined без callback при create-fail; совместимо со старым PayIn.declined() без kwargs."""
    try:
        pay_in.declined(send_callback=send_callback)
    except TypeError:
        if send_callback:
            pay_in.declined()
        else:
            from payments.models import PayInStatus

            pay_in.status = PayInStatus.objects.get(name="Declined")
            pay_in.updated_at = timezone.now()
            pay_in.save(update_fields=["status", "updated_at"])


def is_psp_trader(trader) -> bool:
    """Виртуальные PSP-трейдеры не используют SMS/liveness — не блокировать по auto_live."""
    if trader is None:
        return False
    from payments import fairpay_client as fc
    from payments import expayone_client as ec
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as plc2
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    return (
        fc.is_fairpay_trader(trader)
        or ec.is_expayone_trader(trader)
        or pc.is_protocol_trader(trader)
        or plc.is_playments_trader(trader)
        or cc.is_concored_trader(trader)
        or pmc.is_paymap_trader(trader)
        or bzc.is_bitzone_trader(trader)
        or plc2.is_plutus_trader(trader)
        or syc.is_syndicate_trader(trader)
        or bpc.is_botonpay_trader(trader)
    )


def psp_order_usd_ledger_amount(order) -> Decimal:
    """
    USDT для Freeze/Charge у PSP: Transaction.value хранит 2 знака после запятой.
    Микросуммы (< 0.01 USDT) иначе округляются до 0 и complete падает на проверке frozen.
    """
    raw = Decimal(str(getattr(order, "usd_amount", 0) or 0))
    if raw <= 0:
        return Decimal("0")
    q = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if q <= 0:
        q = Decimal("0.01")
    return q


def ensure_psp_frozen_for_complete(order) -> None:
    """
    PSP pay-in: на frozen должна быть сумма заказа в ledger-формате (2 dp).
    После expire/cancel webhook разморозка снимает freeze; перед complete дозамораживаем из available.
    """
    if not getattr(order, "payment_details_id", None):
        return
    trader = order.payment_details.group.trader
    if not is_psp_trader(trader):
        return

    from basics.models import Balance
    from trade.models import Transaction, TransactionType

    frozen_bal = Balance.objects.select_for_update().get(pk=trader.frozen_balance_usdt_id)
    need = psp_order_usd_ledger_amount(order)
    if need <= 0:
        return
    if frozen_bal.amount >= need:
        return

    shortfall = (need - frozen_bal.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if shortfall <= 0:
        return

    available_bal = Balance.objects.select_for_update().get(pk=trader.balance_usdt_id)
    if available_bal.amount < shortfall:
        raise ValidationError(
            {
                "details": (
                    f"PSP trader {trader.user.username}: frozen balance insufficient for complete "
                    f"(order={need}, frozen={frozen_bal.amount}, available={available_bal.amount})"
                )
            }
        )

    transaction_type = TransactionType.objects.get(name="Freeze")
    Transaction.create(
        _from=trader.balance_usdt,
        _to=trader.frozen_balance_usdt,
        value=shortfall,
        _transaction_type=transaction_type,
        _linked_in_order=order,
        _comment="PSP replenish frozen before complete",
    )


def _team_mdr_in_map(groups) -> dict[tuple[int, int], Decimal]:
    """(team_id, payment_system_id) -> mdr_in для сортировки PSP-каскада."""
    from basics.models import TraderTeamRates

    team_ids = {g.trader.team_id for g in groups if g.trader and g.trader.team_id}
    ps_ids = {g.payment_system_id for g in groups if g.payment_system_id}
    if not team_ids or not ps_ids:
        return {}
    return {
        (row["team_id"], row["payment_system_id"]): row["mdr_in"]
        for row in TraderTeamRates.objects.filter(
            team_id__in=team_ids,
            payment_system_id__in=ps_ids,
        ).values("team_id", "payment_system_id", "mdr_in")
    }


def sort_groups_for_routing(groups, amount=None):
    """
    Порядок выбора PSP-группы.
    Если все кандидаты — PSP-трейдеры: сначала меньший mdr_in (дешевле провайдер),
    затем current_volume. Иначе — только по current_volume (как раньше).
    """
    groups = list(groups)
    if not groups:
        return groups
    if all(is_psp_trader(g.trader) for g in groups):
        mdr_map = _team_mdr_in_map(groups)
        return sorted(
            groups,
            key=lambda g: (
                mdr_map.get((g.trader.team_id, g.payment_system_id), Decimal("999")),
                g.current_volume or Decimal(0),
                g.trader.user.username if g.trader and g.trader.user else "",
            ),
        )
    return sorted(groups, key=lambda g: g.current_volume or Decimal(0))


def psp_routing_amount_ok(trader, amount) -> bool:
    """Сумма не ограничивает выбор PSP — лимиты только MerchantSolution и ответ API провайдера."""
    return True


def psp_trader_usernames() -> frozenset[str]:
    """Usernames виртуальных PSP-трейдеров (для роутинга)."""
    from django.conf import settings
    from payments import fairpay_client as fc
    from payments import expayone_client as ec
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as pltc
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    names = {
        fc.fairpay_trader_username(),
        ec.expayone_trader_username(),
        pc.protocol_trader_username(),
        plc.playments_trader_username(),
        cc.concored_trader_username(),
        pmc.paymap_trader_username(),
        bzc.bitzone_trader_username(),
        pltc.plutus_trader_username(),
        syc.syndicate_trader_username(),
        bpc.botonpay_trader_username(),
    }
    extra = getattr(settings, "PSP_TRADER_USERNAMES", None)
    if isinstance(extra, str) and extra.strip():
        names.update(u.strip() for u in extra.split(",") if u.strip())
    elif isinstance(extra, (list, tuple, set)):
        names.update(str(u).strip() for u in extra if str(u).strip())
    return frozenset(n for n in names if n)


def filter_inorders_for_trader_lk(qs):
    """Трейдеру — только живые заявки с реальными реквизитами; без PSP/Cannot process/Declined."""
    usernames = psp_trader_usernames()
    if usernames:
        qs = qs.exclude(payment_details__group__trader__user__username__in=usernames)
    return (
        qs.exclude(status__name="Cannot process")
        .exclude(payment_details__isnull=True)
        .exclude(pay_in__status__name="Declined")
    )


def requisite_payload_has_fields(req: dict | None) -> bool:
    if not req or not isinstance(req, dict):
        return False
    return bool(
        str(req.get("card_number") or "").strip()
        or str(req.get("phone") or "").strip()
        or str(req.get("deposit_number") or "").strip()
        or str(req.get("deeplink") or "").strip()
        or str(req.get("payment_form_url") or "").strip()
        or str(req.get("qr_image_url") or "").strip()
    )


def requisite_for_payin(pay_in: Any) -> dict | None:
    from payments import fairpay_client as fc
    from payments import expayone_client as ec
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as pltc
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    for getter in (
        fc.fairpay_requisite_for_payin,
        ec.expayone_requisite_for_payin,
        pc.protocol_requisite_for_payin,
        plc.playments_requisite_for_payin,
        cc.concored_requisite_for_payin,
        pmc.paymap_requisite_for_payin,
        bzc.bitzone_requisite_for_payin,
        pltc.plutus_requisite_for_payin,
        syc.syndicate_requisite_for_payin,
        bpc.botonpay_requisite_for_payin,
    ):
        req = getter(pay_in)
        if requisite_payload_has_fields(req):
            return req
    return None


def enrich_payin_payment_details(representation: dict, pay_in: Any) -> dict:
    from payments import fairpay_client as fc
    from payments import expayone_client as ec
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as pltc
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    representation = fc.enrich_payin_payment_details(representation, pay_in)
    representation = ec.enrich_payin_payment_details(representation, pay_in)
    representation = pc.enrich_payin_payment_details(representation, pay_in)
    representation = plc.enrich_payin_payment_details(representation, pay_in)
    representation = cc.enrich_payin_payment_details(representation, pay_in)
    representation = pmc.enrich_payin_payment_details(representation, pay_in)
    representation = bzc.enrich_payin_payment_details(representation, pay_in)
    representation = pltc.enrich_payin_payment_details(representation, pay_in)
    representation = syc.enrich_payin_payment_details(representation, pay_in)
    return bpc.enrich_payin_payment_details(representation, pay_in)


def payin_routed_group(pay_in: Any):
    """PaymentDetailsGroup, подобранная роутингом для pay-in."""
    order = getattr(pay_in, "order", None)
    if order is None or order.payment_details is None:
        return None
    return order.payment_details.group


def payin_routed_group_matches_ps(pay_in: Any) -> bool:
    """payment_system заявки совпадает с PS включённой виртуальной группы."""
    group = payin_routed_group(pay_in)
    if group is None or not pay_in.payment_system_id:
        return False
    return group.payment_system_id == pay_in.payment_system_id


def payin_routed_psp_group_active(pay_in: Any) -> bool:
    """Виртуальная группа активна (in_active + status=1)."""
    group = payin_routed_group(pay_in)
    if group is None:
        return False
    return bool(group.in_active and group.status == 1)


def _psp_provider_for_trader(trader):
    """Провайдер PSP по трейдеру подобранного реквизита (виртуальная группа)."""
    from payments import expayone_client as ec
    from payments import fairpay_client as fc
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as pltc
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    if pc.is_protocol_trader(trader):
        return "protocol", pc.try_attach_protocol_session
    if ec.is_expayone_trader(trader):
        return "expayone", ec.try_attach_expayone_session
    if bpc.is_botonpay_trader(trader):
        return "botonpay", bpc.try_attach_botonpay_session
    if bzc.is_bitzone_trader(trader):
        return "bitzone", bzc.try_attach_bitzone_session
    if pltc.is_plutus_trader(trader):
        return "plutus", pltc.try_attach_plutus_session
    if syc.is_syndicate_trader(trader):
        return "syndicate", syc.try_attach_syndicate_session
    if fc.is_fairpay_trader(trader):
        return "fairpay", fc.try_attach_fairpay_session
    if plc.is_playments_trader(trader):
        return "playments", plc.try_attach_playments_session
    if cc.is_concored_trader(trader):
        return "concored", cc.try_attach_concored_session
    if pmc.is_paymap_trader(trader):
        return "paymap", pmc.try_attach_paymap_session
    return None, None


def _swap_inorder_payment_details(pay_in: Any, new_detail, amount: Decimal) -> None:
    """Переключить InOrder на другую виртуальную группу PSP (fallback)."""
    from basics.models import PaymentDetailsGroup
    from django.db.models import F
    from trade.models import InOrder

    order = pay_in.order
    if order is None or new_detail is None:
        return
    old_detail = order.payment_details
    with transaction.atomic():
        od = InOrder.objects.select_for_update().get(pk=order.pk)
        od.payment_details = new_detail
        od.save(update_fields=["payment_details"])
        if old_detail and old_detail.group_id != new_detail.group_id:
            PaymentDetailsGroup.objects.filter(pk=old_detail.group_id).update(
                current_volume=F("current_volume") - amount,
            )
            PaymentDetailsGroup.objects.filter(pk=new_detail.group_id).update(
                current_volume=F("current_volume") + amount,
            )
    pay_in.refresh_from_db()
    order.refresh_from_db()


def _iter_psp_fallback_candidates(pay_in: Any, *, exclude_trader_id: int | None):
    """Альтернативные PSP-группы на том же PS (кроме уже попробованного трейдера)."""
    from basics.models import PaymentDetails, PaymentDetailsGroup

    order = pay_in.order
    if order is None or order.solution is None:
        return
    ps = pay_in.payment_system
    traffic = order.solution.traffic
    amount = pay_in.amount
    groups = list(
        PaymentDetailsGroup.objects.filter(
            payment_system=ps,
            status=1,
            in_active=True,
            work_type="by_card",
            allowed_traffic=traffic,
            trader__blocked=False,
        )
        .select_related("trader", "trader__user")
    )
    seen_trader_ids: set[int] = set()
    for group in sort_groups_for_routing(groups, amount):
        if exclude_trader_id is not None and group.trader_id == exclude_trader_id:
            continue
        if group.trader_id in seen_trader_ids:
            continue
        if not is_psp_trader(group.trader):
            continue
        detail = PaymentDetails.objects.filter(
            group=group,
            status=1,
            sberpay_enabled=False,
            sbp_enabled=False,
            card_number__isnull=False,
        ).first()
        if detail is not None:
            provider_name, attach = _psp_provider_for_trader(group.trader)
            if attach is not None:
                seen_trader_ids.add(group.trader_id)
                yield provider_name, attach, detail


def try_psp_provider_fallback(pay_in: Any, *, failed_provider: str) -> bool:
    """Protocol/ExpayOne не выдал реквизиты — пробуем другой PSP с активной группой."""
    from payments.payin_trace import Direction, trace_log

    failed_trader_id = None
    routed = payin_routed_group(pay_in)
    if routed is not None:
        failed_trader_id = routed.trader_id

    for provider_name, attach, detail in _iter_psp_fallback_candidates(
        pay_in, exclude_trader_id=failed_trader_id
    ):
        _swap_inorder_payment_details(pay_in, detail, pay_in.amount)
        result = attach(pay_in)
        has_req = _payin_has_psp_requisite(pay_in) if result is True else False
        trace_log(
            pay_in=pay_in,
            direction=Direction.ROUTING,
            body={
                "provider": provider_name,
                "success": result is True,
                "has_requisite": has_req,
                "fallback": True,
            },
            note="psp provider fallback",
        )
        # attach() уже проверил ответ PSP; не полагаемся только на reverse OneToOne cache pay_in
        if result is True:
            pay_in.refresh_from_db()
            if getattr(pay_in, "order_id", None):
                pay_in.order.refresh_from_db()
            logger.info(
                "PSP fallback ok pay_in_id=%s failed=%s used=%s has_requisite=%s",
                pay_in.id,
                failed_provider,
                provider_name,
                _payin_has_psp_requisite(pay_in),
            )
            return True
    return False


def try_attach_psp_sessions(pay_in: Any) -> None:
    """Реквизит от PSP-трейдера → один запрос к его API; нет реквизитов в ответе → Cannot process."""
    from payments.payin_trace import Direction, trace_log

    order = getattr(pay_in, "order", None)
    if order is None or order.payment_details is None:
        return
    trader = order.payment_details.group.trader
    if not is_psp_trader(trader):
        return

    if not payin_routed_group_matches_ps(pay_in):
        logger.error(
            "PSP attach skipped: routed group PS mismatch pay_in_id=%s ps=%s",
            pay_in.id,
            pay_in.payment_system.name if pay_in.payment_system else None,
        )
        mark_inorder_cannot_process_from_psp_api(pay_in, provider="routing_mismatch")
        return

    if not payin_routed_psp_group_active(pay_in):
        logger.error("PSP attach skipped: virtual group inactive pay_in_id=%s", pay_in.id)
        mark_inorder_cannot_process_from_psp_api(pay_in, provider="group_inactive")
        return

    provider_name, attach = _psp_provider_for_trader(trader)
    if attach is None:
        return

    result = attach(pay_in)
    trace_log(
        pay_in=pay_in,
        direction=Direction.ROUTING,
        body={"provider": provider_name, "success": result is True},
        note="psp provider api",
    )
    if result is True:
        pay_in.refresh_from_db()
        if getattr(pay_in, "order_id", None):
            pay_in.order.refresh_from_db()
        return

    if try_psp_provider_fallback(pay_in, failed_provider=provider_name):
        return

    mark_inorder_cannot_process_from_psp_api(pay_in, provider=provider_name)


def _payin_has_psp_requisite(pay_in: Any) -> bool:
    return requisite_payload_has_fields(requisite_for_payin(pay_in))


def cancel_psp_if_linked(pay_in: Any) -> None:
    from payments import fairpay_client as fc
    from payments import expayone_client as ec
    from payments import protocol_client as pc
    from payments import playments_client as plc
    from payments import concored_client as cc
    from payments import paymap_client as pmc
    from payments import bitzone_client as bzc
    from payments import plutus_client as pltc
    from payments import syndicate_client as syc
    from payments import botonpay_client as bpc

    fc.fairpay_cancel_if_linked(pay_in)
    ec.expayone_cancel_if_linked(pay_in)
    pc.protocol_cancel_if_linked(pay_in)
    plc.playments_cancel_if_linked(pay_in)
    cc.concored_cancel_if_linked(pay_in)
    pmc.paymap_cancel_if_linked(pay_in)
    bzc.bitzone_cancel_if_linked(pay_in)
    pltc.plutus_cancel_if_linked(pay_in)
    syc.syndicate_cancel_if_linked(pay_in)
    bpc.botonpay_cancel_if_linked(pay_in)


def parse_psp_webhook_paid_amount(body: dict | None) -> Decimal | None:
    """Фактически оплаченная сумма из callback PSP (Protocol: amount / result.amount)."""
    if not isinstance(body, dict):
        return None

    def _positive_decimal(raw) -> Decimal | None:
        if raw is None:
            return None
        try:
            val = Decimal(str(raw).strip().replace(",", "."))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return val if val > 0 else None

    status = (body.get("status") or "").strip().lower().replace("-", "_")
    # Bitzone: после спора приходит re_calculation с фактической суммой в dispute* полях.
    if status in ("re_calculation", "recalculation", "closed", "dispute"):
        for key in ("disputeTraderFiatAmount", "disputeMerchantFiatAmount"):
            paid = _positive_decimal(body.get(key))
            if paid is not None:
                return paid

    candidates: list[Any] = []
    for key in (
        "FactSum",
        "fact_sum",
        "OutSum",
        "outSum",
        "received_amount",
        "disputeTraderFiatAmount",
        "disputeMerchantFiatAmount",
        "fiatAmount",
        "amount_fiat",
        "amount",
        "paidAmount",
        "paid_amount",
        "transferredAmount",
        "requestedAmount",
        "amount_num",
    ):
        if body.get(key) is not None:
            candidates.append(body.get(key))
    result = body.get("result")
    if isinstance(result, dict):
        for key in (
            "amount",
            "paidAmount",
            "paid_amount",
            "transferredAmount",
            "requestedAmount",
            "quotedAmountMinor",
            "requestedAmountMinor",
        ):
            if result.get(key) is not None:
                candidates.append(result.get(key))
    factor = 1
    try:
        from django.conf import settings

        factor = int(getattr(settings, "CONCORDED_AMOUNT_MINOR_FACTOR", 1) or 1)
    except (TypeError, ValueError):
        factor = 1
    for raw in candidates:
        try:
            val = Decimal(str(raw).strip())
        except (InvalidOperation, ValueError, TypeError):
            continue
        if val > 0:
            if factor > 1 and val == val.to_integral_value():
                val = val / Decimal(factor)
            return val
    return None


def psp_webhook_is_recalculation(body: dict | None) -> bool:
    if not isinstance(body, dict):
        return False
    status = (body.get("status") or "").strip().lower().replace("-", "_")
    return status in ("re_calculation", "recalculation")


def handle_psp_success_webhook(order, webhook_body: dict | None) -> str:
    """
    Обработка success webhook PSP.
    Возвращает: completed | recalculated | idempotent.
    """
    from trade.models import InOrder

    if not isinstance(order, InOrder):
        raise ValidationError({"error": "no_inorder"})

    paid_amount = parse_psp_webhook_paid_amount(webhook_body)
    state = order.status.name if order.status else None
    if state == "Completed":
        if psp_webhook_is_recalculation(webhook_body) and paid_amount and paid_amount != order.amount:
            if order.apply_psp_completed_recalc(paid_amount):
                return "recalculated"
        return "idempotent"

    order.complete_from_psp_success(paid_amount)
    return "completed"


def complete_inorder_from_psp_webhook(order, webhook_body: dict | None) -> None:
    handle_psp_success_webhook(order, webhook_body)


def mark_inorder_cannot_process_from_psp_api(pay_in: Any, *, provider: str | None = None) -> None:
    """API PSP не выдал реквизиты → InOrder Cannot process (для саппорта), PayIn Declined."""
    from payments.models import PayIn
    from payments.payin_trace import Direction, trace_log, trace_routing_result
    from trade.models import InOrder, InOrderStatus

    order = getattr(pay_in, "order", None)
    if order is None:
        return

    pay_in_id = pay_in.pk
    with transaction.atomic():
        od = InOrder.objects.select_for_update().get(pk=order.pk)
        if not od.status or od.status.name != "New":
            return
        if od.payment_details_id:
            od.decrease_current_volume()
            od.unfreeze("PSP API failed — Cannot process")
        od.payment_details = None
        od.status = InOrderStatus.objects.get(name="Cannot process")
        od.updated_date = timezone.now()
        od.save(update_fields=["payment_details", "status", "updated_date"])

        pi = PayIn.objects.select_for_update().get(pk=pay_in_id)
        if pi.status and pi.status.name != "Declined":
            decline_payin(pi, send_callback=False)

    pay_in.refresh_from_db()
    order.refresh_from_db()
    trace_routing_result(
        pay_in,
        order,
        note=f"psp api failed provider={provider}",
    )
    trace_log(
        pay_in=pay_in,
        direction=Direction.ROUTING,
        body={"psp_provider": provider, "result": "cannot_process"},
        note="psp provider api failed",
    )
    logger.warning(
        "PSP API → Cannot process pay_in_id=%s provider=%s detail=%s",
        pay_in.id,
        provider,
        psp_create_failure_reason_internal(pay_in),
    )


def mark_inorder_cannot_process_from_psp_cascade(pay_in: Any, *, tried_providers: list[str] | None = None) -> None:
    """Deprecated alias — см. mark_inorder_cannot_process_from_psp_api."""
    provider = (tried_providers or [None])[0]
    mark_inorder_cannot_process_from_psp_api(pay_in, provider=provider)


def cancel_inorder_on_psp_create_failed(order) -> None:
    """Отмена InOrder при ошибке PSP без колбека мерчанту (колбек шлёт только PayIn.declined())."""
    from trade.models import InOrderStatus

    if order is None or not order.status or order.status.name != "New":
        return
    status = InOrderStatus.objects.get(name="Cancelled")
    order.status = status
    order.updated_date = timezone.now()
    order.decrease_current_volume()
    order.save()
    order.unfreeze("In-order cancelled (PSP create failed)")


def _extract_upstream_error(payload: dict) -> str | None:
    """Только для внутренних логов / diagnose_payin — не отдавать мерчанту."""
    top_message = payload.get("message")
    if top_message and str(top_message).strip():
        top_message = str(top_message).strip()
    detail = payload.get("detail")
    if detail and str(detail).strip():
        return str(detail).strip()
    err = payload.get("error")
    if isinstance(err, dict):
        parts = [err.get("message"), err.get("details")]
        parts = [str(p).strip() for p in parts if p]
        if parts:
            return ": ".join(parts)
        if err.get("code") is not None:
            return f"upstream error code {err['code']}"
    if top_message and err and not isinstance(err, dict):
        return f"{top_message} ({err})"
    if top_message:
        return top_message
    if err:
        return str(err)
    return None


# Коды для мерчанта — без имён PSP и без текста upstream API.
MERCHANT_DECLINE_MESSAGES = {
    "routing_unavailable": (
        "Не удалось выдать платёжные реквизиты для указанной суммы и метода оплаты."
    ),
    "requisites_unavailable": (
        "Временно нет доступных реквизитов для этой суммы. Повторите позже или измените сумму."
    ),
    "requisites_empty_response": (
        "Не удалось получить реквизиты для оплаты. Повторите запрос позже."
    ),
}


def classify_payin_decline(pay_in: Any) -> str:
    """Внутренняя классификация отказа (без PII upstream)."""
    from payments.models import (
        BitzonePayInSession,
        BotonpayPayInSession,
        ConcoredPayInSession,
        ExpayonePayInSession,
        FairpayPayInSession,
        PaymapPayInSession,
        PlaymentsPayInSession,
        PlutusPayInSession,
        SyndicatePayInSession,
        ProtocolPayInSession,
    )

    order = getattr(pay_in, "order", None)
    if order is not None and order.status and order.status.name == "Cannot process":
        return "routing_unavailable"

    for model in (
        ExpayonePayInSession,
        FairpayPayInSession,
        ProtocolPayInSession,
        PlaymentsPayInSession,
        ConcoredPayInSession,
        PaymapPayInSession,
        BitzonePayInSession,
        PlutusPayInSession,
        SyndicatePayInSession,
        BotonpayPayInSession,
    ):
        try:
            session = model.objects.get(pay_in=pay_in)
        except model.DoesNotExist:
            continue
        cr = session.create_response or {}
        if not isinstance(cr, dict):
            continue
        if cr.get("error") in ("no_payment_detail_in_response", "no_credentials_in_response"):
            return "requisites_empty_response"
        if _extract_upstream_error(cr):
            return "requisites_unavailable"
        upstream = cr.get("upstream")
        if isinstance(upstream, dict) and _extract_upstream_error(upstream):
            return "requisites_unavailable"
    return "requisites_unavailable"


def psp_create_failure_reason_internal(pay_in: Any) -> str:
    """Подробности для логов и manage.py diagnose_payin (не API мерчанта)."""
    from payments.models import (
        BitzonePayInSession,
        BotonpayPayInSession,
        ConcoredPayInSession,
        ExpayonePayInSession,
        FairpayPayInSession,
        PaymapPayInSession,
        PlaymentsPayInSession,
        PlutusPayInSession,
        SyndicatePayInSession,
        ProtocolPayInSession,
    )

    code = classify_payin_decline(pay_in)
    parts = [f"code={code}"]

    order = getattr(pay_in, "order", None)
    if order is not None and order.status:
        parts.append(f"in_order_status={order.status.name}")

    for model, label in (
        (ExpayonePayInSession, "expayone"),
        (FairpayPayInSession, "fairpay"),
        (ProtocolPayInSession, "protocol"),
        (PlaymentsPayInSession, "playments"),
        (ConcoredPayInSession, "concored"),
        (PaymapPayInSession, "paymap"),
        (BitzonePayInSession, "bitzone"),
        (PlutusPayInSession, "plutus"),
        (SyndicatePayInSession, "syndicate"),
        (BotonpayPayInSession, "botonpay"),
    ):
        try:
            session = model.objects.get(pay_in=pay_in)
        except model.DoesNotExist:
            continue
        cr = session.create_response or {}
        if isinstance(cr, dict) and cr:
            detail = _extract_upstream_error(cr)
            if not detail and cr.get("error"):
                detail = str(cr.get("error"))
            upstream = cr.get("upstream")
            if not detail and isinstance(upstream, dict):
                detail = _extract_upstream_error(upstream)
            if detail:
                parts.append(f"{label}={detail[:500]}")
            elif cr:
                parts.append(f"{label}_response=present")
    return " | ".join(parts)


def merchant_decline_payload(pay_in: Any) -> dict[str, str]:
    code = classify_payin_decline(pay_in)
    payload = {
        "error": MERCHANT_DECLINE_MESSAGES.get(code, MERCHANT_DECLINE_MESSAGES["requisites_unavailable"]),
        "error_code": code,
        "pay_in_id": str(pay_in.id),
    }
    order = pay_in.order
    if order is not None:
        payload["in_order_id"] = str(order.id)
    return payload


def psp_create_failure_reason(pay_in: Any) -> str:
    """Сообщение для мерчанта — без имён PSP и без upstream-текста."""
    code = classify_payin_decline(pay_in)
    return MERCHANT_DECLINE_MESSAGES.get(code, MERCHANT_DECLINE_MESSAGES["requisites_unavailable"])


def get_payin_decline_payload(pay_in: Any) -> dict | None:
    """Если PayIn уже Declined — payload для ответа мерчанту (без raise)."""
    pay_in.refresh_from_db()
    if pay_in.status and pay_in.status.name == "Declined":
        return merchant_decline_payload(pay_in)
    return None


def ensure_payin_created_ok(pay_in: Any) -> Any:
    """После create + PSP: актуальный PayIn. Declined не бросает исключение — см. wrap_merchant_payin_create."""
    pay_in.refresh_from_db()
    if pay_in.status and pay_in.status.name == "Declined":
        logger.warning(
            "PayIn declined pay_in_id=%s merchant_order_id=%s detail=%s",
            pay_in.id,
            pay_in.merchant_order_id,
            psp_create_failure_reason_internal(pay_in),
        )
    return pay_in
