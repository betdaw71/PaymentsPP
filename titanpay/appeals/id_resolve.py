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
# Telegram captions sometimes wrap a UUID mid-token across lines.
WRAPPED_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}\s*-\s*[0-9a-fA-F]{4}\s*-\s*[0-9a-fA-F]{4}\s*-\s*"
    r"[0-9a-fA-F]{4}\s*-\s*[0-9a-fA-F]{12}",
    re.MULTILINE,
)
COMPACT_UUID32_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")
COMPACT_HEX8_RE = re.compile(r"^[0-9a-fA-F]{8}$")
GENERIC_ID_LABEL_RE = re.compile(
    r"(?:^|[\s])(?:ID|uuid|pay[_-]?in|invoice|deal)\s*[:：#]?\s*([A-Za-z0-9._-]{6,64})",
    re.IGNORECASE | re.MULTILINE,
)
BARE_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]{6,64}")

# Melbet / merchant ticket: "📜 Заказ: 22924514129" (ID may wrap to the next line)
ORDER_LABEL_RE = re.compile(
    r"(?:Заказ|Order(?:\s*ID)?|ID\s*заказа|номер заказа|merchant[_ ]?order(?:[ _]?id)?)\s*[:：]\s*"
    r"[\r\n\s]*([A-Za-z0-9._-]{3,64})",
    re.IGNORECASE,
)
# "🎟 Тикет #6620b1cb" / "Тикет №6620b1cb" / "Ticket: 6620b1cb"
TICKET_LABEL_RE = re.compile(
    r"(?:Тикет|Ticket)\s*[#№n]?\s*[:：]?\s*([0-9a-fA-F]{8})\b",
    re.IGNORECASE,
)
PSP_NUMBER_RE = re.compile(
    r"(?:Номер в [ПГ]?ПС|PSP(?:\s*ID)?|provider[_ ]?(?:id|order))\s*[:：]\s*"
    r"[\r\n\s]*([A-Za-z0-9._-]{3,64})",
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

    def _add(value: str) -> None:
        normalized = value.lower()
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)

    for match in UUID_RE.findall(text):
        _add(match)
    for match in WRAPPED_UUID_RE.findall(text):
        compacted = re.sub(r"\s+", "", match)
        if UUID_RE.fullmatch(compacted):
            _add(compacted)
    for compact in COMPACT_UUID32_RE.findall(text):
        dashed = (
            f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
            f"{compact[16:20]}-{compact[20:32]}"
        )
        _add(dashed)
    return out


def normalize_appeal_text(text: str) -> str:
    """Flatten Telegram wrapping so wrapped UUIDs / IDs resolve like /lookup one-liners."""
    raw = (text or "").replace("\u00a0", " ").replace("\u202f", " ")
    # Join hyphen-broken UUID fragments: "...a1b2-\n3c4d-..." -> "...a1b2-3c4d-..."
    raw = re.sub(r"-\s*\n\s*", "-", raw)
    # Also collapse lone newlines inside hex runs without losing intentional paragraphs.
    raw = re.sub(
        r"([0-9a-fA-F]{4,})\s*\n\s*([0-9a-fA-F-]{4,})",
        r"\1\2",
        raw,
    )
    return raw


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
    text = normalize_appeal_text(text)
    order_ids = [m.group(1).strip() for m in ORDER_LABEL_RE.finditer(text)]
    order_ids.extend(m.group(1).strip() for m in GENERIC_ID_LABEL_RE.finditer(text))
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

    from payments.integrations.melbet.models import MelbetTransactionSession

    session = (
        MelbetTransactionSession.objects.filter(id=parsed, pay_in__isnull=False)
        .select_related("pay_in", "pay_in__merchant", "pay_in__order")
        .first()
    )
    if session and session.pay_in:
        return session.pay_in

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


def _session_pay_in(session) -> PayIn | None:
    from payments.models import PayIn

    if session is None:
        return None
    pay_in_id = getattr(session, "pay_in_id", None)
    if not pay_in_id:
        return None
    return PayIn.objects.filter(id=pay_in_id).select_related("merchant", "order").first()


