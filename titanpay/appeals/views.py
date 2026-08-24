from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from appeals.services import init_telegram_chat, process_merchant_appeal_message
from basics.permissions import TgBotPermission


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
def process_message(request):
    chat_id = request.data.get("chat_id")
    message_id = request.data.get("message_id")
    text = request.data.get("text") or ""
    uploaded = request.FILES.get("file")

    if chat_id is None or message_id is None:
        return Response(
            {"ok": False, "message": "Нужны chat_id и message_id."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded is None:
        return Response({"ok": False, "skip": True, "message": ""}, status=status.HTTP_200_OK)

    file_bytes = uploaded.read()
    filename = uploaded.name or "receipt"

    ok, message = process_merchant_appeal_message(
        chat_id=int(chat_id),
        message_id=int(message_id),
        text=text,
        file_bytes=file_bytes,
        filename=filename,
    )
    code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return Response({"ok": ok, "message": message}, status=code)
