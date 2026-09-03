from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from appeals.models import PayInAppeal, PayInAppealStatus
from appeals.services import chat_role_for_telegram, init_telegram_chat, process_merchant_appeal_message
from basics.permissions import TgBotPermission


def _collect_deal_ids(pay_in) -> dict:
    """Собрать все ID по сделке: PayIn, InOrder, merchant_order_id, PSP-сессии."""
    from payments.models import (
        BotonpayPayInSession,
        BitzonePayInSession,
        FairpayPayInSession,
        GipayPayInSession,
        PayplatPayInSession,
        VisionxPayInSession,
        ExpayonePayInSession,
        ProtocolPayInSession,
        SyndicatePayInSession,
    )

    result = {
        "pay_in_id": str(pay_in.id),
        "merchant_order_id": pay_in.merchant_order_id or "",
        "in_order_id": str(pay_in.order_id) if pay_in.order_id else "",
        "status": pay_in.status.name if pay_in.status else "",
        "amount": str(pay_in.amount),
        "merchant": (pay_in.merchant.user.username if pay_in.merchant and pay_in.merchant.user else ""),
    }

    if pay_in.order:
        order = pay_in.order
        result["in_order_status"] = order.status.name if order.status else ""

    # PSP sessions
    psp_sessions = [
        ("payplat", PayplatPayInSession, "external_id", "provider_order_id"),
        ("gipay", GipayPayInSession, "external_id", "provider_payment_id"),
        ("botonpay", BotonpayPayInSession, "external_id", "provider_deal_uuid"),
        ("bitzone", BitzonePayInSession, "external_id", "provider_transaction_id"),
        ("fairpay", FairpayPayInSession, "external_id", "provider_order_id"),
        ("visionx", VisionxPayInSession, "external_id", "provider_invoice_id"),
        ("expayone", ExpayonePayInSession, "external_id", "provider_order_id"),
        ("protocol", ProtocolPayInSession, "external_id", "provider_payment_id"),
        ("syndicate", SyndicatePayInSession, "external_id", "provider_order_id"),
    ]

    for psp_name, model, ext_field, prov_field in psp_sessions:
        try:
            session = model.objects.get(pay_in=pay_in)
            result[f"{psp_name}_external_id"] = getattr(session, ext_field, "") or ""
            result[f"{psp_name}_provider_id"] = getattr(session, prov_field, "") or ""
            result[f"{psp_name}_last_status"] = getattr(session, "last_notified_state", "") or getattr(session, "last_notified_status", "") or ""
        except model.DoesNotExist:
            pass

    # Melbet session
    try:
        from payments.integrations.melbet.models import MelbetTransactionSession
        msession = MelbetTransactionSession.objects.filter(pay_in=pay_in).first()
        if msession:
            result["melbet_session_id"] = str(msession.id)
            result["melbet_order_id"] = msession.order_id or ""
    except Exception:
        pass

    # Appeals
    from appeals.models import PayInAppeal
    appeals = PayInAppeal.objects.filter(pay_in=pay_in).order_by("-created_at")[:5]
    if appeals:
        result["appeals"] = [
            {"id": str(a.id), "status": a.status, "created_at": str(a.created_at)}
            for a in appeals
        ]

    return result


