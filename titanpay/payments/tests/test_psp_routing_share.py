from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.psp_payin import (
    apply_preferred_psp_order,
    get_share_window_hours,
    parse_routing_share_map,
    sort_groups_for_routing,
)


class _ScriptedRng:
    def __init__(self, values):
        self.values = list(values)

    def random(self):
        if not self.values:
            return 0.0
        return self.values.pop(0)


def _group(username, pk, *, volume="0", team_id=1, ps_id=1):
    trader = SimpleNamespace(
        team_id=team_id,
        user=SimpleNamespace(username=username),
    )
    return SimpleNamespace(
        pk=pk,
        id=pk,
        trader=trader,
        trader_id=pk,
        payment_system_id=ps_id,
        current_volume=Decimal(volume),
    )


class ParseRoutingShareMapTest(SimpleTestCase):
    def test_dict_drops_zero_and_negative(self):
        parsed = parse_routing_share_map({"payplat1": 70, "gipay1": 30, "bitzone1": 0, "x": -1})
        self.assertEqual(parsed["payplat1"], Decimal("70"))
        self.assertEqual(parsed["gipay1"], Decimal("30"))
        self.assertNotIn("bitzone1", parsed)
        self.assertNotIn("x", parsed)

    def test_json_string_and_casefold(self):
        parsed = parse_routing_share_map('{"PayPlat1": "70.5", "gipay1": 29.5}')
        self.assertEqual(parsed["payplat1"], Decimal("70.5"))
        self.assertEqual(parsed["gipay1"], Decimal("29.5"))

    def test_invalid_json_is_empty(self):
        self.assertEqual(parse_routing_share_map("{not json"), {})

    @override_settings(PSP_ROUTING_SHARE_WINDOW_HOURS="48")
    def test_window_hours_clamped(self):
        self.assertEqual(get_share_window_hours(), 48)

    @override_settings(PSP_ROUTING_SHARE_WINDOW_HOURS="0")
    def test_window_hours_minimum(self):
        self.assertEqual(get_share_window_hours(), 1)


@override_settings(
    PSP_ROUTING_PRIORITY_MAP={"payplat1": 1, "gipay1": 2, "bitzone1": 3},
    PSP_ROUTING_SHARE_MAP={},
)
@patch("payments.psp_payin._team_mdr_in_map", return_value={})
class SortGroupsForRoutingShareTest(SimpleTestCase):
    def test_empty_share_map_uses_cascade_priority(self, _mdr):
        groups = [
            _group("bitzone1", 3),
            _group("gipay1", 2),
            _group("payplat1", 1),
        ]
        ordered = sort_groups_for_routing(groups, share_volumes={})
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["payplat1", "gipay1", "bitzone1"],
        )

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 70, "gipay1": 30})
    def test_share_roll_low_picks_payplat_first(self, _mdr):
        groups = [
            _group("payplat1", 1),
            _group("gipay1", 2),
            _group("bitzone1", 3),
        ]
        rng = _ScriptedRng([0.0, 0.0])
        ordered = sort_groups_for_routing(groups, rng=rng)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["payplat1", "gipay1", "bitzone1"],
        )

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 70, "gipay1": 30})
    def test_share_roll_high_picks_gipay_first_not_catchup(self, _mdr):
        groups = [
            _group("payplat1", 1),
            _group("gipay1", 2),
            _group("bitzone1", 3),
        ]
        rng = _ScriptedRng([0.99, 0.0])
        ordered = sort_groups_for_routing(
            groups,
            share_volumes={"payplat1": 90, "gipay1": 10},
            rng=rng,
        )
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["gipay1", "payplat1", "bitzone1"],
        )

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 70, "gipay1": 30})
    def test_history_volume_does_not_force_gipay(self, _mdr):
        groups = [_group("payplat1", 1), _group("gipay1", 2), _group("bitzone1", 3)]
        rng = _ScriptedRng([0.0, 0.0])
        ordered = sort_groups_for_routing(
            groups,
            share_volumes={"payplat1": 10_000_000, "gipay1": 1},
            rng=rng,
        )
        self.assertEqual(ordered[0].trader.user.username, "payplat1")

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 70, "gipay1": 30})
    def test_missing_provider_share_is_renormalized(self, _mdr):
        groups = [_group("payplat1", 1), _group("bitzone1", 3)]
        ordered = sort_groups_for_routing(groups, rng=_ScriptedRng([0.0]))
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["payplat1", "bitzone1"],
        )

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 50, "gipay1": 50})
    def test_unweighted_psp_stays_after_weighted(self, _mdr):
        groups = [_group("bitzone1", 3), _group("gipay1", 2), _group("payplat1", 1)]
        rng = _ScriptedRng([0.99, 0.0])
        ordered = sort_groups_for_routing(groups, rng=rng)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["payplat1", "gipay1", "bitzone1"],
        )


@override_settings(
    PAYPLAT_TRADER_USERNAME="payplat1",
    GIPAY_TRADER_USERNAME="gipay1",
)
class ApplyPreferredPspOrderTest(SimpleTestCase):
    @override_settings(PSP_ROUTING_SHARE_MAP={})
    def test_without_shares_payplat_is_forced_first(self):
        groups = [_group("gipay1", 2), _group("payplat1", 1), _group("bitzone1", 3)]
        ordered = apply_preferred_psp_order(groups)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["payplat1", "gipay1", "bitzone1"],
        )

    @override_settings(PSP_ROUTING_SHARE_MAP={"payplat1": 70, "gipay1": 30})
    def test_with_shares_does_not_reorder(self):
        groups = [_group("gipay1", 2), _group("payplat1", 1), _group("bitzone1", 3)]
        ordered = apply_preferred_psp_order(groups)
        self.assertEqual(
            [g.trader.user.username for g in ordered],
            ["gipay1", "payplat1", "bitzone1"],
        )
