from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from payments.deal_margin import DealMarginQuote, quote_deal_margin, trader_margin_ok_for_payin
from payments.dual_fx import DualFxQuote


def _ps(rate="525", name="C2CKZT", symbol="KZT"):
    return SimpleNamespace(
        name=name,
        get_rate=lambda: Decimal(rate),
        currency=SimpleNamespace(symbol=symbol),
    )


def _trader(username="patriot1", mdr=Decimal("6.5"), tl_pct=Decimal("0.5")):
    team = SimpleNamespace(id=1, teamlead_percentage=tl_pct)
    return SimpleNamespace(
        team_id=1,
        team=team,
        user=SimpleNamespace(username=username),
    )


def _merchant(username="aggrepay", agent_pct=Decimal("0.2")):
    agent = SimpleNamespace(commission_percent=agent_pct)
    return SimpleNamespace(user=SimpleNamespace(username=username), agent=agent)


def _solution(mdr=Decimal("6"), merchant=None, ps=None):
    return SimpleNamespace(
        mdr_in=mdr,
        merchant=merchant or _merchant(),
        payment_system=ps or _ps(),
    )


@override_settings(DEAL_MARGIN_FILTER_ENABLED="1", DEAL_MARGIN_MIN_PCT="0.2")
class DealMarginQuoteTest(SimpleTestCase):
    @patch("payments.deal_margin._trader_mdr_in", return_value=Decimal("6.5"))
    @patch("payments.dual_fx.quote_dual_fx")
    def test_profitable_ok(self, mock_fx, _mdr):
        mock_fx.return_value = DualFxQuote(
            merchant_rate=Decimal("525"),
            psp_rate=Decimal("520"),
            merchant_usd=Decimal("100.00"),
            psp_usd=Decimal("100.96"),
            merchant_markup=Decimal("1.05"),
            psp_markup=Decimal("1.04"),
        )
        q = quote_deal_margin(
            amount=Decimal("52500"),
            payment_system=_ps(),
            trader=_trader(tl_pct=Decimal("0.5")),
            merchant=_merchant(agent_pct=Decimal("0.2")),
            solution=_solution(mdr=Decimal("6")),
        )
        # m_fee=6, t_fee=6.56, agent=0.20, fx=0.96 → pnl=6+0.96-6.56-0.20=0.20 → 0.2%
        self.assertEqual(q.merchant_fee, Decimal("6.00"))
        self.assertEqual(q.trader_fee, Decimal("6.56"))
        self.assertEqual(q.agent_fee, Decimal("0.20"))
        self.assertEqual(q.teamlead_share, Decimal("0.50"))  # 0.5% of merchant_usd 100
        self.assertEqual(q.fx_spread, Decimal("0.96"))
        self.assertEqual(q.platform_pnl, Decimal("0.20"))
        self.assertTrue(q.ok)

    @patch("payments.deal_margin._trader_mdr_in", return_value=Decimal("7.0"))
    @patch("payments.dual_fx.quote_dual_fx")
    def test_below_min_rejected(self, mock_fx, _mdr):
        mock_fx.return_value = DualFxQuote(
            merchant_rate=Decimal("525"),
            psp_rate=Decimal("525"),
            merchant_usd=Decimal("100.00"),
            psp_usd=Decimal("100.00"),
            merchant_markup=Decimal("1.05"),
            psp_markup=Decimal("1.05"),
        )
        # m_fee=6, t_fee=7, agent=0.2, fx=0 → pnl=-1.2 → -1.2%
        ok, q = trader_margin_ok_for_payin(
            amount=Decimal("52500"),
            payment_system=_ps(),
            trader=_trader(mdr=Decimal("7")),
            merchant=_merchant(),
            solution=_solution(mdr=Decimal("6")),
        )
        self.assertFalse(ok)
        self.assertFalse(q.ok)
        self.assertIn("margin_low", q.as_skip_reason())

    @override_settings(DEAL_MARGIN_FILTER_ENABLED="0")
    @patch("payments.deal_margin.quote_deal_margin")
    def test_filter_disabled_always_ok(self, mock_q):
        mock_q.return_value = DealMarginQuote(
            amount=Decimal("1"),
            merchant_usd=Decimal("1"),
            psp_usd=Decimal("1"),
            merchant_rate=Decimal("1"),
            psp_rate=Decimal("1"),
            merchant_mdr=Decimal("1"),
            trader_mdr=Decimal("9"),
            merchant_fee=Decimal("0"),
            trader_fee=Decimal("1"),
            agent_fee=Decimal("0"),
            teamlead_pct=Decimal("0"),
            teamlead_share=Decimal("0"),
            fx_spread=Decimal("0"),
            platform_pnl=Decimal("-1"),
            platform_pct=Decimal("-100"),
            min_pct=Decimal("0.2"),
            ok=False,
        )
        ok, _ = trader_margin_ok_for_payin(
            amount=Decimal("1"),
            payment_system=_ps(),
            trader=_trader(),
            merchant=_merchant(),
            solution=_solution(),
        )
        self.assertTrue(ok)
        mock_q.assert_not_called()
