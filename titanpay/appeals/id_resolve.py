from __future__ import annotations

import re
import uuid as uuid_lib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payments.models import PayIn

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
COMPACT_HEX8_RE = re.compile(r"^[0-9a-fA-F]{8}$")

# Melbet / merchant ticket: "📜 Заказ: 22924514129"
ORDER_LABEL_RE = re.compile(
    r"(?:Заказ|Order(?:\s*ID)?|merchant[_ ]?order(?:[ _]?id)?)\s*[:：]\s*([A-Za-z0-9._-]{3,64})",
    re.IGNORECASE,
)
# "🎟 Тикет #6620b1cb"
TICKET_LABEL_RE = re.compile(
    r"Тикет\s*#?\s*([0-9a-fA-F]{8})\b",
    re.IGNORECASE,
)
PSP_NUMBER_RE = re.compile(
    r"(?:Номер в ПС|PSP(?:\s*ID)?|provider[_ ]?(?:id|order))\s*[:：]\s*([A-Za-z0-9._-]{3,64})",
    re.IGNORECASE,
)


@dataclass
class TicketHints:
    merchant_order_ids: list[str] = field(default_factory=list)
    ticket_hexes: list[str] = field(default_factory=list)
    psp_ids: list[str] = field(default_factory=list)

    @property
    def has_ids(self) -> bool:
        return bool(self.merchant_order_ids or self.ticket_hexes or self.psp_ids)


@dataclass
class ResolveResult:
    ok: bool
    pay_in: PayIn | None = None
    error_code: str = ""
    error_message: str = ""
    recognized: bool = False


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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            continue
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def parse_appeal_ticket(text: str) -> TicketHints:
    """Extract IDs from Melbet-style tickets and other labelled merchant messages."""
    if not text:
        return TicketHints()
    order_ids = [m.group(1).strip() for m in ORDER_LABEL_RE.finditer(text)]
    ticket_hexes = [m.group(1).lower() for m in TICKET_LABEL_RE.finditer(text)]
    psp_ids = [m.group(1).strip() for m in PSP_NUMBER_RE.finditer(text)]
    return TicketHints(
        merchant_order_ids=_dedupe(order_ids),
        ticket_hexes=_dedupe(ticket_hexes),
        psp_ids=_dedupe(psp_ids),
    )


