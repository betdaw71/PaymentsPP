"""Смоук-тест hosted payment page: HTML, obtain API, ассеты, Melbet без обязательного чека.

  docker compose exec -T app python manage.py test_payment_page
  docker compose exec -T app python manage.py test_payment_page --pay-in <uuid>
  docker compose exec -T app python manage.py test_payment_page --live
  docker compose exec -T app python manage.py test_payment_page --merchant melbet
  docker compose exec -T app python manage.py test_payment_page --create --live
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from merchant.kzt_settlement import is_melbet_merchant, melbet_kzt_usernames
from payments.models import PayIn
from payments.payment_page import payment_page
from payments.payment_page_assets import kaspi_guide_asset_path
from payments.payment_page_enrich import enrich_for_payment_page
from payments.receipt_policy import receipt_required_for_payin
from payments.utils import generate_link


class Command(BaseCommand):
    help = "Проверить, что платёжная страница открывается, obtain отвечает, чек Melbet не обязателен"

    def add_arguments(self, parser):
        parser.add_argument("--pay-in", dest="pay_in_id", help="UUID существующего PayIn")
        parser.add_argument("--merchant", default="melbet", help="username мерчанта для автопоиска заявки")
        parser.add_argument(
            "--live",
            action="store_true",
            help="Дополнительно дернуть публичные URL (pay.* / api.*)",
        )
        parser.add_argument(
            "--create",
            action="store_true",
            help="Создать тестовый Melbet deposit (callback на example.invalid, Melbet не дергается)",
        )
        parser.add_argument("--amount", default="10000", help="Сумма для --create (KZT)")
        parser.add_argument("--method", default="card2card_kzt_kaspi", help="Melbet method для --create")

    def handle(self, *args, **options):
        self._failures = 0
        self._checks = 0

        self.stdout.write(self.style.HTTP_INFO("\n=== Payment page smoke test ===\n"))
        self._static_checks()

        pay_in = None
        if options.get("create"):
            pay_in = self._create_melbet_deposit(
                merchant=options.get("merchant") or "melbet",
                amount=options.get("amount") or "10000",
                method=options.get("method") or "card2card_kzt_kaspi",
            )
        if pay_in is None:
            pay_in = self._resolve_pay_in(options.get("pay_in_id"), options.get("merchant") or "melbet")
        if pay_in is None:
            self.stdout.write(self.style.WARNING("  нет заявки этого мерчанта — obtain по живому id пропущен"))
        else:
            self._check_payin(pay_in)
            try:
                self._check_http_views(pay_in)
            except Exception as exc:  # noqa: BLE001
                self._ok("in-process HTTP checks", False, str(exc))
            if options.get("live"):
                self._check_live(pay_in)

        self._check_unknown_payin_404()

        self.stdout.write("")
        if self._failures:
            self.stdout.write(self.style.ERROR(f"FAIL {self._failures}/{self._checks} checks"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"OK {self._checks}/{self._checks} checks"))

    def _ok(self, name: str, passed: bool, detail: str = "") -> None:
        self._checks += 1
        mark = self.style.SUCCESS("OK") if passed else self.style.ERROR("FAIL")
        extra = f" — {detail}" if detail else ""
        self.stdout.write(f"  [{mark}] {name}{extra}")
        if not passed:
            self._failures += 1

    def _static_checks(self) -> None:
        tpl = Path(settings.BASE_DIR) / "templates" / "payment_page" / "pay.html"
        src = tpl.read_text(encoding="utf-8") if tpl.is_file() else ""
        self._ok("pay.html exists", tpl.is_file())
        self._ok("pay.html has obtain fetch", "obtainUrl" in src or "/obtain/" in src)
        self._ok("pay.html has Я оплатил", 'id="btn-sent"' in src)
        self._ok("pay.html hides receipt when not required", "if (!receiptRequired)" in src)
        asset = (
            Path(settings.BASE_DIR) / "payments" / "static" / "payment_page" / "kaspi-international-transfers-guide.png"
        )
        self._ok("kaspi guide png", asset.is_file(), f"{asset.stat().st_size if asset.is_file() else 0} bytes")
        self._ok("kaspi asset path", kaspi_guide_asset_path().startswith("/payment-page-assets/"))

    def _create_melbet_deposit(self, *, merchant: str, amount: str, method: str) -> PayIn:
        from payments.integrations.melbet.amount_probe import is_melbet_deposit_allocated
        from payments.integrations.melbet.models import MelbetIntegrationConfig
        from payments.integrations.melbet.services import MelbetServiceError, create_melbet_deposit, deposit_response

        cfg = (
            MelbetIntegrationConfig.objects.select_related("merchant__user")
            .filter(merchant__user__username=merchant, active=True)
            .first()
        )
        if cfg is None:
            raise CommandError(f"Нет активной MelbetIntegrationConfig для мерчанта {merchant!r}")

        order_id = f"smoke-{uuid.uuid4().hex[:12]}"
        payload = {
            "order_id": order_id,
            "amount": str(Decimal(str(amount))),
            "currency": "KZT",
            "method": method,
            "customer_account_id": f"smoke-{order_id}",
            "callback_url": "https://example.invalid/melbet-smoke",
            "success_url": "https://example.invalid/ok",
            "pending_url": "https://example.invalid/pending",
            "fail_url": "https://example.invalid/fail",
        }
        self.stdout.write(f"  creating Melbet deposit merchant={merchant} amount={payload['amount']} method={method}")
        try:
            pay_in = create_melbet_deposit(cfg, payload)
        except MelbetServiceError as exc:
            self._ok("create Melbet deposit", False, f"{exc.code} {exc}")
            raise CommandError(f"Melbet deposit failed: {exc}") from exc

        pay_in = (
            PayIn.objects.select_related(
                "status",
                "currency",
                "payment_system",
                "order__status",
                "order__payment_details__group__trader__user",
                "merchant__user",
                "melbet_session",
            )
            .get(pk=pay_in.pk)
        )
        allocated = is_melbet_deposit_allocated(pay_in)
        trader = ""
        if pay_in.order and pay_in.order.payment_details_id:
            trader = pay_in.order.payment_details.group.trader.user.username
        resp = deposit_response(pay_in)
        self._ok(
            "create Melbet deposit allocated",
            allocated,
            f"PayIn={pay_in.id} order={pay_in.order.status.name if pay_in.order else '-'} trader={trader or '-'}",
        )
        self.stdout.write(f"  redirect_url: {resp.get('redirect_url')}")
        self.stdout.write(self.style.WARNING("  тестовая заявка: после проверки отмените её в админке, Melbet не получит callback"))
        return pay_in

    def _resolve_pay_in(self, pay_in_id: str | None, merchant: str) -> PayIn | None:
        qs = PayIn.objects.select_related(
            "status",
            "currency",
            "payment_system",
            "order__status",
            "merchant__user",
            "melbet_session",
        )
        if pay_in_id:
            pay_in = qs.filter(id=pay_in_id).first()
            self._ok(f"PayIn {pay_in_id}", pay_in is not None)
            return pay_in
        names = list(melbet_kzt_usernames()) if merchant in melbet_kzt_usernames() else [merchant]
        merchant_qs = qs.filter(merchant__user__username__in=names)
        pay_in = (
            merchant_qs.filter(status__name__in=["New", "In Progress"])
            .order_by("-created_at")
            .first()
        )
        if pay_in is None:
            pay_in = merchant_qs.order_by("-created_at").first()
            if pay_in:
                self.stdout.write(
                    self.style.WARNING(
                        f"  нет активной заявки {names} — берём последнюю "
                        f"{pay_in.status.name if pay_in.status else '-'}"
                    )
                )
        if pay_in:
            self.stdout.write(
                f"  using PayIn {pay_in.id} merchant={pay_in.merchant.user.username if pay_in.merchant else '-'} "
                f"status={pay_in.status.name if pay_in.status else '-'}"
            )
        return pay_in

    def _check_payin(self, pay_in: PayIn) -> None:
        required = receipt_required_for_payin(pay_in)
        if is_melbet_merchant(pay_in.merchant):
            self._ok("Melbet receipt_required=false", required is False)
        else:
            self._ok(
                "receipt_required flag",
                True,
                f"{required} (merchant={pay_in.merchant.user.username if pay_in.merchant else '-'})",
            )
        link = generate_link(pay_in.id, pay_in.payment_system.name if pay_in.payment_system else "")
        self._ok("redirect_url generated", bool(link) and str(pay_in.id) in link, link)

    def _gate_headers(self) -> dict:
        gate = os.getenv("CLIENT_GATE", "")
        return {"GATE": gate} if gate else {}

    def _check_http_views(self, pay_in: PayIn) -> None:
        factory = RequestFactory()
        request = factory.get(f"/{pay_in.id}/")
        try:
            response = payment_page(request, pay_in.id)
        except Exception as exc:  # noqa: BLE001
            self._ok("render payment_page", False, str(exc))
            return
        self._ok("render payment_page HTTP", response.status_code == 200, str(response.status_code))
        html = response.content.decode("utf-8", errors="replace")
        self._ok("HTML contains pay_in id", str(pay_in.id) in html)
        self._ok("HTML has no traceback", "Traceback (most recent call last)" not in html)
        self._ok(
            "HTML loads obtain endpoint",
            "obtainUrl" in html and "/api/v1/payments/in/invoice/" in html and "PAY_IN_ID" in html,
        )

        from rest_framework.test import APIRequestFactory

        from payments.viewsets import PayInInvoiceViewset

        api_factory = APIRequestFactory()
        obtain_view = PayInInvoiceViewset.as_view(
            {"get": "obtain"},
            permission_classes=[],
            authentication_classes=[],
        )
        obtain = obtain_view(api_factory.get(f"/api/v1/payments/in/invoice/{pay_in.id}/obtain/"), id=pay_in.id)
        self._ok("obtain HTTP", obtain.status_code == 200, str(obtain.status_code))
        if obtain.status_code != 200:
            self.stdout.write(f"    body: {self._response_preview(obtain)}")
            return
        data = getattr(obtain, "data", None)
        if not isinstance(data, dict):
            self._ok("obtain JSON", False, self._response_preview(obtain))
            return
        order_status = pay_in.order.status.name if pay_in.order and pay_in.order.status else ""
        if is_melbet_merchant(pay_in.merchant):
            self._ok("obtain receipt_required=false", data.get("receipt_required") is False)
            actions = data.get("bank_actions") or []
            if order_status in {"New", "In Progress", "Money sent by user"}:
                self._ok(
                    "obtain Kaspi button not Homebank",
                    any((a.get("id") or "").startswith("kaspi") for a in actions)
                    and not any((a.get("id") or "") == "halyk" for a in actions),
                    str([a.get("id") for a in actions]),
                )
                guides = data.get("bank_guides") or []
                self._ok(
                    "obtain Kaspi guide image",
                    bool(guides) and "kaspi-international-transfers-guide" in str(guides[0].get("image_url") or ""),
                )
        self._ok("obtain has amount", data.get("amount") is not None, str(data.get("amount")))
        self._ok("obtain has currency", bool(data.get("currency")), str(data.get("currency")))
        self._ok(
            "obtain requisites or explicit empty",
            "requisites_available" in data,
            f"available={data.get('requisites_available')} details={bool(data.get('payment_details'))}",
        )
        if order_status in {"New", "In Progress", "Money sent by user"}:
            self._ok(
                "active deal has requisites",
                bool(data.get("requisites_available") and data.get("payment_details")),
                f"order={order_status}",
            )
        enriched = enrich_for_payment_page(dict(data), pay_in)
        self._ok("enrich does not crash", True, f"locale={enriched.get('locale')}")

        from payments.payment_page_assets import serve_payment_page_asset

        asset = serve_payment_page_asset(
            factory.get(kaspi_guide_asset_path()),
            "kaspi-international-transfers-guide.png",
        )
        self._ok(
            "kaspi asset HTTP",
            asset.status_code == 200 and str(asset.get("Content-Type", "")).startswith("image/"),
            f"{asset.status_code} {asset.get('Content-Type')}",
        )

    def _check_unknown_payin_404(self) -> None:
        missing = uuid.uuid4()
        factory = RequestFactory()
        from django.http import Http404

        try:
            payment_page(factory.get(f"/{missing}/"), missing)
            self._ok("unknown pay-in is 404", False, "view returned a page")
        except Http404:
            self._ok("unknown pay-in is 404", True)

        from rest_framework.test import APIRequestFactory

        from payments.viewsets import PayInInvoiceViewset

        obtain_view = PayInInvoiceViewset.as_view(
            {"get": "obtain"},
            permission_classes=[],
            authentication_classes=[],
        )
        obtain = obtain_view(
            APIRequestFactory().get(f"/api/v1/payments/in/invoice/{missing}/obtain/"),
            id=missing,
        )
        self._ok("unknown obtain is 404", obtain.status_code == 404, str(obtain.status_code))

    @staticmethod
    def _response_preview(response) -> str:
        data = getattr(response, "data", None)
        if data is not None:
            return repr(data)[:400]
        try:
            return repr(response.content)[:400]
        except Exception:  # noqa: BLE001
            return f"<unrendered {type(response).__name__} {getattr(response, 'status_code', '?')}>"

    def _check_live(self, pay_in: PayIn) -> None:
        import requests

        page_url = generate_link(pay_in.id, pay_in.payment_system.name if pay_in.payment_system else "")
        api_base = (getattr(settings, "PUBLIC_API_URL", "") or "").rstrip("/")
        headers = self._gate_headers()
        try:
            page = requests.get(page_url, timeout=15, allow_redirects=True)
            self._ok("live page", page.status_code == 200, f"{page.status_code} {page_url}")
            self._ok("live page has id", str(pay_in.id) in page.text)
        except requests.RequestException as exc:
            self._ok("live page", False, str(exc))
        try:
            obtain = requests.get(
                f"{api_base}/api/v1/payments/in/invoice/{pay_in.id}/obtain/",
                headers=headers,
                timeout=15,
            )
            self._ok("live obtain", obtain.status_code == 200, str(obtain.status_code))
            if obtain.status_code != 200:
                self.stdout.write(f"    body: {obtain.text[:400]}")
        except requests.RequestException as exc:
            self._ok("live obtain", False, str(exc))
        try:
            host = page_url.split(str(pay_in.id))[0].rstrip("/")
            asset = requests.get(f"{host}{kaspi_guide_asset_path()}", timeout=15)
            self._ok("live kaspi asset", asset.status_code == 200, str(asset.status_code))
        except requests.RequestException as exc:
            self._ok("live kaspi asset", False, str(exc))
