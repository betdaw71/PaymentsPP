from payments.models import Client
from titanpay.settings import PAYMENT_PAGE_URL, CLIENT_SUCCESS_RATE
from payments.models import PayIn, PayOut, PayInStatus, PayOutStatus
from decimal import Decimal
from rest_framework.exceptions import ValidationError
import re


def assert_payin_amount_within_solution(solution, amount) -> None:
    """Лимиты MerchantSolution — частая причина Amount out of limits! при верном payment_system."""
    amt = Decimal(str(amount))
    mn = solution.min_limit_in
    mx = solution.max_limit_in
    if mn <= amt <= mx:
        return
    ps_name = solution.payment_system.name if solution.payment_system_id else ""
    payload = {
        "error": "Amount out of limits!",
        "error_code": "amount_out_of_limits",
        "payment_system": ps_name,
        "amount": str(amt),
        "min_amount": str(mn),
        "max_amount": str(mx),
        "ftd": solution.ftd,
    }
    if mx <= 0:
        payload["hint"] = "max_limit_in is not set for this method — contact support"
    raise ValidationError(payload)


def _clean_client_str(value, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if max_len is not None:
        s = s[:max_len]
    return s


def _client_id_key(client_id: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (client_id or "").lower())


def is_placeholder_client_email(email: str | None, client_id: str | None) -> bool:
    """Мерчанты иногда кладут client_id / order id в email вместо реального адреса."""
    email = _clean_client_str(email, max_len=63)
    client_id = _clean_client_str(client_id, max_len=255)
    if not email or not client_id:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    cid_key = _client_id_key(client_id)
    local_key = _client_id_key(local)
    if cid_key and local_key == cid_key:
        return True
    if local.lower() == client_id.lower():
        return True
    if domain.lower().endswith("orders.pandapay24.com"):
        return True
    return False


def normalize_client_info(client_info: dict) -> dict:
    """Нормализация client из API мерчанта перед сохранением."""
    if not isinstance(client_info, dict):
        client_info = {}
    client_id = _clean_client_str(client_info.get("client_id"), max_len=255)
    email = _clean_client_str(client_info.get("email"), max_len=63)
    phone = _clean_client_str(client_info.get("phone"), max_len=31)
    name = _clean_client_str(client_info.get("name"), max_len=63)
    if is_placeholder_client_email(email, client_id):
        email = None
    return {
        "client_id": client_id,
        "email": email,
        "phone": phone,
        "name": name,
    }


def get_client_object(client_info, merchant):
    info = normalize_client_info(client_info)
    client_id = info["client_id"]
    if not client_id:
        raise ValidationError({"client": {"client_id": "This field is required."}})

    clients = Client.objects.filter(merchant=merchant, client_id=client_id)

    if not clients.exists():
        client = Client.objects.create(
            client_id=client_id,
            merchant=merchant,
            email=info["email"],
            phone=info["phone"],
            name=info["name"],
        )
    else:
        client = clients.first()
        updates: dict[str, str | None] = {}
        if info["phone"] and client.phone != info["phone"]:
            updates["phone"] = info["phone"]
        if info["name"] and client.name != info["name"]:
            updates["name"] = info["name"]
        if client.email and is_placeholder_client_email(client.email, client_id):
            updates["email"] = info["email"]
        elif info["email"] and client.email != info["email"]:
            updates["email"] = info["email"]
        if updates:
            Client.objects.filter(pk=client.pk).update(**updates)
            client.refresh_from_db()

    if client.order_count == 0:
        return client, True

    if client.is_blacklisted:
        return client, False

    return client, True


def check_pending(client, _in=True):
    if _in:
        status = PayInStatus.objects.get(name="In Progress")
        orders = PayIn.objects.filter(client=client, status=status)
    else:
        status = PayOutStatus.objects.get(name="In Progress")
        orders = PayOut.objects.filter(client=client, status=status)

    return orders.exists()
