from __future__ import annotations

import re
import uuid as uuid_lib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payments.models import PayIn

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


@dataclass
class ResolveResult:
    ok: bool
    pay_in: PayIn | None = None
    error_code: str = ""
    error_message: str = ""


def extract_uuids(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in UUID_RE.findall(text):
        normalized = match.lower()
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _pay_in_for_uuid(value: str) -> PayIn | None:
    from payments.models import PayIn
    from trade.models import InOrder

    try:
        parsed = uuid_lib.UUID(value)
    except (TypeError, ValueError):
        return None

    pay_in = PayIn.objects.filter(id=parsed).select_related("merchant", "order").first()
    if pay_in:
        return pay_in

    order = InOrder.objects.filter(id=parsed).first()
    if order:
        return PayIn.objects.filter(order=order).select_related("merchant", "order").first()

    pay_in = PayIn.objects.filter(merchant_order_id=str(parsed)).select_related("merchant", "order").first()
    if pay_in:
        return pay_in

    from payments.models import BotonpayPayInSession

    session = BotonpayPayInSession.objects.filter(provider_deal_uuid=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    return None


def resolve_pay_in_from_message(text: str) -> ResolveResult:
    uuids = extract_uuids(text)
    if not uuids:
        return ResolveResult(
            ok=False,
            error_code="no_id",
            error_message="Не удалось определить заявку: в сообщении нет ID.",
        )

    pay_ins: list[PayIn] = []
    for value in uuids:
        pay_in = _pay_in_for_uuid(value)
        if pay_in:
            pay_ins.append(pay_in)

    if not pay_ins:
        return ResolveResult(
            ok=False,
            error_code="not_found",
            error_message="Заявка с указанным ID не найдена в системе.",
        )

    unique_ids = {str(p.id) for p in pay_ins}
    if len(unique_ids) > 1:
        return ResolveResult(
            ok=False,
            error_code="ambiguous_id",
            error_message=(
                "В сообщении несколько ID, относящихся к разным заявкам. "
                "Отправьте чек с одним ID заявки."
            ),
        )

    return ResolveResult(ok=True, pay_in=pay_ins[0])
