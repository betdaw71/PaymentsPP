from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TrafficType,
)
from merchant.models import Merchant, MerchantSolution
from payments.psp_payin import sort_groups_for_routing
from trade.models import InOrder, InOrderStatus
from trade.routing.fair_pick import pick_least_loaded_detail
from trade.routing.human_fair import (
    exclude_overloaded_details,
    should_skip_fair_share,
    sort_human_groups,
)


def _g(username, pk, *, volume="0"):
    trader = SimpleNamespace(user=SimpleNamespace(username=username), team_id=1)
    return SimpleNamespace(
        pk=pk,
        id=pk,
        trader=trader,
        trader_id=pk,
        payment_system_id=1,
        current_volume=Decimal(volume),
    )


class SortHumanGroupsUnitTest(SimpleTestCase):
    def test_fewer_recent_issues_first_even_if_volume_higher(self):
        # Fail-loop: low volume after Expired should NOT win over fewer issues.
        a = _g("resdfe", 1, volume="100")
        b = _g("resdfe1", 2, volume="0")
        load = {
            "1": {"recent": 10, "open": 0},
            "2": {"recent": 60, "open": 0},
        }
        ordered = sort_human_groups([b, a], load_stats=load)
        self.assertEqual([g.trader.user.username for g in ordered], ["resdfe", "resdfe1"])

    def test_open_break_ties(self):
        a = _g("a", 1, volume="0")
        b = _g("b", 2, volume="0")
        load = {
            "1": {"recent": 5, "open": 3},
            "2": {"recent": 5, "open": 0},
        }
        ordered = sort_human_groups([a, b], load_stats=load)
        self.assertEqual(ordered[0].trader.user.username, "b")


class FairShareSkipUnitTest(SimpleTestCase):
    @override_settings(HUMAN_ROUTING_FAIR_SHARE_LEAD=3)
    def test_skips_when_ahead_and_peer_remains(self):
        g = _g("hot", 1)
        peer = _g("cold", 2)
        load = {"1": {"recent": 10}, "2": {"recent": 2}}
        self.assertEqual(
            should_skip_fair_share(
                g, peer_groups=[g, peer], load_stats=load, remaining_peers=[peer]
            ),
            "fair_share",
        )

    @override_settings(HUMAN_ROUTING_FAIR_SHARE_LEAD=3)
    def test_no_skip_when_last_human(self):
        g = _g("hot", 1)
        load = {"1": {"recent": 99}}
        self.assertIsNone(
            should_skip_fair_share(
                g, peer_groups=[g], load_stats=load, remaining_peers=[]
            )
        )


@override_settings(
    PSP_ROUTING_PRIORITY_MAP={"payplat1": 1, "gipay1": 2},
    PSP_ROUTING_SHARE_MAP={},
    HUMAN_ROUTING_FAIR=True,
)
@patch("payments.psp_payin._team_mdr_in_map", return_value={})
class SortGroupsHumanFairTest(SimpleTestCase):
    @patch(
        "trade.routing.human_fair.fetch_group_load_stats",
        return_value={
            "21": {"recent": 5, "open": 0},
            "20": {"recent": 40, "open": 0},
        },
    )
    def test_live_order_by_recent_not_volume(self, _load, _mdr):
        groups = [
            _g("payplat1", 1, volume="0"),
            _g("live_b", 20, volume="0"),
            _g("gipay1", 2, volume="0"),
            _g("live_a", 21, volume="999"),
        ]
        # live_a has fewer recent → first among humans despite high volume
        ordered = sort_groups_for_routing(groups)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["live_a", "live_b", "payplat1", "gipay1"],
        )


class FairPickAndCapTest(TestCase):
    def setUp(self):
        kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        traffic = TrafficType.objects.create(name="Standard")
        ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16"}},
            usdt_exchange_rate=Decimal("500"),
        )
        user = User.objects.create_user(username="fair_cap_trader", password="x")
        trader = Trader.objects.create(
            user=user,
            currency=kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("1000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.group = PaymentDetailsGroup.objects.create(
            trader=trader,
            currency=kzt,
            payment_system=ps,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="DROP",
        )
        self.busy = PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000001",
        )
        self.idle = PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4222222222222222",
            deposit_number="00000000000000000002",
        )
        merch_user = User.objects.create_user(username="fair_cap_merch", password="x")
        merchant = Merchant.objects.create(
            user=merch_user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.solution = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=ps,
            traffic=traffic,
            mdr_in=Decimal("6"),
        )
        self.st_new = InOrderStatus.objects.create(name="New")
        for amt in (Decimal("1000"), Decimal("2000")):
            InOrder.objects.create(
                amount=amt,
                usd_amount=Decimal("2"),
                payment_details=self.busy,
                status=self.st_new,
                solution=self.solution,
                arbitrage_comment="",
                pic="https://example.com/x",
                creation_date=timezone.now(),
            )

    def test_pick_prefers_idle(self):
        qs = PaymentDetails.objects.filter(group=self.group, status=1)
        self.assertEqual(pick_least_loaded_detail(qs).id, self.idle.id)

    @override_settings(HUMAN_ROUTING_MAX_OPEN_PER_DETAIL=2)
    def test_exclude_card_with_two_open(self):
        qs = PaymentDetails.objects.filter(group=self.group, status=1)
        filtered = exclude_overloaded_details(qs, max_open=2)
        ids = set(filtered.values_list("id", flat=True))
        self.assertNotIn(self.busy.id, ids)
        self.assertIn(self.idle.id, ids)