def _pay_in_for_psp_id(value: str) -> PayIn | None:
    from payments.models import (
        BitzonePayInSession,
        BotonpayPayInSession,
        ConcoredPayInSession,
        ExpayonePayInSession,
        FairpayPayInSession,
        GipayPayInSession,
        PaymapPayInSession,
        PayplatPayInSession,
        PlaymentsPayInSession,
        PlutusPayInSession,
        ProtocolPayInSession,
        SyndicatePayInSession,
        VisionxPayInSession,
    )

    candidate = (value or "").strip()
    if not candidate:
        return None

    lookups: list[tuple[object, dict]] = [
        (BotonpayPayInSession, {"provider_deal_uuid": candidate}),
        (BotonpayPayInSession, {"external_id": candidate}),
        (GipayPayInSession, {"provider_payment_id": candidate}),
        (GipayPayInSession, {"external_id": candidate}),
        (VisionxPayInSession, {"provider_invoice_id": candidate}),
        (VisionxPayInSession, {"provider_deal_id": candidate}),
        (VisionxPayInSession, {"external_id": candidate}),
        (PayplatPayInSession, {"provider_order_id": candidate}),
        (PayplatPayInSession, {"external_id": candidate}),
        (BitzonePayInSession, {"provider_transaction_id": candidate}),
        (BitzonePayInSession, {"external_id": candidate}),
        (ProtocolPayInSession, {"provider_payment_id": candidate}),
        (ProtocolPayInSession, {"external_id": candidate}),
        (ExpayonePayInSession, {"provider_order_id": candidate}),
        (ExpayonePayInSession, {"external_id": candidate}),
        (SyndicatePayInSession, {"provider_order_id": candidate}),
        (SyndicatePayInSession, {"external_id": candidate}),
        (PlutusPayInSession, {"provider_trade_uuid": candidate}),
        (PlutusPayInSession, {"external_id": candidate}),
        (PaymapPayInSession, {"provider_invoice_id": candidate}),
        (PaymapPayInSession, {"external_id": candidate}),
        (ConcoredPayInSession, {"provider_payment_id": candidate}),
        (ConcoredPayInSession, {"external_id": candidate}),
        (PlaymentsPayInSession, {"external_id": candidate}),
        (PlaymentsPayInSession, {"provider_deposit_id": candidate}),
    ]
    if candidate.isdigit():
        lookups.append((FairpayPayInSession, {"provider_order_id": int(candidate)}))
    lookups.append((FairpayPayInSession, {"external_id": candidate}))

    for model, filters in lookups:
        session = model.objects.filter(**filters).select_related("pay_in").first()
        pay_in = _session_pay_in(session)
        if pay_in:
            return pay_in
    return None


def _unique_pay_ins(pay_ins: list[PayIn]) -> list[PayIn]:
    unique: dict[str, PayIn] = {}
    for pay_in in pay_ins:
        unique[str(pay_in.id)] = pay_in
    return list(unique.values())


def _looks_like_loose_id_token(value: str) -> bool:
    token = (value or "").strip()
    if len(token) < 6 or len(token) > 64:
        return False
    if token.isdigit():
        return 6 <= len(token) <= 24
    if UUID_RE.fullmatch(token) or COMPACT_UUID32_RE.fullmatch(token) or COMPACT_HEX8_RE.fullmatch(token):
        return True
    if "-" in token or "_" in token:
        return True
    return False


def _pay_in_for_any_id(value: str) -> PayIn | None:
    pay_in = _pay_in_for_uuid(value)
    if pay_in:
        return pay_in
    pay_in = _pay_in_for_merchant_order_id(value)
    if pay_in:
        return pay_in
    pay_in = _pay_in_for_psp_id(value)
    if pay_in:
        return pay_in
    if COMPACT_HEX8_RE.fullmatch((value or "").strip()):
        return _pay_in_for_compact_prefix(value)
    return None


def resolve_pay_in_from_message(text: str) -> ResolveResult:
    raw = normalize_appeal_text(text)
    uuids = extract_uuids(raw)
    hints = parse_appeal_ticket(raw)
    recognized = bool(uuids or hints.has_ids or is_merchant_appeal_ticket(raw))

    pay_ins: list[PayIn] = []
    for value in uuids:
        pay_in = _pay_in_for_uuid(value)
        if pay_in:
            pay_ins.append(pay_in)
        else:
            pay_in = _pay_in_for_psp_id(value)
            if pay_in:
                pay_ins.append(pay_in)

    for order_id in hints.merchant_order_ids:
        pay_in = _pay_in_for_any_id(order_id)
        if pay_in:
            pay_ins.append(pay_in)

    if not pay_ins:
        for psp_id in hints.psp_ids:
            pay_in = _pay_in_for_any_id(psp_id)
            if pay_in:
                pay_ins.append(pay_in)

    if not pay_ins:
        for hex8 in hints.ticket_hexes:
            pay_in = _pay_in_for_compact_prefix(hex8)
            if pay_in:
                pay_ins.append(pay_in)

    if not pay_ins:
        for line in raw.splitlines():
            candidate = line.strip().strip(".,;#")
            if not candidate:
                continue
            if not _looks_like_loose_id_token(candidate) and not UUID_RE.search(candidate):
                continue
            pay_in = _pay_in_for_any_id(candidate)
            if pay_in:
                pay_ins.append(pay_in)

    if not pay_ins:
        for token in BARE_ID_TOKEN_RE.findall(raw):
            if not _looks_like_loose_id_token(token):
                continue
            pay_in = _pay_in_for_any_id(token)
            if pay_in:
                pay_ins.append(pay_in)

    unique = _unique_pay_ins(pay_ins)
    if not unique:
        if recognized:
            return ResolveResult(
                ok=False,
                error_code="not_found",
                error_message="Апелляция не принята: ID не распознан.",
                recognized=True,
            )
        return ResolveResult(
            ok=False,
            error_code="no_id",
            error_message="Апелляция не принята: ID не распознан.",
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
