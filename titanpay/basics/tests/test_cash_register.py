from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from basics.cash_register import (
    fx_spread,
    kzt_to_usd,
    merchant_usdt_net,
    payin_pnl,
    payout_pnl,
    psp_held_usdt,
    snapshot,
)
from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentSystem,
    PlatformExpense,
    TeamLead,
    Trader,
    TraderTeam,
    TrafficType,
)
from merchant.models import Agent, Merchant, MerchantSolution
from trade.models import InOrder, InOrderStatus, OutOrder, OutOrderStatus


class CashRegisterMathTest(SimpleTestCase):
    def test_fx_spread_uses_psp_usd(self):
        self.assertEqual(fx_spread("100.00", "102.00"), Decimal("2.00"))

    def test_missing_psp_usd_is_zero_spread(self):
        self.assertEqual(fx_spread("100.00", "0"), Decimal("0.00"))

    def test_payin_pnl(self):
        # MDR 7 + FX 2 - PSP 5.7 - agent 0.20
        self.assertEqual(
            payin_pnl(
                merchant_fee="7.00",
                trader_fee="5.70",
                agent_fee="0.20",
                usd_amount="100.00",
                psp_usd_amount="102.00",
            ),
            Decimal("3.10"),
        )

    def test_payout_pnl(self):
        self.assertEqual(payout_pnl(merchant_fee="8.00", trader_fee="6.50"), Decimal("1.50"))

    def test_mostbet_net_is_available_minus_rolling(self):
        self.assertEqual(merchant_usdt_net("6320.71", "0.01", "5000.00"), Decimal("1320.72"))

    def test_kzt_to_usd_uses_c2ckzt_rate(self):
        self.assertEqual(kzt_to_usd("105000", rate="525"), Decimal("200.00"))

    def test_psp_negative_counts_as_held(self):
        self.assertEqual(psp_held_usdt("-200.00"), Decimal("200.00"))
        self.assertEqual(psp_held_usdt("985220.69"), Decimal("985220.69"))


