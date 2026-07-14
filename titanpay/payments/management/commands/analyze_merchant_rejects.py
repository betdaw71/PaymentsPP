"""Сводка всех отказов мерчанта: не только InOrder «Cannot process»."""
from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from payments.models import PayIn, PayInTraceLog


class Command(BaseCommand):
    help = (
        "Почему мерчант видит отказы, а Cannot process пусто. "
        "Пример: analyze_merchant_rejects --merchant pandapay --hours 6"
    )

    def add_arguments(self, parser):
        parser.add_argument("--merchant", required=True, help="username мерчанта")
        parser.add_argument("--hours", type=float, default=6)
        parser.add_argument("--ps", default="", help="фильтр payment_system, напр. C2CKZT")

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(hours=float(options["hours"]))
        merchant_name = options["merchant"].strip()
        ps = (options.get("ps") or "").strip()

        payin_qs = PayIn.objects.filter(
            created_at__gte=since,
            merchant__user__username=merchant_name,
        )
        if ps:
            payin_qs = payin_qs.filter(payment_system__name__iexact=ps)

        declined = payin_qs.filter(status__name="Declined")
        declined_total = declined.count()

        inorder_by_status = (
            declined.values("order__status__name")
            .annotate(n=Count("id"))
            .order_by("-n")
        )

        self.stdout.write(self.style.HTTP_INFO("\n=== Отказы мерчанта — сводка ==="))
        self.stdout.write(f"merchant:     {merchant_name}")
        self.stdout.write(f"period:       last {options['hours']}h (since {since:%Y-%m-%d %H:%M UTC})")
        if ps:
            self.stdout.write(f"payment_system: {ps}")
        self.stdout.write(f"PayIn total:  {payin_qs.count()}")
        self.stdout.write(f"PayIn Declined: {declined_total}")

        self.stdout.write(self.style.HTTP_INFO("\n--- InOrder status у Declined pay-in ---"))
        if not declined_total:
            self.stdout.write("  (нет Declined pay-in в окне)")
        else:
            for row in inorder_by_status:
                name = row["order__status__name"] or "(no order)"
                self.stdout.write(f"  {name:20} {row['n']}")

        cannot_process = declined.filter(order__status__name="Cannot process").count()
        cancelled = declined.filter(order__status__name="Cancelled").count()
        still_new = declined.filter(order__status__name="New").count()

        self.stdout.write(self.style.HTTP_INFO("\n--- Интерпретация ---"))
        if cannot_process:
            self.stdout.write(
                f"  Cannot process: {cannot_process} — роутинг/PSP не выдал реквизиты (ожидаемый кейс)"
            )
        if cancelled:
            self.stdout.write(
                self.style.WARNING(
                    f"  Cancelled: {cancelled} — СТАРАЯ логика (до deploy mark_inorder_cannot_process). "
                    "В фильтре «Cannot process» их не будет — смотрите «Отклонённые» / Cancelled."
                )
            )
        if still_new:
            self.stdout.write(
                self.style.ERROR(
                    f"  New: {still_new} — баг: PayIn Declined, но InOrder ещё New. "
                    "Нужен diagnose_payin по pay_in_id."
                )
            )

        # Trace: отказы до создания PayIn (валидация)
        trace_qs = PayInTraceLog.objects.filter(
            created_at__gte=since,
            merchant__user__username=merchant_name,
            direction="merchant_request",
        )
        if trace_qs.exists():
            responses = PayInTraceLog.objects.filter(
                created_at__gte=since,
                merchant__user__username=merchant_name,
                direction="merchant_response",
            )
            validation_fails = responses.filter(status_code=400, note="validation error").count()
            decline_responses = responses.filter(status_code=400, note="declined").count()
            success = responses.filter(status_code=201).count()

            self.stdout.write(self.style.HTTP_INFO("\n--- HTTP trace (PayInTraceLog) ---"))
            self.stdout.write(f"  create requests:     {trace_qs.count()}")
            self.stdout.write(f"  HTTP 201 success:    {success}")
            self.stdout.write(f"  HTTP 400 validation: {validation_fails}  ← нет PayIn в БД")
            self.stdout.write(f"  HTTP 400 declined:   {decline_responses}  ← PayIn Declined")

            if validation_fails:
                self.stdout.write(self.style.HTTP_INFO("\n--- Топ validation error ---"))
                err_counter = Counter()
                for log in responses.filter(status_code=400, note="validation error")[:500]:
                    body = log.body or {}
                    if isinstance(body, dict):
                        key = str(body.get("error") or body)[:120]
                    else:
                        key = str(body)[:120]
                    err_counter[key] += 1
                for msg, n in err_counter.most_common(10):
                    self.stdout.write(f"  [{n:4}] {msg}")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nPayInTraceLog пуст — deploy + migrate 0011_payin_trace_log для полной картины."
                )
            )

        no_record = 0
        if trace_qs.exists():
            reqs = trace_qs.count()
            created = payin_qs.count()
            # приблизительно: validation + signature до create
            responses_400_val = PayInTraceLog.objects.filter(
                created_at__gte=since,
                merchant__user__username=merchant_name,
                direction="merchant_response",
                status_code=400,
                note="validation error",
            ).count()
            no_record = responses_400_val

        self.stdout.write(self.style.HTTP_INFO("\n--- Что сказать мерчанту ---"))
        if no_record and no_record >= declined_total:
            self.stdout.write(
                "  Большинство отказов — до создания заявки (лимиты, ftd, дубликат order_id, "
                "pending pay-in, подпись). В InOrder/PayIn их нет."
            )
        elif cancelled and not cannot_process:
            self.stdout.write(
                "  Declined есть, но InOrder = Cancelled, не Cannot process. "
                "Задеплойте payments/psp_payin.py + serializers (mark_inorder_cannot_process)."
            )
        elif cannot_process:
            self.stdout.write(
                "  Cannot process есть в БД. В ЛК саппорта: вкладка «Все» или фильтр status=Cannot process. "
                "На вкладке «Активные» их не видно."
            )
        else:
            self.stdout.write(
                "  Попросите у мерчанта pay_in_id или merchant_order_id + время — "
                "python manage.py diagnose_payin <uuid>"
            )

        self.stdout.write("")
