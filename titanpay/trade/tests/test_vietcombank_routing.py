from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)
from basics.utils import xe_kzt_markup_for_ps
from payments.utils import translate_bank
from trade.routing.base import route
from trade.routing.ps_names import routing_payment_systems
from trade.utils import choose_trader_in


@override_settings(KZT_C2C_BANK_PS_NAMES="Vietcombank")
class VietcombankC2cRoutingTest(TestCase):
    def setUp(self):
        self.kzt = Currency.objects.create(name="Tenge", symbol="KZT")
        Language.objects.create(name="Russian")
        self.traffic = TrafficType.objects.create(name="Standard")
        fields = {"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}}
        self.c2ckzt = PaymentSystem.objects.create(
            name="C2CKZT",
            currency=self.kzt,
            required_fields=fields,
            usdt_exchange_rate=Decimal("500"),
        )
        self.vcb = PaymentSystem.objects.create(
            name="Vietcombank",
            currency=self.kzt,
            required_fields=fields,
            usdt_exchange_rate=Decimal("480"),
        )
        team = TraderTeam.objects.create(name="vn-team")
        TraderTeamRates.objects.create(team=team, payment_system=self.c2ckzt, mdr_in=Decimal("5"))
        TraderTeamRates.objects.create(team=team, payment_system=self.vcb, mdr_in=Decimal("5"))
        user = User.objects.create_user(username="vn_trader", password="x")
        self.trader = Trader.objects.create(
            user=user,
            team=team,
            currency=self.kzt,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("100000")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.group = PaymentDetailsGroup.objects.create(
            trader=self.trader,
            currency=self.kzt,
            payment_system=self.vcb,
            status=1,
            in_active=True,
            work_type="by_card",
            owner="NGUYEN VAN A",
            limit_per_period=Decimal("1000000"),
        )
        self.group.allowed_traffic.add(self.traffic)
        self.card = PaymentDetails.objects.create(
            group=self.group,
            status=1,
            card_number="4111111111111111",
            deposit_number="00000000000000000001",
        )

    def test_c2ckzt_request_includes_vietcombank_ps(self):
        names = {ps.name for ps in routing_payment_systems(self.c2ckzt)}
        self.assertIn("C2CKZT", names)
        self.assertIn("Vietcombank", names)

    def test_route_c2ckzt_picks_vietcombank_card(self):
        router = route(self.c2ckzt)
        amount = Decimal("10000")
        usd = amount / self.c2ckzt.get_rate()
        options = router.get_possible_options_in(None, self.c2ckzt, amount, self.traffic, usd)
        self.assertTrue(options.filter(id=self.group.id).exists())
        detail, usd_amount, ps, ok = choose_trader_in(
            amount, self.c2ckzt, self.traffic, [], 0
        )
        self.assertTrue(ok)
        self.assertEqual(detail.id, self.card.id)
        self.assertEqual(ps.id, self.c2ckzt.id)
        self.assertEqual(usd_amount, amount / self.vcb.get_rate())

    def test_merchant_bank_field_is_vietcombank(self):
        from payments.serializers import PaymentDetailsCardSerializer

        data = PaymentDetailsCardSerializer(self.card).data
        self.assertEqual(data["bank"], "Vietcombank")
        self.assertEqual(data["card_number"], "4111111111111111")

    def test_translate_bank(self):
        self.assertEqual(translate_bank("Vietcombank"), "Vietcombank")
        self.assertIsNone(translate_bank("C2CKZT"))

    def test_min_max_amount_in_excludes_local_group(self):
        self.group.min_amount_in = Decimal("1000")
        self.group.max_amount_in = Decimal("5000")
        self.group.save(update_fields=["min_amount_in", "max_amount_in"])
        router = route(self.c2ckzt)
        usd = Decimal("10000") / self.c2ckzt.get_rate()
        too_big = router.get_possible_options_in(
            None, self.c2ckzt, Decimal("10000"), self.traffic, usd
        )
        self.assertFalse(too_big.filter(id=self.group.id).exists())
        ok = router.get_possible_options_in(
            None, self.c2ckzt, Decimal("4000"), self.traffic, Decimal("4000") / self.c2ckzt.get_rate()
        )
        self.assertTrue(ok.filter(id=self.group.id).exists())


@override_settings(XE_KZT_MARKUP="", XE_KZT_MARKUP_BY_PS='{"Vietcombank":"1.04"}')
class XeKztMarkupTest(SimpleTestCase):
    def test_vietcombank_default_is_plus_4(self):
        self.assertEqual(xe_kzt_markup_for_ps("Vietcombank"), Decimal("1.04"))

    def test_other_kzt_ps_default_is_plus_5(self):
        self.assertEqual(xe_kzt_markup_for_ps("C2CKZT"), Decimal("1.05"))

    @override_settings(XE_KZT_MARKUP="1.06", XE_KZT_MARKUP_BY_PS='{"Vietcombank":"1.04"}')
    def test_per_ps_overrides_global(self):
        self.assertEqual(xe_kzt_markup_for_ps("Vietcombank"), Decimal("1.04"))
        self.assertEqual(xe_kzt_markup_for_ps("C2CKZT"), Decimal("1.06"))
