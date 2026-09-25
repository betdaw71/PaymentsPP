"""Консольный просмотр полного audit-trail pay-in (мерчант ↔ Protocol ↔ колбеки)."""
from __future__ import annotations

import json
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from payments.models import PayIn, PayInTraceLog


DIRECTION_LABELS = {
    "merchant_request": "← МЕРЧАНТ (входящий запрос create)",
    "merchant_response": "→ МЕРЧАНТ (ответ create / ошибка)",
    "routing": "↔ РОУТИНГ (InOrder после create)",
    "protocol_out_request": "→ PROTOCOL (исходящий запрос)",
    "protocol_out_response": "← PROTOCOL (ответ API)",
    "protocol_webhook": "← PROTOCOL (колбек webhook)",
    "merchant_callback": "→ МЕРЧАНТ (исходящий callback)",
}


class Command(BaseCommand):
    help = (
        "Показать все тела HTTP по pay-in: запрос мерчанта, роутинг, Protocol out/in, callback мерчанту. "
        "Примеры: payin_trace <uuid> | --merchant pandapay --hours 2 | --follow | --cannot-process"
    )

    def add_arguments(self, parser):
        parser.add_argument("pay_in_id", nargs="?", type=str, help="UUID pay-in")
        parser.add_argument("--merchant", type=str, help="Фильтр по username мерчанта, напр. pandapay")
        parser.add_argument("--merchant-order-id", type=str, help="merchant_order_id из запроса мерчанта")
        parser.add_argument("--hours", type=float, default=24, help="Окно времени для списка (часы)")
        parser.add_argument("--limit", type=int, default=50, help="Макс. pay-in в списке")
        parser.add_argument(
            "--cannot-process",
            action="store_true",
            help="Только InOrder со статусом Cannot process",
        )
        parser.add_argument(
            "--follow",
            action="store_true",
            help="Следить за новыми событиями (как tail -f), Ctrl+C для выхода",
        )
        parser.add_argument("--interval", type=float, default=2.0, help="Интервал poll в --follow (сек)")

    def handle(self, *args, **options):
        if options["follow"]:
            self._follow(options)
            return

        pay_in_id = (options.get("pay_in_id") or "").strip()
        if pay_in_id:
            self._print_payin_trace(pay_in_id)
            return

        self._list_recent(options)

    def _follow(self, options):
        self.stdout.write(self.style.HTTP_INFO("Слежение за PayInTraceLog (Ctrl+C — выход)…"))
        last_created = timezone.now()
        merchant = (options.get("merchant") or "").strip()

        while True:
            qs = PayInTraceLog.objects.select_related("pay_in", "merchant__user").filter(
                created_at__gt=last_created
            ).order_by("created_at")
            if merchant:
                qs = qs.filter(merchant__user__username=merchant)

            for entry in qs:
                self._print_entry(entry)
                last_created = entry.created_at

            time.sleep(options["interval"])

    def _print_payin_trace(self, pay_in_id: str):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from trade.models import InOrder

        pay_in = None
        try:
            pay_in = PayIn.objects.select_related(
                "status",
                "merchant__user",
                "order__status",
                "payment_system",
            ).get(id=pay_in_id)
        except (PayIn.DoesNotExist, ValueError, DjangoValidationError):
            pay_in = (
                PayIn.objects.select_related(
                    "status",
                    "merchant__user",
                    "order__status",
                    "payment_system",
                )
                .filter(merchant_order_id=pay_in_id)
                .order_by("-created_at")
                .first()
            )
            if pay_in is None:
                try:
                    order = InOrder.objects.filter(id=pay_in_id).first()
                except DjangoValidationError:
                    order = None
                if order is not None:
                    pay_in = (
                        PayIn.objects.select_related(
                            "status",
                            "merchant__user",
                            "order__status",
                            "payment_system",
                        )
                        .filter(order=order)
                        .order_by("-created_at")
                        .first()
                    )
            if pay_in is None:
                raise CommandError(
                    f"PayIn {pay_in_id} не найден (ни id, ни merchant_order_id, ни InOrder id). "
                    f"Пример: python manage.py payin_trace <pay_in_id>"
                )
            self.stdout.write(self.style.WARNING(f"Найден не по PayIn.id: {pay_in.id}"))

        self.stdout.write(self.style.HTTP_INFO(f"\n{'=' * 72}"))
        self.stdout.write(self.style.HTTP_INFO(f"PAY-IN TRACE  {pay_in.id}"))
        self.stdout.write(f"merchant:         {pay_in.merchant.user.username if pay_in.merchant else '-'}")
        self.stdout.write(f"merchant_order:   {pay_in.merchant_order_id}")
        self.stdout.write(f"pay_in status:    {pay_in.status.name if pay_in.status else '-'}")
        self.stdout.write(f"payment_system:   {pay_in.payment_system.name if pay_in.payment_system else '-'}")
        self.stdout.write(f"amount:           {pay_in.amount}")

        order = pay_in.order
        if order:
            self.stdout.write(f"in_order:         {order.id}")
            self.stdout.write(f"in_order status:  {order.status.name if order.status else '-'}")
            self.stdout.write(f"payment_details:  {order.payment_details_id or 'NULL (Cannot process / нет трейдера)'}")

        logs = PayInTraceLog.objects.filter(pay_in=pay_in).order_by("created_at")
        if not logs.exists():
            logs = PayInTraceLog.objects.filter(merchant_order_id=pay_in.merchant_order_id).order_by("created_at")

        if not logs.exists():
            self.stdout.write(self.style.WARNING("\nНет записей PayInTraceLog (нужен deploy + migrate 0011)."))
            self.stdout.write("Старые данные: python manage.py diagnose_payin " + pay_in_id)
            return

        for entry in logs:
            self._print_entry(entry)

        self.stdout.write(self.style.HTTP_INFO(f"\n{'=' * 72}\n"))

    def _list_recent(self, options):
        since = timezone.now() - timedelta(hours=options["hours"])
        merchant = (options.get("merchant") or "").strip()

        qs = PayIn.objects.filter(created_at__gte=since).select_related(
            "status", "merchant__user", "order__status", "payment_system"
        )
        if merchant:
            qs = qs.filter(merchant__user__username=merchant)
        if options["cannot_process"]:
            qs = qs.filter(order__status__name="Cannot process")
        if options.get("merchant_order_id"):
            qs = qs.filter(merchant_order_id=options["merchant_order_id"])

        qs = qs.order_by("-created_at")[: options["limit"]]

        if not qs.exists():
            self.stdout.write(self.style.WARNING("Заявок не найдено по фильтру."))
            return

        title = "Cannot process" if options["cannot_process"] else "recent pay-ins"
        self.stdout.write(self.style.HTTP_INFO(f"\n=== {title} (последние {options['limit']}, {options['hours']}h) ===\n"))
        for pay_in in qs:
            order_status = pay_in.order.status.name if pay_in.order and pay_in.order.status else "-"
            self.stdout.write(
                f"{pay_in.created_at:%Y-%m-%d %H:%M:%S}  "
                f"pay_in={pay_in.id}  "
                f"merchant={pay_in.merchant.user.username if pay_in.merchant else '-'}  "
                f"order={pay_in.merchant_order_id}  "
                f"ps={pay_in.payment_system.name if pay_in.payment_system else '-'}  "
                f"amount={pay_in.amount}  "
                f"pay_in_status={pay_in.status.name if pay_in.status else '-'}  "
                f"in_order={order_status}"
            )
            self.stdout.write(f"  → python manage.py payin_trace {pay_in.id}\n")

    def _print_entry(self, entry: PayInTraceLog):
        label = DIRECTION_LABELS.get(entry.direction, entry.direction)
        self.stdout.write(self.style.HTTP_INFO(f"\n--- {entry.created_at:%Y-%m-%d %H:%M:%S.%f}  {label} ---"))
        if entry.http_method or entry.url:
            self.stdout.write(f"HTTP: {entry.http_method} {entry.url}".strip())
        if entry.status_code is not None:
            self.stdout.write(f"status_code: {entry.status_code}")
        if entry.note:
            self.stdout.write(f"note: {entry.note}")
        if entry.pay_in_id:
            self.stdout.write(f"pay_in: {entry.pay_in_id}")
        if entry.merchant_order_id:
            self.stdout.write(f"merchant_order_id: {entry.merchant_order_id}")
        body = json.dumps(entry.body, ensure_ascii=False, indent=2, default=str)
        self.stdout.write(body)
