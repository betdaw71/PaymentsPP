"""Hosted payment page for invoice (redirect) integration."""
from __future__ import annotations

import os

from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt

from payments.models import PayIn
from payments.payment_page_enrich import resolve_locale


def _page_config() -> dict:
    return {
        "api_base": getattr(settings, "PUBLIC_API_URL", "https://api.avapay.net").rstrip("/"),
        "client_gate": os.getenv("CLIENT_GATE", ""),
        "brand": getattr(settings, "PAYMENT_PAGE_BRAND", "AvaPay"),
    }


@xframe_options_exempt
def payment_page(request, pay_in_id):
    """https://pay.{domain}/{pay_in_id} — страница оплаты для invoice-интеграции."""
    try:
        pay_in = PayIn.objects.select_related("currency", "payment_system").get(id=pay_in_id)
    except PayIn.DoesNotExist as exc:
        raise Http404("Payment not found") from exc
    ctx = {
        "pay_in_id": str(pay_in_id),
        "default_locale": resolve_locale(pay_in, request.GET.get("lang")),
        **_page_config(),
    }
    return render(request, "payment_page/pay.html", ctx)


@xframe_options_exempt
def payment_page_redirect(request, pay_in_id):
    """HTTP-редирект на success_url / failed_url мерчанта (удобно для deep links)."""
    try:
        pay_in = PayIn.objects.select_related("status").get(id=pay_in_id)
    except PayIn.DoesNotExist as exc:
        raise Http404("Payment not found") from exc

    status_name = pay_in.status.name if pay_in.status else ""
    if status_name == "Success" and pay_in.success_url:
        return HttpResponseRedirect(pay_in.success_url)
    if status_name in ("Failed", "Declined") and pay_in.failed_url:
        return HttpResponseRedirect(pay_in.failed_url)
    if status_name in ("New", "In Progress") and getattr(pay_in, "pending_url", None):
        return HttpResponseRedirect(pay_in.pending_url)
    return HttpResponseRedirect(f"/{pay_in_id}/")