@override_settings(PAYPLAT_TRADER_USERNAME="payplat1")
@patch("basics.cash_register.fetch_platform_wallet_usdt", return_value=(Decimal("0"), "TEPKpVsAUyrkLx38ueFzSQP1HXGX8XK1Tt"))
class CashRegisterSnapshotTest(TestCase):
    def setUp(self):
        Language.objects.create(name="Russian")
        kzt = Currency.objects.create(name="Tenge CR", symbol="KZTCR")
        self.ps = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=kzt,
            required_fields={},
            usdt_exchange_rate=Decimal("500"),
        )
        traffic = TrafficType.objects.create(name="Standard CR")
        team = TraderTeam.objects.create(name="psp-cr")
        psp_user = User.objects.create_user(username="payplat1", password="x")
        Trader.objects.create(
            user=psp_user,
            team=team,
            currency=kzt,
            credit_limit=Decimal("50000"),
            working_deposit=Decimal("12000"),
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("-200.00")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        own_user = User.objects.create_user(username="trader_own", password="x")
        Trader.objects.create(
            user=own_user,
            team=team,
            currency=kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("50.00")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        merchant_user = User.objects.create_user(username="pandapay", password="x")
        self.merchant = Merchant.objects.create(
            user=merchant_user,
            balance=Balance.objects.create(type=0, amount=Decimal("80.00")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("20.00")),
            rolling_reserve=Decimal("2217.00"),
        )
        self.solution = MerchantSolution.objects.create(
            merchant=self.merchant,
            payment_system=self.ps,
            traffic=traffic,
            mdr_in=Decimal("7.00"),
        )
        agent_user = User.objects.create_user(username="L_payments", password="x")
        Agent.objects.create(
            user=agent_user,
            balance=Balance.objects.create(type=0, amount=Decimal("5.00")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        tl_user = User.objects.create_user(username="tl1", password="x")
        TeamLead.objects.create(
            user=tl_user,
            balance=Balance.objects.create(type=0, amount=Decimal("3.00")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        completed_in = InOrderStatus.objects.create(name="Completed")
        completed_out = OutOrderStatus.objects.create(name="Completed")
        now = timezone.now()
        InOrder.objects.create(
            status=completed_in,
            amount=Decimal("50000.00"),
            usd_amount=Decimal("100.00"),
            psp_usd_amount=Decimal("102.00"),
            solution=self.solution,
            merchant_fee=Decimal("7.00"),
            trader_fee=Decimal("5.70"),
            agent_fee=Decimal("0.20"),
            completion_date=now,
            arbitrage_comment="",
            pic="https://example.com/in",
        )
        OutOrder.objects.create(
            status=completed_out,
            amount=Decimal("1000.00"),
            usd_amount=Decimal("2.00"),
            solution=self.solution,
            merchant_fee=Decimal("0.16"),
            trader_fee=Decimal("0.10"),
            completion_date=now,
            pic="https://example.com/out",
        )
        PlatformExpense.objects.create(amount=Decimal("1.00"), comment="hosting", source="telegram")

    def test_cash_is_assets_minus_liabilities(self, _wallet):
        data = snapshot()
        # PSP -200 в ЛК = 200 на сайте провайдера
        # assets: 200 + trader 50 = 250
        # liabilities: merchant 100 + agent 5 + teamlead 3 = 108
        # cash = 142
        self.assertEqual(data["assets"]["psp_total"], "200.00")
        self.assertEqual(data["assets"]["traders_total"], "50.00")
        self.assertEqual(data["liabilities"]["merchants_total"], "100.00")
        self.assertEqual(data["liabilities"]["agents_total"], "5.00")
        self.assertEqual(data["liabilities"]["teamleads_total"], "3.00")
        self.assertEqual(data["cash"], "142.00")
        self.assertEqual(data["memo"]["rolling_reserve"], "2217.00")
        self.assertEqual(data["memo"]["working_deposit"], "12000.00")

    def test_mostbet_liability_nets_rolling(self, _wallet):
        user = User.objects.create_user(username="mostbet", password="x")
        Merchant.objects.create(
            user=user,
            balance=Balance.objects.create(type=0, amount=Decimal("6320.71")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0.01")),
            rolling_reserve=Decimal("5000.00"),
        )
        data = snapshot()
        row = next(item for item in data["liabilities"]["merchants"] if item["username"] == "mostbet")
        self.assertEqual(row["net"], "1320.72")
        self.assertEqual(row["rolling_reserve"], "5000.00")
        # previous merchants_total 100 + mostbet 1320.72
        self.assertEqual(data["liabilities"]["merchants_total"], "1420.72")

    @override_settings(MELBET_KZT_USERNAMES="melbet,melbet_test", PAYPLAT_TRADER_USERNAME="payplat1")
    def test_melbet_kzt_prepaid_is_asset(self, _wallet):
        user = User.objects.create_user(username="melbet", password="x")
        Merchant.objects.create(
            user=user,
            balance=Balance.objects.create(type=0, amount=Decimal("0")),
            frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
            balance_kzt=Balance.objects.create(type=0, amount=Decimal("105000.00")),
            frozen_balance_kzt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        data = snapshot()
        self.assertEqual(data["kzt_usdt_rate"], "500.00")
        row = next(item for item in data["assets"]["receivables"] if item["username"] == "melbet")
        self.assertEqual(row["kzt"], "105000.00")
        self.assertEqual(row["available"], "210.00")
        self.assertEqual(data["assets"]["receivables_total"], "210.00")
        names = [item["username"] for item in data["liabilities"]["merchants"]]
        self.assertIn("melbet", names)
        self.assertEqual(data["liabilities"]["merchants_total"], "100.00")

    def test_day_pnl_includes_fx_and_expense(self, _wallet):
        data = snapshot()
        day = data["pnl"]["day"]
        # 7 + 2 + 0.16 - 5.70 - 0.10 - 0.20 - 1.00 = 2.16
        self.assertEqual(day["orders_in"], 1)
        self.assertEqual(day["orders_out"], 1)
        self.assertEqual(day["payin_mdr"], "7.00")
        self.assertEqual(day["payin_fx"], "2.00")
        self.assertEqual(day["payout_mdr"], "0.16")
        self.assertEqual(day["trader_fee"], "5.80")
        self.assertEqual(day["agent_fee"], "0.20")
        self.assertEqual(day["expenses"], "1.00")
        self.assertEqual(day["net"], "2.16")
