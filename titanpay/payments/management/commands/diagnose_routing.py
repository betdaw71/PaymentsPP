"""Почему роутинг не находит реквизиты (Cannot process) — без создания pay-in."""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from basics.models import PaymentDetails, PaymentDetailsGroup, PaymentSystem, TraderTeamRates
from merchant.models import Merchant, MerchantSolution
from trade.models import InOrder
from trade.routing.base import route
from trade.routing.routeutils import get_teams_for_ps
from trade.utils import choose_trader_in


class Command(BaseCommand):
    help = "Диагностика роутинга pay-in: почему Cannot process для merchant+PS+amount"

    def add_arguments(self, parser):
        parser.add_argument("merchant_username", type=str)
        parser.add_argument("--ps", type=str, default="C2CKZT")
        parser.add_argument("--amount", type=str, required=True)
        parser.add_argument("--ftd", type=str, default="false", help="true / false")

    def handle(self, *args, **options):
        amount = Decimal(options["amount"])
        ps_name = options["ps"].strip()
        ftd = options["ftd"].strip().lower() in ("1", "true", "yes", "t")

        try:
            merchant = Merchant.objects.get(user__username=options["merchant_username"])
        except Merchant.DoesNotExist:
            raise CommandError(f"Merchant {options['merchant_username']!r} not found")

        sol = MerchantSolution.objects.filter(
            merchant=merchant,
            payment_system__name__iexact=ps_name,
            ftd=ftd,
            status=1,
        ).select_related("payment_system", "payment_system__currency", "traffic").first()
        if sol is None:
            raise CommandError(f"No active MerchantSolution {ps_name} ftd={ftd} for {merchant.user.username}")

        ps = sol.payment_system
        traffic = sol.traffic
        usd_amount = amount / ps.get_rate()

        self.stdout.write(self.style.HTTP_INFO(f"\n=== Routing diagnose ==="))
        self.stdout.write(f"merchant:     {merchant.user.username}")
        self.stdout.write(f"PS:           {ps.name} ({ps.currency.symbol})")
        self.stdout.write(f"amount:       {amount} (≈ {usd_amount} USDT)")
        self.stdout.write(f"ftd:          {ftd}")
        self.stdout.write(f"traffic:      {traffic.name} (id={traffic.id})")
        self.stdout.write(f"solution:     pay-in [{sol.min_limit_in} .. {sol.max_limit_in}]")

        if amount < sol.min_limit_in or amount > sol.max_limit_in:
            self.stdout.write(self.style.ERROR(
                f"✗ Сумма вне MerchantSolution [{sol.min_limit_in} .. {sol.max_limit_in}]"
            ))

        teams = get_teams_for_ps(ps)
        self.stdout.write(f"\nteams с TraderTeamRates: {[t.name for t in teams]}")
        if not teams.exists():
            self.stdout.write(self.style.ERROR(
                "✗ Нет команд с TraderTeamRates на эту PS — run shell_create_protocol_trader.py"
            ))

        try:
            router = route(ps)
        except Exception as exc:
            raise CommandError(f"route() failed: {exc}") from exc

        from basics.models import TraderTeamRates
        from payments.psp_payin import (
            get_routing_share_map,
            get_share_window_hours,
            is_psp_trader,
            psp_routing_priority_for_trader,
            share_metrics_for_groups,
            sort_groups_for_routing,
        )

        options_qs = router.get_possible_options_in(None, ps, amount, traffic, usd_amount)
        self.stdout.write(f"\nгрупп после фильтра: {options_qs.count()}")

        mdr_map = {
            (r["team_id"], r["payment_system_id"]): r["mdr_in"]
            for r in TraderTeamRates.objects.filter(payment_system=ps).values(
                "team_id", "payment_system_id", "mdr_in"
            )
        }
        sorted_groups = sort_groups_for_routing(
            options_qs.select_related("trader", "trader__user", "trader__team", "payment_system"),
            amount,
        )
        if sorted_groups:
            from payments.psp_payin import is_psp_trader

            non_psp = [
                g.trader.user.username
                for g in sorted_groups
                if g.trader and g.trader.user and not is_psp_trader(g.trader)
            ]
            if non_psp:
                self.stdout.write(
                    self.style.WARNING(
                        f"  не-PSP в выборке ({non_psp[:5]}): идут ПОСЛЕ всех PSP, приоритет payplat/gipay не сбрасывается"
                    )
                )
            share_map = get_routing_share_map()
            share_rows = share_metrics_for_groups(sorted_groups) if share_map else {}
            if share_map:
                self.stdout.write(
                    self.style.HTTP_INFO(
                        f"\nдоли трафика PSP_ROUTING_SHARE_MAP окно={get_share_window_hours()}ч "
                        f"(нормализация среди тех, кто сейчас в каскаде):"
                    )
                )
                for uname, row in share_rows.items():
                    target_pct = (row["target"] * 100).quantize(Decimal("0.1"))
                    actual_pct = (row["actual"] * 100).quantize(Decimal("0.1"))
                    deficit_pct = (row["deficit"] * 100).quantize(Decimal("0.1"))
                    self.stdout.write(
                        f"  {uname}: target={target_pct}% actual={actual_pct}% "
                        f"deficit={deficit_pct}% window_vol={row['volume']}"
                    )
                missing_shares = [
                    name for name in share_map if name not in share_rows
                ]
                if missing_shares:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  нет в текущем каскаде (доля перераспределена): {missing_shares}"
                        )
                    )
            self.stdout.write(self.style.HTTP_INFO("\nпорядок каскада (первый = будет выбран):"))
            for i, g in enumerate(sorted_groups[:15], 1):
                t = g.trader
                bal = t.balance_usdt.amount if t.balance_usdt else None
                cards = PaymentDetails.objects.filter(
                    group=g, status=1, sberpay_enabled=False, sbp_enabled=False, card_number__isnull=False
                ).count()
                traffics = list(g.allowed_traffic.values_list("name", flat=True))
                mdr = mdr_map.get((t.team_id, ps.id))
                mdr_s = f" mdr_in={mdr}%" if mdr is not None else ""
                prio = psp_routing_priority_for_trader(t)
                share = share_rows.get((t.user.username or "").strip().lower()) if t.user else None
                share_s = ""
                if share:
                    target_pct = (share["target"] * 100).quantize(Decimal("0.1"))
                    actual_pct = (share["actual"] * 100).quantize(Decimal("0.1"))
                    deficit_pct = (share["deficit"] * 100).quantize(Decimal("0.1"))
                    share_s = (
                        f" share={target_pct}% actual={actual_pct}% deficit={deficit_pct}%"
                    )
                self.stdout.write(
                    f"  {i}. group {g.id} trader={t.user.username} cascade_priority={prio}{mdr_s}{share_s} cards={cards} "
                    f"vol={g.current_volume}/{g.limit_per_period} balance_usdt={bal} traffic={traffics}"
                )

        if not options_qs.exists():
            self.stdout.write(self.style.WARNING("\n--- Все группы на PS (почему отфильтрованы) ---"))
            all_groups = PaymentDetailsGroup.objects.filter(payment_system=ps).select_related("trader", "trader__user")
            for g in all_groups:
                t = g.trader
                has_rate = TraderTeamRates.objects.filter(team=t.team, payment_system=ps).exists()
                in_team = teams.filter(pk=t.team_id).exists()
                traffics = list(g.allowed_traffic.values_list("name", flat=True))
                bal = t.balance_usdt.amount if t.balance_usdt else None
                cards = PaymentDetails.objects.filter(
                    group=g, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
                ).count()
                issues = []
                psp = is_psp_trader(t)
                if g.status != 1:
                    issues.append(f"status={g.status}")
                if not g.in_active:
                    issues.append("in_active=False")
                if g.work_type != "by_card":
                    issues.append(f"work_type={g.work_type!r}")
                if t.blocked:
                    issues.append("trader blocked")
                if not psp and not in_team:
                    issues.append("team без TraderTeamRates на PS")
                if not psp and not has_rate:
                    issues.append("нет TraderTeamRates")
                if not psp and traffic.name not in traffics:
                    issues.append(f"traffic «{traffic.name}» не в allowed_traffic {traffics}")
                if bal is not None and bal <= 0:
                    issues.append(f"balance_usdt={bal}")
                if cards == 0:
                    issues.append("нет карт")
                if not psp and g.current_volume + amount > g.limit_per_period:
                    issues.append(f"limit {g.current_volume}+{amount}>{g.limit_per_period}")
                mark = "✗" if issues else "?"
                self.stdout.write(
                    f"  {mark} group {g.id} trader={t.user.username} cards={cards} "
                    f"vol={g.current_volume}/{g.limit_per_period}"
                )
                for issue in issues:
                    self.stdout.write(self.style.WARNING(f"      → {issue}"))

        active_orders = InOrder.objects.filter(
            status__name__in=["New", "Money sent by user"],
            amount=amount,
            solution__payment_system=ps,
        )
        active_n = active_orders.count()
        if active_n:
            self.stdout.write(
                self.style.WARNING(
                    f"\nактивных заявок на сумму {amount} ({ps.name}): {active_n} "
                    "(блокируют карту при той же сумме — не PSP)"
                )
            )
            for o in active_orders.select_related("status", "payment_details__group__trader__user")[:10]:
                trader = (
                    o.payment_details.group.trader.user.username
                    if o.payment_details and o.payment_details.group
                    else "—"
                )
                self.stdout.write(f"  • {o.id} status={o.status.name} trader={trader} moid={o.merchant_order_id}")

        detail, _, _, ok = choose_trader_in(
            amount, ps, traffic, active_orders, 0, merchant=merchant,
        )
        self.stdout.write(
            self.style.HTTP_INFO(
                f"\nchoose_trader_in → {'OK group ' + str(detail.group_id) if ok else 'Cannot process'}"
            )
        )
        if not ok and active_n:
            self.stdout.write(self.style.ERROR(
                "\nВероятная причина: все карты заняты активными заявками на эту сумму.\n"
                "  • Дождитесь expire/cancel старых заявок, или\n"
                "  • Создайте pay-in с другой суммой (например amount+1), или\n"
                "  • Добавьте ещё PaymentDetails в группу трейдера."
            ))
        if not ok:
            self.stdout.write(self.style.ERROR(
                "\nФикс на сервере:\n"
                "  1) docker compose exec app python manage.py shell\n"
                "     exec(open('basics/shell_create_protocol_trader.py').read()); run()\n"
                "  2) exec(open('basics/shell_protocol_add_virtual_requisites.py').read())\n"
                "     run(extra_groups=3, sync_traffic=True)\n"
                "  3) merchant_limits pandapay --ps C2CKZT  # проверить traffic и лимиты\n"
            ))
