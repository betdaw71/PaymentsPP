"""Выбор serializer для публичного obtain pay-in invoice (платёжная страница)."""
from __future__ import annotations

from payments.models import PayIn
from payments.serializers import (
    PayInInvoiceFailSerializer,
    PayInInvoiceInProgressSerializer,
    PayInInvoiceNewSerializer,
    PayInInvoiceRetrieveSerializer,
    PayInInvoiceSuccessSerializer,
)


def payin_invoice_obtain_serializer(pay_in: PayIn):
    status_name = pay_in.status.name if pay_in.status else ""
    order_status = pay_in.order.status.name if pay_in.order and pay_in.order.status else ""

    if status_name == "Success":
        return PayInInvoiceSuccessSerializer(pay_in)
    if status_name in ("Failed", "Declined"):
        return PayInInvoiceFailSerializer(pay_in)
    if status_name == "New":
        return PayInInvoiceNewSerializer(pay_in)
    if status_name == "In Progress" and order_status in ("Money sent by user", "Arbitrage"):
        return PayInInvoiceInProgressSerializer(pay_in)
    return PayInInvoiceRetrieveSerializer(pay_in)