@api_view(["POST"])
@permission_classes([TgBotPermission])
def init_chat(request):
    counterparty_id = (request.data.get("counterparty_id") or "").strip()
    chat_id = request.data.get("chat_id")
    if not counterparty_id or chat_id is None:
        return Response(
            {"ok": False, "message": "Нужны counterparty_id и chat_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ok, message = init_telegram_chat(
        counterparty_id=counterparty_id,
        chat_id=int(chat_id),
        title=(request.data.get("title") or "").strip(),
        registered_by_username=(request.data.get("registered_by_username") or "").strip(),
    )
    code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return Response({"ok": ok, "message": message}, status=code)


@api_view(["POST"])
@permission_classes([TgBotPermission])
def chat_role(request):
    chat_id = request.data.get("chat_id")
    if chat_id is None:
        return Response(
            {"ok": False, "role": "unknown", "message": "Нужен chat_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        role = chat_role_for_telegram(int(chat_id))
    except (TypeError, ValueError):
        return Response(
            {"ok": False, "role": "unknown", "message": "Некорректный chat_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"ok": True, "role": role})


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([TgBotPermission])
def process_message(request):
    chat_id = request.data.get("chat_id")
    message_id = request.data.get("message_id")
    text = request.data.get("text") or ""
    uploaded = request.FILES.get("file")

    if chat_id is None or message_id is None:
        return Response(
            {"ok": False, "message": "Нужны chat_id и message_id.", "recognized": False, "outcome": "rejected"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ticket_uploaded = request.FILES.get("ticket_file")
    ticket_file_bytes = ticket_uploaded.read() if ticket_uploaded else None
    if uploaded is None:
        file_bytes = b""
        filename = ""
    else:
        file_bytes = uploaded.read()
        filename = uploaded.name or "receipt"

    try:
        result = process_merchant_appeal_message(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=text,
            file_bytes=file_bytes,
            filename=filename,
            ticket_file_bytes=ticket_file_bytes,
        )
    except Exception as exc:
        return Response(
            {
                "ok": False,
                "message": "",
                "recognized": False,
                "outcome": "rejected",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if result.outcome == "skip":
        return Response(
            {"ok": False, "skip": True, "message": "", "recognized": False, "outcome": "skip"},
            status=status.HTTP_200_OK,
        )

    code = (
        status.HTTP_200_OK
        if result.ok or result.outcome in {"await_receipt", "duplicate"}
        else status.HTTP_400_BAD_REQUEST
    )
    return Response(
        {
            "ok": result.ok,
            "message": result.message,
            "recognized": result.recognized,
            "outcome": result.outcome,
        },
        status=code,
    )


@api_view(["GET"])
@permission_classes([TgBotPermission])
def pending_inline_clicks(request):
    appeals = (
        PayInAppeal.objects.filter(
            merchant_inline_clicked=False,
            source_telegram_chat_id__isnull=False,
            source_telegram_message_id__isnull=False,
            status__in=[PayInAppealStatus.APPROVED, PayInAppealStatus.REJECTED],
        )
        .order_by("created_at")[:50]
    )
    items = [
        {
            "id": str(appeal.id),
            "chat_id": appeal.source_telegram_chat_id,
            "message_id": appeal.source_telegram_message_id,
            "approved": appeal.status == PayInAppealStatus.APPROVED,
        }
        for appeal in appeals
    ]
    return Response({"ok": True, "items": items})


@api_view(["POST"])
@permission_classes([TgBotPermission])
def mark_inline_clicked(request):
    appeal_id = (request.data.get("id") or "").strip()
    if not appeal_id:
        return Response({"ok": False, "message": "Нужен id."}, status=status.HTTP_400_BAD_REQUEST)
    updated = PayInAppeal.objects.filter(id=appeal_id).update(merchant_inline_clicked=True)
    if not updated:
        return Response({"ok": False, "message": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([TgBotPermission])
def lookup_deal(request):
    """GET /api/v1/bot/appeals/lookup/?q=<any_id> — все ID по сделке."""
    from appeals.id_resolve import resolve_pay_in_from_message

    query = (request.query_params.get("q") or "").strip()
    if not query:
        return Response(
            {"ok": False, "message": "Параметр q обязателен."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    resolved = resolve_pay_in_from_message(query)
    if not resolved.ok or resolved.pay_in is None:
        return Response(
            {"ok": False, "message": resolved.error_message or "Заявка не найдена."},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = _collect_deal_ids(resolved.pay_in)
    return Response({"ok": True, "data": data})