def is_merchant_appeal_ticket(text: str) -> bool:
    if not text:
        return False
    if extract_uuids(text):
        return True
    hints = parse_appeal_ticket(text)
    if hints.has_ids:
        return True
    lowered = text.lower()
    return "реквизиты из заявки" in lowered or "маска юзера" in lowered


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

    from payments.models import BotonpayPayInSession, GipayPayInSession, PayplatPayInSession, VisionxPayInSession

    session = BotonpayPayInSession.objects.filter(provider_deal_uuid=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = GipayPayInSession.objects.filter(provider_payment_id=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = VisionxPayInSession.objects.filter(provider_invoice_id=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = VisionxPayInSession.objects.filter(provider_deal_id=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = PayplatPayInSession.objects.filter(provider_order_id=str(parsed)).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    return None


def _pay_in_for_merchant_order_id(value: str) -> PayIn | None:
    from payments.models import PayIn

    candidate = (value or "").strip()
    if not candidate:
        return None

    pay_in = PayIn.objects.filter(merchant_order_id=candidate).select_related("merchant", "order").first()
    if pay_in:
        return pay_in

    from payments.integrations.melbet.models import MelbetTransactionSession

    session = (
        MelbetTransactionSession.objects.filter(order_id=candidate, pay_in__isnull=False)
        .select_related("pay_in", "pay_in__merchant", "pay_in__order")
        .first()
    )
    if session and session.pay_in:
        return session.pay_in
    return None


def _compact_id_qs(model):
    from django.db.models import CharField, Value
    from django.db.models.functions import Cast, Lower, Replace

    return model.objects.annotate(
        compact_id=Lower(Replace(Cast("id", CharField()), Value("-"), Value(""))),
    )


def _pay_in_for_compact_prefix(hex8: str) -> PayIn | None:
    from payments.models import PayIn
    from trade.models import InOrder

    prefix = (hex8 or "").strip().lower()
    if not COMPACT_HEX8_RE.fullmatch(prefix):
        return None

    matches = list(
        _compact_id_qs(PayIn)
        .filter(compact_id__startswith=prefix)
        .select_related("merchant", "order")[:5]
    )
    unique = {str(p.id): p for p in matches}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        return None

    orders = list(_compact_id_qs(InOrder).filter(compact_id__startswith=prefix)[:5])
    pay_ins: list[PayIn] = []
    for order in orders:
        pay_in = PayIn.objects.filter(order=order).select_related("merchant", "order").first()
        if pay_in:
            pay_ins.append(pay_in)
    unique = {str(p.id): p for p in pay_ins}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def _pay_in_for_psp_id(value: str) -> PayIn | None:
    from payments.models import (
        BotonpayPayInSession,
        GipayPayInSession,
        PayIn,
        PayplatPayInSession,
        VisionxPayInSession,
    )

    candidate = (value or "").strip()
    if not candidate:
        return None

    session = BotonpayPayInSession.objects.filter(provider_deal_uuid=candidate).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = GipayPayInSession.objects.filter(provider_payment_id=candidate).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = VisionxPayInSession.objects.filter(provider_invoice_id=candidate).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = VisionxPayInSession.objects.filter(provider_deal_id=candidate).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    session = PayplatPayInSession.objects.filter(provider_order_id=candidate).select_related("pay_in").first()
    if session and session.pay_in_id:
        return PayIn.objects.filter(id=session.pay_in_id).select_related("merchant", "order").first()

    return None


def _unique_pay_ins(pay_ins: list[PayIn]) -> list[PayIn]:
    unique: dict[str, PayIn] = {}
    for pay_in in pay_ins:
        unique[str(pay_in.id)] = pay_in
    return list(unique.values())


def resolve_pay_in_from_message(text: str) -> ResolveResult:
    raw = text or ""
    uuids = extract_uuids(raw)
    hints = parse_appeal_ticket(raw)
    recognized = bool(uuids or hints.has_ids or is_merchant_appeal_ticket(raw))

    pay_ins: list[PayIn] = []
    for value in uuids:
        pay_in = _pay_in_for_uuid(value)
        if pay_in:
            pay_ins.append(pay_in)

    for order_id in hints.merchant_order_ids:
        pay_in = _pay_in_for_merchant_order_id(order_id)
        if pay_in:
            pay_ins.append(pay_in)

    if not pay_ins:
        for psp_id in hints.psp_ids:
            pay_in = _pay_in_for_psp_id(psp_id)
            if pay_in:
                pay_ins.append(pay_in)

    if not pay_ins:
        for hex8 in hints.ticket_hexes:
            pay_in = _pay_in_for_compact_prefix(hex8)
            if pay_in:
                pay_ins.append(pay_in)

    if not pay_ins:
        for line in raw.splitlines():
            candidate = line.strip()
            if not candidate or UUID_RE.search(candidate) or ORDER_LABEL_RE.search(candidate):
                continue
            pay_in = _pay_in_for_merchant_order_id(candidate)
            if pay_in:
                pay_ins.append(pay_in)

    unique = _unique_pay_ins(pay_ins)
    if not unique:
        if recognized:
            return ResolveResult(
                ok=False,
                error_code="not_found",
                error_message="Заявка с указанным ID не найдена в системе.",
                recognized=True,
            )
        return ResolveResult(
            ok=False,
            error_code="no_id",
            error_message="Не удалось определить заявку: в сообщении нет ID.",
            recognized=False,
        )

    if len(unique) > 1:
        return ResolveResult(
            ok=False,
            error_code="ambiguous_id",
            error_message=(
                "В сообщении несколько ID, относящихся к разным заявкам. "
                "Отправьте чек с одним ID заявки."
            ),
            recognized=True,
        )

    return ResolveResult(ok=True, pay_in=unique[0], recognized=True)
