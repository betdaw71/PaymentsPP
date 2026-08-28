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
from payments.gipay_client import gipay_trader_username
from payments.payplat_client import payplat_trader_username
from payments.psp_payin import psp_create_failure_reason_internal, psp_trader_usernames
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
        if order.solution_id:
            self.stdout.write(
                f"ftd:              {order.solution.ftd}  "
                f"traffic={order.solution.traffic.name if order.solution.traffic_id else None}"
            )
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

        declined = bool(pay_in.status and pay_in.status.name == "Declined")
        self.stdout.write(self.style.HTTP_INFO("\n=== Причина (внутренняя, не для мерчанта) ==="))
        if declined or (order.status and order.status.name in ("Cannot process", "Cancelled")):
            self.stdout.write(psp_create_failure_reason_internal(pay_in))
        else:
            self.stdout.write(
                f"PayIn={pay_in.status.name if pay_in.status else None} "
                f"InOrder={order.status.name if order.status else None} — отказ мерчанту не отправлялся"
            )

        self.stdout.write(self.style.HTTP_INFO("\n=== Ответ мерчанту (API) ==="))
        if declined:
            from payments.psp_payin import merchant_decline_payload
            self.stdout.write(str(merchant_decline_payload(pay_in)))
        else:
            self.stdout.write("(не declined — смотри merchant_response в каскаде ниже)")

        self._print_cascade_trace(pay_in)

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

        if pay_in.payment_system_id:
            self._psp_group_status_on_ps(pay_in)

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

    def _print_routing_decision(self, body: dict) -> None:
        sol = body.get("solution") or {}
        qs = body.get("queryset") or {}
        chosen = body.get("chosen") or {}
        self.stdout.write(self.style.HTTP_INFO("  --- routing decision ---"))
        if sol:
            self.stdout.write(
                f"  solution ftd={sol.get('ftd')} traffic={sol.get('traffic')} "
                f"ps={sol.get('ps')} amount={sol.get('amount')}"
            )
        if qs:
            self.stdout.write(
                f"  queryset need_usdt={qs.get('need_usdt')} groups={qs.get('included_count')} "
                f"traders={qs.get('included_traders')}"
            )
            for row in qs.get("excluded_psp") or []:
                self.stdout.write(
                    self.style.WARNING(
                        f"    EXCLUDED {row.get('trader')} bal={row.get('balance_usdt')} "
                        f"need={row.get('need_usdt')} skip={row.get('skip')}"
                    )
                )
            for row in qs.get("included_psp") or []:
                if row.get("trader") in ("payplat1", "gipay1"):
                    over = " OVER_LIMIT" if row.get("over_group_limit") else ""
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    IN {row.get('trader')} prio={row.get('priority')} "
                            f"bal={row.get('balance_usdt')} vol={row.get('volume')}/{row.get('limit_per_period')}{over}"
                        )
                    )
        sort_rows = body.get("sort") or []
        if sort_rows:
            names = [f"{r.get('n')}:{r.get('trader')}(p={r.get('priority')})" for r in sort_rows[:10]]
            self.stdout.write(f"  sort: {names}")
        skipped = body.get("skipped") or []
        if skipped:
            self.stdout.write(f"  skipped cards: {skipped}")
        if chosen:
            self.stdout.write(
                self.style.HTTP_INFO(
                    f"  chosen={chosen.get('trader')} prio={chosen.get('priority')} "
                    f"bal={chosen.get('balance_usdt')} group={chosen.get('group_id')}"
                )
            )

    def _print_cascade_trace(self, pay_in) -> None:
        """Факт вызовов API по PayInTraceLog: кто первый, кто fallback, кого не трогали."""
        self.stdout.write(self.style.HTTP_INFO("\n=== Каскад PSP (факт, не текущие группы) ==="))
        traces = list(PayInTraceLog.objects.filter(pay_in=pay_in).order_by("created_at", "id"))
        if not traces:
            self.stdout.write(self.style.WARNING("  PayInTraceLog пуст — нет записи кто вызывался"))
            return

        first_trader = None
        had_routing_decision = False
        attempts: list[tuple[str, bool | None, str]] = []
        merchant_http = None
        for entry in traces:
            note = entry.note or ""
            body = entry.body if isinstance(entry.body, dict) else {}
            if entry.direction == "routing" and "after InOrder.create" in note:
                first_trader = body.get("trader")
                self.stdout.write(
                    f"  InOrder.create → trader={first_trader} "
                    f"in_order={body.get('in_order_status')} "
                    f"ps={body.get('payment_system')} amount={body.get('amount')}"
                )
            elif entry.direction == "routing" and note == "routing decision":
                had_routing_decision = True
                self._print_routing_decision(body)
            elif entry.direction == "routing" and note == "psp fallback candidates":
                self.stdout.write("  fallback candidates (порядок вызова):")
                for i, row in enumerate(body.get("candidates") or [], 1):
                    self.stdout.write(
                        f"    {i}. {row.get('provider')} trader={row.get('trader')} "
                        f"prio={row.get('priority')} balance_usdt={row.get('balance_usdt')}"
                    )
                if not body.get("candidates"):
                    self.stdout.write("    (пусто — PayPlat/GiPay нет в iterator)")
            elif entry.direction == "routing" and note == "psp provider api":
                attempts.append((str(body.get("provider") or "?"), body.get("success"), "first"))
            elif entry.direction == "routing" and note == "psp provider fallback":
                attempts.append((str(body.get("provider") or "?"), body.get("success"), "fallback"))
            elif entry.direction == "merchant_response":
                merchant_http = entry.status_code

        if not attempts:
            self.stdout.write(self.style.WARNING("  нет routing-записей psp provider api/fallback"))
            for entry in traces:
                if entry.direction == "routing":
                    body = entry.body if isinstance(entry.body, dict) else {}
                    self.stdout.write(f"  routing note={entry.note!r} body={body}")

        for i, (provider, ok, kind) in enumerate(attempts, 1):
            if ok is True:
                tag = self.style.SUCCESS("OK реквизит")
            elif ok is False:
                tag = self.style.ERROR("FAIL")
            else:
                tag = "?"
            self.stdout.write(f"  {i}. {provider:12} [{kind:8}] {tag}")

        tried = {p for p, _, _ in attempts}
        self.stdout.write("")
        for name in ("payplat", "gipay"):
            if name in tried:
                last = next((a for a in reversed(attempts) if a[0] == name), None)
                ok = last[1] if last else None
                msg = "вызван, реквизит выдан" if ok is True else "вызван, провайдер отказал"
                style = self.style.SUCCESS if ok is True else self.style.WARNING
                self.stdout.write(style(f"  {name}: {msg}"))
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"  {name}: API НЕ ВЫЗЫВАЛСЯ (нет сессии ≠ отказ провайдера; "
                        f"первый трейдер был {first_trader or '?'})"
                    )
                )

        if first_trader and first_trader not in ("payplat1", "gipay1"):
            self.stdout.write(
                self.style.ERROR(
                    f"  первый слот каскада = {first_trader}, а не payplat1/gipay1"
                )
            )
            if not had_routing_decision:
                self.stdout.write(
                    self.style.WARNING(
                        "  нет снимка routing decision — заявка обработана другим инстансом "
                        "или воркером без текущего кода (не этот docker compose after pull)."
                    )
                )
        if merchant_http is not None:
            self.stdout.write(f"  ответ create мерчанту HTTP {merchant_http}")

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

    def _psp_group_status_on_ps(self, pay_in) -> None:
        """Почему GiPay/PayPlat не попали в каскад (нет сессии = API не вызывался)."""
        ps = pay_in.payment_system
        if ps is None:
            return
        traffic = pay_in.order.solution.traffic if pay_in.order and pay_in.order.solution else None
        focus = (gipay_trader_username(), payplat_trader_username())
        self.stdout.write(self.style.HTTP_INFO(f"\n=== PSP группы на {ps.name} (gipay/payplat) ==="))
        if traffic is not None:
            self.stdout.write(f"  solution.traffic={traffic.name} id={traffic.id}")
        from django.contrib.auth.models import User
        from trade.routing.routeutils import get_teams_for_ps

        teams = get_teams_for_ps(ps)
        for username in focus:
            user = User.objects.filter(username=username).first()
            if user is None:
                self.stdout.write(f"  {username}: user not found")
                continue
            group = PaymentDetailsGroup.objects.filter(
                payment_system=ps,
                trader__user=user,
            ).select_related("trader").first()
            if group is None:
                self.stdout.write(self.style.ERROR(f"  {username}: нет группы на {ps.name}"))
                continue
            has_card = PaymentDetails.objects.filter(
                group=group,
                status=1,
                card_number__isnull=False,
                sberpay_enabled=False,
                sbp_enabled=False,
            ).exists()
            traffics = list(group.allowed_traffic.values_list("name", flat=True))
            traffic_ids = list(group.allowed_traffic.values_list("id", flat=True))
            in_team = teams.filter(pk=group.trader.team_id).exists()
            in_cascade = (
                group.status == 1
                and group.in_active
                and group.work_type == "by_card"
                and not group.trader.blocked
                and has_card
            )
            tag = self.style.SUCCESS if in_cascade else self.style.ERROR
            self.stdout.write(
                tag(
                    f"  {username}: group={group.id} status={group.status} in_active={group.in_active} "
                    f"card_ok={has_card} traffic={traffics} in_team={in_team}"
                )
            )
            if not in_cascade:
                self.stdout.write(
                    self.style.WARNING(
                        "    → API не вызывался: группа не в каскаде fallback "
                        "(включите shell_setup_pandapay_gipay_payplat_prod_routing.py)"
                    )
                )
            if traffic and traffic.id not in traffic_ids:
                self.stdout.write(
                    self.style.WARNING(
                        f"    → traffic «{traffic.name}» id={traffic.id} не в allowed_traffic "
                        f"(по имени={traffic.name in traffics}; PSP больше не режутся по traffic)"
                    )
                )
            if not in_team:
                self.stdout.write(
                    self.style.WARNING(
                        "    → команда трейдера без TraderTeamRates на эту PS "
                        "(PSP больше не режутся по team)"
                    )
                )

        active_psp = PaymentDetailsGroup.objects.filter(
            payment_system=ps,
            in_active=True,
            trader__user__username__in=psp_trader_usernames(),
        ).select_related("trader__user")
        names = [g.trader.user.username for g in active_psp if g.trader and g.trader.user]
        self.stdout.write(f"Все активные PSP на {ps.name}: {names or '(нет)'}")
