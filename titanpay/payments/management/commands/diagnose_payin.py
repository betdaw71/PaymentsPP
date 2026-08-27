"""Диагностика отклонённого pay-in: роутинг, PSP, видимость в ЛК."""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from payments.models import (
    BitzonePayInSession,
    BotonpayPayInSession,
    ConcoredPayInSession,
    ExpayonePayInSession,
    FairpayPayInSession,
    GipayPayInSession,
    PayplatPayInSession,
    VisionxPayInSession,
    PayIn,
    PayInTraceLog,
    PaymapPayInSession,
    PlutusPayInSession,
    ProtocolPayInSession,
    SyndicatePayInSession,
)
from payments.psp_payin import psp_create_failure_reason_internal
from trade.models import InOrder, Transaction
from trade.routing.base import route
from trade.routing.routeutils import get_teams_for_ps
from basics.models import PaymentDetailsGroup, PaymentDetails, TraderTeamRates


class Command(BaseCommand):
    help = "Разбор pay-in по UUID: почему Declined и почему не видно в ЛК саппорта"

    def add_arguments(self, parser):
        parser.add_argument("pay_in_id", type=str, help="UUID pay-in (поле id) или merchant_order_id")

    def handle(self, *args, **options):
        pid = options["pay_in_id"].strip()
        qs = PayIn.objects.select_related(
            "status",
            "currency",
            "payment_system",
            "merchant",
            "merchant__user",
            "order",
            "order__status",
            "order__solution",
            "order__solution__merchant",
            "order__solution__payment_system",
            "order__solution__traffic",
            "order__payment_details",
            "order__payment_details__group",
            "order__payment_details__group__trader",
            "order__payment_details__group__trader__user",
            "order__payment_details__group__trader__team",
        )
        try:
            pay_in = qs.get(id=pid)
        except PayIn.DoesNotExist:
            by_moid = qs.filter(merchant_order_id=pid).order_by("-created_at").first()
            if by_moid is None:
                raise CommandError(
                    f"PayIn {pid} не найден в БД (ни по id, ни по merchant_order_id). "
                    f"Используйте поле id из ответа create, не merchant_order_id клиента."
                )
            pay_in = by_moid
            self.stdout.write(
                self.style.WARNING(f"Найден по merchant_order_id (последний): {pay_in.id}")
            )

        self.stdout.write(self.style.HTTP_INFO(f"\n=== PayIn {pay_in.id} ==="))
        self.stdout.write(f"status:           {pay_in.status.name if pay_in.status else None}")
        self.stdout.write(f"recalculated:     {pay_in.recalculated}")
        self.stdout.write(f"merchant:         {pay_in.merchant.user.username if pay_in.merchant else None}")
        self.stdout.write(f"merchant_order:   {pay_in.merchant_order_id}")
        self.stdout.write(f"amount:           {pay_in.amount} {pay_in.currency.symbol if pay_in.currency else ''}")
        self.stdout.write(f"payment_system:   {pay_in.payment_system.name if pay_in.payment_system else None}")
        self.stdout.write(f"created_at:       {pay_in.created_at}")

        order = pay_in.order
        if not order:
            self.stdout.write(self.style.ERROR("InOrder: отсутствует"))
            return

        self.stdout.write(self.style.HTTP_INFO(f"\n=== InOrder {order.id} ==="))
        self.stdout.write(f"status:           {order.status.name if order.status else None}")
        self.stdout.write(f"recalculated:     {order.recalculated}")
        if order.recalculated:
            self.stdout.write(f"recalc_amount:    {order.recalculated_amount}")
        self.stdout.write(f"payment_details:  {order.payment_details_id}")
        if order.payment_details:
            self.stdout.write(
                f"routed_trader:    {order.payment_details.group.trader.user.username} "
                f"(PS виртуальной группы = payment_system заявки; expayone1/protocol1 — по включённым группам)"
            )
        if order.payment_details:
            g = order.payment_details.group
            self.stdout.write(f"trader:           {g.trader.user.username}")
            self.stdout.write(f"team:             {g.trader.team.name}")
            self.stdout.write(f"group:            {g.id} ({g.owner})")

        self.stdout.write(self.style.HTTP_INFO("\n=== Причина (внутренняя, не для мерчанта) ==="))
        self.stdout.write(psp_create_failure_reason_internal(pay_in))
        self.stdout.write(self.style.HTTP_INFO("\n=== Ответ мерчанту (API) ==="))
        from payments.psp_payin import merchant_decline_payload
        self.stdout.write(str(merchant_decline_payload(pay_in)))

        self.stdout.write(self.style.HTTP_INFO("\n=== PSP sessions ==="))
        for label, model in (
            ("ExpayOne", ExpayonePayInSession),
            ("FairPay", FairpayPayInSession),
            ("Protocol", ProtocolPayInSession),
            ("GiPay", GipayPayInSession),
            ("VisionX", VisionxPayInSession),
            ("PayPlat", PayplatPayInSession),
            ("Concored", ConcoredPayInSession),
            ("PayMap", PaymapPayInSession),
            ("Bitzone", BitzonePayInSession),
            ("BotonPay", BotonpayPayInSession),
            ("Plutus", PlutusPayInSession),
            ("Syndicate", SyndicatePayInSession),
        ):
            try:
                s = model.objects.get(pay_in=pay_in)
            except model.DoesNotExist:
                self.stdout.write(f"{label}: нет сессии")
                continue
            self.stdout.write(f"\n{label} session:")
            if label == "Bitzone":
                self.stdout.write(f"  provider_id:      {getattr(s, 'provider_transaction_id', '')}")
                self.stdout.write(f"  external_id:      {getattr(s, 'external_id', '')}")
                self.stdout.write(f"  last_status:      {getattr(s, 'last_notified_status', '')}")
                wh = s.last_webhook_payload or {}
                if wh:
                    self.stdout.write(
                        f"  last_webhook:     status={wh.get('status')} "
                        f"fiat={wh.get('fiatAmount')} "
                        f"disputeTrader={wh.get('disputeTraderFiatAmount')} "
                        f"disputeMerchant={wh.get('disputeMerchantFiatAmount')}"
                    )
            elif label == "BotonPay":
                from payments.psp_payin import _botonpay_deal_uuid_from_session

                self.stdout.write(f"  platform_pay_in:  {getattr(s, 'external_id', '')}")
                self.stdout.write(f"  botonpay_deal_id: {_botonpay_deal_uuid_from_session(s)}")
                self.stdout.write(f"  last_status:      {getattr(s, 'last_notified_status', '')}")
            cr = s.create_response or {}
            self.stdout.write(json.dumps(cr, ensure_ascii=False, indent=2, default=str)[:4000])

        if order.status and order.status.name == "Cannot process":
            self._explain_in_order_create_failure(pay_in, order)
            if self._has_psp_api_attempt(pay_in):
                self.stdout.write(
                    self.style.WARNING(
                        "\nРоутинг подобрал PSP-реквизит, но API провайдера не вернул реквизиты "
                        "→ InOrder «Cannot process», PayIn Declined."
                    )
                )
            else:
                self._routing_diagnosis(pay_in, order)
        elif order.status and order.status.name == "Cancelled" and pay_in.status.name == "Declined":
            self.stdout.write(
                self.style.WARNING(
                    "\nРоутинг прошёл, но PSP не выдал реквизиты → InOrder Cancelled (старая логика)."
                )
            )

        self.stdout.write(self.style.HTTP_INFO("\n=== Видимость в ЛК саппорта ==="))
        if order.status and order.status.name == "Cannot process":
            self.stdout.write(
                "InOrder «Cannot process» — вкладка «Отклонённые» или «Все» в ЛК саппорта "
                "(нужен deploy fix в trade/viewsets.py _support_in_orders_queryset)."
            )
        elif order.status and order.status.name == "Cancelled":
            self.stdout.write("Должна быть во вкладке «Отклонённые» (не «Активные»).")
        self.stdout.write(f"Поиск по InOrder id: {order.id}")
        self.stdout.write(f"Поиск по merchant_order_id: {pay_in.merchant_order_id}")
        self.stdout.write(f"Полный HTTP trace: python manage.py payin_trace {pay_in.id}")

    def _explain_in_order_create_failure(self, pay_in, order):
        """Различить отказ choose_trader_in и сбой freeze() до вызова Concored/других PSP."""
        self.stdout.write(self.style.HTTP_INFO("\n=== InOrder.create (до PSP) ==="))
        fees_set = (order.merchant_fee or 0) > 0 or (order.trader_fee or 0) > 0
        freeze_tx = Transaction.objects.filter(
            linked_in_order=order,
            transaction_type__name="Freeze",
        ).exists()
        if fees_set and not freeze_tx:
            self.stdout.write(
                self.style.ERROR(
                    "Причина: роутинг подобрал трейдера, но freeze() не прошёл "
                    "(недостаточно balance_usdt у трейдера на момент создания). "
                    "Concored/PSP API не вызывались."
                )
            )
            self.stdout.write(
                f"  usd_amount заявки: {order.usd_amount}  "
                f"merchant_fee={order.merchant_fee} trader_fee={order.trader_fee}"
            )
        elif not fees_set:
            self.stdout.write(
                "Причина: choose_trader_in не нашёл свободную группу/карту при создании "
                "(баланс, лимиты, traffic, in_active, команда без rates и т.д.). "
                "Concored/PSP API не вызывались."
            )
        else:
            self.stdout.write("Неожиданное состояние: есть Freeze-транзакция при Cannot process.")

        trace = (
            PayInTraceLog.objects.filter(pay_in=pay_in, direction="routing")
            .order_by("created_at")
            .first()
        )
        if trace and isinstance(trace.body, dict):
            self.stdout.write(
                f"PayInTraceLog routing: trader={trace.body.get('trader')} "
                f"payment_details_id={trace.body.get('payment_details_id')}"
            )
        elif not PayInTraceLog.objects.filter(pay_in=pay_in).exists():
            self.stdout.write(
                self.style.WARNING(
                    "PayInTraceLog пуст — заявка до deploy trace или без migrate 0011; "
                    "повторите тест после деплоя."
                )
            )

    def _has_psp_api_attempt(self, pay_in) -> bool:
        for model in (
            ExpayonePayInSession,
            FairpayPayInSession,
            ProtocolPayInSession,
            GipayPayInSession,
            VisionxPayInSession,
            PayplatPayInSession,
            ConcoredPayInSession,
            PaymapPayInSession,
            BitzonePayInSession,
            BotonpayPayInSession,
            PlutusPayInSession,
            SyndicatePayInSession,
        ):
            if model.objects.filter(pay_in=pay_in).exists():
                return True
        return False

    def _routing_diagnosis(self, pay_in, order):
        self.stdout.write(self.style.HTTP_INFO("\n=== Диагностика роутинга (Cannot process) ==="))
        ps = order.solution.payment_system
        traffic = order.solution.traffic
        amount = order.amount
        usd_amount = amount / ps.get_rate() if ps else Decimal(0)

        teams = get_teams_for_ps(ps)
        self.stdout.write(f"teams с TraderTeamRates для {ps.name}: {[t.name for t in teams]}")

        try:
            router = route(ps)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"route() error: {exc}"))
            return

        options = router.get_possible_options_in(None, ps, amount, traffic, usd_amount)
        self.stdout.write(f"групп после фильтра баланса/лимитов: {options.count()}")

        for g in options[:10]:
            trader = g.trader
            bal = trader.balance_usdt.amount if trader.balance_usdt else None
            self.stdout.write(
                f"  - group {g.id} trader={trader.user.username} "
                f"status={g.status} in_active={g.in_active} blocked={trader.blocked} "
                f"balance_usdt={bal} current_volume={g.current_volume} limit={g.limit_per_period}"
            )

        if not options.exists():
            all_groups = PaymentDetailsGroup.objects.filter(payment_system=ps)
            self.stdout.write(f"\nВсего групп на PS {ps.name}: {all_groups.count()}")
            self.stdout.write(f"traffic у заявки (MerchantSolution): {traffic.name} (id={traffic.id})")
            for g in all_groups:
                t = g.trader
                has_rate = TraderTeamRates.objects.filter(team=t.team, payment_system=ps).exists()
                traffics = list(g.allowed_traffic.values_list("name", flat=True))
                bal = t.balance_usdt.amount if t.balance_usdt else None
                in_teams = teams.filter(pk=t.team_id).exists()
                has_card = PaymentDetails.objects.filter(
                    group=g, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
                ).exists()
                self.stdout.write(
                    f"  group {g.id} trader={t.user.username} status={g.status} in_active={g.in_active} "
                    f"work_type={g.work_type} blocked={t.blocked} team_rated={in_teams} "
                    f"team_rates={has_rate} balance_usdt={bal} traffic={traffics} card_ok={has_card} "
                    f"vol={g.current_volume}/{g.limit_per_period}"
                )
                if traffic.name not in traffics:
                    self.stdout.write(self.style.WARNING(f"    → traffic «{traffic.name}» не в allowed_traffic группы"))
                if not in_teams:
                    self.stdout.write(self.style.WARNING("    → у команды трейдера нет TraderTeamRates на эту PS"))
                if g.work_type != "by_card":
                    self.stdout.write(self.style.WARNING(f"    → work_type={g.work_type!r}, нужно by_card"))
                if bal is not None and bal < usd_amount:
                    self.stdout.write(self.style.WARNING(f"    → balance_usdt {bal} < нужно {usd_amount}"))

        active = InOrder.objects.filter(
            status__name__in=["New", "Money sent by user"],
            amount=amount,
            solution__payment_system=ps,
        )
        detail = router.choose_detail_in(amount, usd_amount, ps, traffic, active, 0)
        self.stdout.write(f"choose_detail_in → {detail.id if detail else 'None'}")
