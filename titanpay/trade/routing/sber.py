from merchant.models import Merchant, MerchantSolution
from basics.models import PaymentDetails, PaymentSystem, Trader, PaymentDetailsGroup, TrafficType
from rest_framework.exceptions import ValidationError
from django.db.models import F, ExpressionWrapper, DecimalField, Q, Value
import random
import re
from decimal import Decimal

from trade.routing.ps_names import routing_payment_systems
from trade.routing.routeutils import get_teams_for_payment_systems, in_order_amount_q
from payments.psp_payin import DISABLED_PSP_TRADER_USERNAMES, psp_trader_usernames


class SberRouting:
    def get_possible_options_in(self, risk_cluster, payment_system: PaymentSystem, amount, traffic_type: TrafficType, usd_amount):
        route_ps = routing_payment_systems(payment_system)
        teams = get_teams_for_payment_systems(route_ps)
        psp_users = psp_trader_usernames()
        # PSP-виртуальные группы: не режем по team/traffic — иначе payplat1/gipay1
        # выпадают из каскада, если MerchantSolution.traffic ≠ Standard.
        psp_q = Q(trader__user__username__in=psp_users)
        need = Decimal(str(usd_amount or 0))
        psp_need = ExpressionWrapper(
            Value(need) - F("trader__credit_limit"),
            output_field=DecimalField(max_digits=32, decimal_places=2),
        )
        balance_ok = (Q(trader__balance_usdt__amount__gte=need) & ~psp_q) | (
            psp_q & Q(trader__balance_usdt__amount__gte=psp_need)
        )
        base = PaymentDetailsGroup.objects.filter(
            work_type="by_card",
            status=1,
            payment_system__in=route_ps,
            in_active=True,
            trader__blocked=False,
        ).exclude(trader__user__username__in=DISABLED_PSP_TRADER_USERNAMES).filter(balance_ok)
        regular_q = Q(trader__team__in=teams, allowed_traffic=traffic_type)
        possible_options = base.filter(psp_q | regular_q).distinct()

        filtered_options = possible_options.annotate(
            total_value=ExpressionWrapper(
                F("current_volume") + amount,
                output_field=DecimalField(max_digits=32, decimal_places=2),
            )
        ).filter(Q(total_value__lte=F("limit_per_period")) | psp_q).filter(
            in_order_amount_q(amount, psp_q=psp_q)
        )
        try:
            from payments.payin_trace import record_in_queryset

            record_in_queryset(
                payment_system=payment_system,
                traffic_type=traffic_type,
                amount=amount,
                usd_amount=usd_amount,
                options_qs=filtered_options,
            )
        except Exception:
            import logging
            logging.getLogger("payin.trace").exception("routing queryset snapshot failed")
        return filtered_options
    
    def get_details(self, possible_options, active_orders, amount, merchant=None, payment_system=None):
        from payments.deal_margin import margin_ok_for_group
        from payments.payin_trace import record_in_sort_and_pick
        from payments.psp_payin import (
            apply_preferred_psp_order,
            is_preferred_payin_psp,
            is_psp_trader,
            sort_groups_for_routing,
        )
        from merchant.kzt_settlement import melbet_kzt_test_trader_username

        chosen_group = apply_preferred_psp_order(
            sort_groups_for_routing(
                possible_options.select_related(
                    "trader",
                    "trader__user",
                    "trader__team",
                    "trader__team__teamlead",
                    "payment_system",
                    "trader__balance_usdt",
                ),
                amount,
                merchant=merchant,
                payment_system=payment_system,
            ),
            merchant=merchant,
            payment_system=payment_system,
        )

        preferred = melbet_kzt_test_trader_username(merchant)
        if preferred:
            pref = [g for g in chosen_group if g.trader.user.username == preferred]
            if pref:
                chosen_group = pref + [g for g in chosen_group if g.trader.user.username != preferred]

        active_details = PaymentDetails.objects.filter(inorders__in=active_orders)
        skipped = []
        margin_ps = payment_system

        from trade.routing.deal_spacing import group_skip_reason_for_deal_spacing
        from trade.routing.human_fair import (
            exclude_overloaded_details,
            fair_routing_enabled,
            fetch_group_load_stats,
            should_skip_fair_share,
        )

        human_groups = [
            g for g in chosen_group
            if not is_psp_trader(g.trader) and not is_preferred_payin_psp(g.trader)
        ]
        human_load = {}
        if fair_routing_enabled() and human_groups:
            human_load = fetch_group_load_stats([g.id for g in human_groups])

        from payments.astrum_client import astrum_trader_allowed_for_merchant

        for idx, group in enumerate(chosen_group):
            uname = group.trader.user.username if group.trader and group.trader.user else "?"
            if not astrum_trader_allowed_for_merchant(
                group.trader, merchant, payment_system=payment_system
            ):
                skipped.append({
                    "trader": uname,
                    "group_id": str(group.id),
                    "skip": "astrum_local_other_merchant",
                })
                continue
            is_human = not is_psp_trader(group.trader) and not is_preferred_payin_psp(group.trader)
            if is_human:
                spacing_skip = group_skip_reason_for_deal_spacing(group, amount)
                if spacing_skip:
                    skipped.append({
                        "trader": uname,
                        "group_id": str(group.id),
                        "skip": spacing_skip,
                    })
                    continue
                if fair_routing_enabled() and human_load:
                    remaining_humans = [
                        g for g in chosen_group[idx + 1:]
                        if not is_psp_trader(g.trader) and not is_preferred_payin_psp(g.trader)
                    ]
                    fair_skip = should_skip_fair_share(
                        group,
                        peer_groups=human_groups,
                        load_stats=human_load,
                        remaining_peers=remaining_humans,
                    )
                    if fair_skip:
                        skipped.append({
                            "trader": uname,
                            "group_id": str(group.id),
                            "skip": fair_skip,
                        })
                        continue
            if margin_ps is not None:
                margin_ok, margin_skip = margin_ok_for_group(
                    group,
                    amount=amount,
                    payment_system=margin_ps,
                    merchant=merchant,
                )
                if not margin_ok:
                    skipped.append({
                        "trader": uname,
                        "group_id": str(group.id),
                        "skip": margin_skip or "margin_low",
                    })
                    continue
            ps_name = (
                (group.payment_system.name if group.payment_system_id else "")
                or (margin_ps.name if margin_ps is not None else "")
                or ""
            ).upper()
            details_base = PaymentDetails.objects.filter(
                group=group,
                status=1,
                sberpay_enabled=False,
                sbp_enabled=False,
            )
            if ps_name == "PHONEKGS":
                available_details = details_base.exclude(phone__isnull=True).exclude(phone="")
            elif ps_name == "QRKGS":
                # Живые ELQR: qr_payload и/или телефон; PSP — карта-заглушка.
                available_details = details_base.filter(
                    Q(qr_payload__isnull=False) & ~Q(qr_payload="")
                    | Q(phone__isnull=False) & ~Q(phone="")
                    | Q(card_number__isnull=False) & ~Q(card_number="")
                )
            else:
                available_details = details_base.exclude(
                    card_number__isnull=True
                ).exclude(card_number="")
            # PSP / payplat / gipay: виртуальная карта не блокируется активной заявкой на ту же сумму.
            if is_human:
                available_details = available_details.exclude(id__in=active_details)
                if fair_routing_enabled():
                    available_details = exclude_overloaded_details(available_details)
                from payments.georgian_banks import exclude_georgian_human_details

                available_details, georgian_blocked = exclude_georgian_human_details(
                    available_details, merchant
                )
                if georgian_blocked and not available_details.exists():
                    skipped.append({
                        "trader": uname,
                        "group_id": str(group.id),
                        "skip": "georgian_bank",
                    })
                    continue
            if not available_details.exists():
                skipped.append({"trader": uname, "group_id": str(group.id), "skip": "no_free_card"})
                continue
            group_ps = group.payment_system
            group_rate = group_ps.get_rate() if group_ps else None
            if group_rate:
                usd_needed = amount / group_rate
                from payments.psp_payin import trader_covers_inflow

                if not trader_covers_inflow(group.trader, usd_needed):
                    skipped.append({"trader": uname, "group_id": str(group.id), "skip": "usd_for_group_ps"})
                    continue
            from trade.routing.fair_pick import pick_least_loaded_detail

            chosen_detail = pick_least_loaded_detail(available_details)
            try:
                record_in_sort_and_pick(
                    sorted_groups=chosen_group,
                    skipped=skipped,
                    chosen_detail=chosen_detail,
                )
            except Exception:
                import logging
                logging.getLogger("payin.trace").exception("routing pick snapshot failed")
            return chosen_detail

        try:
            record_in_sort_and_pick(sorted_groups=chosen_group, skipped=skipped, chosen_detail=None)
        except Exception:
            import logging
            logging.getLogger("payin.trace").exception("routing pick snapshot failed")
        return None

    def check_cluster(self, risk_cluster, payment_system, amount, active_orders, traffic_type, usd_amount):
        options = self.get_possible_options_in(risk_cluster, payment_system, amount, traffic_type, usd_amount)

        chosen_detail = self.get_details(
            options, active_orders, amount, payment_system=payment_system
        )

        if chosen_detail is not None:
            return chosen_detail

        return None

    def choose_detail_in(self, amount: Decimal, usd_amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, active_orders,
                         client_deposit_count, merchant=None):

        possible_options = self.get_possible_options_in(None, payment_system, amount, traffic_type, usd_amount)
        from payments.payin_remap import local_c2c_provider_groups, local_kzt_c2c_cascade_for

        if local_kzt_c2c_cascade_for(merchant, payment_system) is not None:
            possible_options = (
                possible_options | local_c2c_provider_groups(payment_system)
            ).distinct()

        chosen_detail = self.get_details(
            possible_options,
            active_orders,
            amount,
            merchant=merchant,
            payment_system=payment_system,
        )

        if chosen_detail is not None:
            return chosen_detail

        return None

    def get_possible_options_out(self, payment_system: PaymentSystem, traffic_type: TrafficType, amount, excluded):
        psp_users = psp_trader_usernames()
        psp_q = Q(trader__user__username__in=psp_users)
        possible_groups = PaymentDetailsGroup.objects.filter(
            status=1,
            payment_system__in=routing_payment_systems(payment_system),
            out_active=True,
            min_amount_out__lte=amount,
            max_amount_out__gte=amount,
            amount__gte=amount,
            trader__blocked=False,
            deposit_number_on=False,
        ).exclude(trader__user__username__in=DISABLED_PSP_TRADER_USERNAMES).filter(Q(allowed_traffic=traffic_type) | psp_q).distinct()

        possible_groups = possible_groups.exclude(trader__in=excluded)

        return possible_groups.order_by('current_out_volume')

    def choose_detail_out(self, amount: Decimal, payment_system: PaymentSystem, traffic_type: TrafficType, excluded=None, merchant=None):
        if excluded is None:
            excluded = list()

        possible_options = self.get_possible_options_out(payment_system, traffic_type, amount, excluded)
        if not possible_options.exists():
            return None

        groups = list(possible_options)
        from trade.routing.preferred import preferred_payout_trader_username

        preferred = preferred_payout_trader_username(merchant)
        if preferred:
            pref = [
                g for g in groups
                if g.trader and g.trader.user and g.trader.user.username == preferred
            ]
            if pref:
                groups = pref + [g for g in groups if g not in pref]

        for group in groups:
            # KGS phone/QR out details may have phone/qr_payload without card_number.
            base = PaymentDetails.objects.filter(
                group=group,
                status=1,
                sberpay_enabled=False,
                sbp_enabled=False,
            )
            chosen_detail = (
                base.exclude(card_number__isnull=True)
                .exclude(card_number="")
                .order_by("?")
                .first()
            )
            if chosen_detail is None:
                chosen_detail = (
                    base.exclude(phone__isnull=True).exclude(phone="").order_by("?").first()
                )
            if chosen_detail is None:
                chosen_detail = (
                    base.exclude(qr_payload__isnull=True)
                    .exclude(qr_payload="")
                    .order_by("?")
                    .first()
                )
            if chosen_detail is not None:
                return chosen_detail

        return None