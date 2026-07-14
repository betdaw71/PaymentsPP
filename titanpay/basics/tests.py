import json
import os

from django.test import TestCase, Client
from django.contrib.auth.models import User
from basics.models import Trader, TraderTeam, Currency, Language, PaymentSystem, TrafficType, PaymentDetailsGroup, Balance
from trade.models import TransactionType, Address
from titanpay.settings import DEBUG, SBER_NAME
from basics.utils import get_usdt_rate

# from usermanagement.models import SupportMember
# from merchant.models import Merchant
# m_user = User.objects.create_user(username='test_merchant', password='Proverka1', email="test_merchant@test.com", first_name='Merch', last_name='Ant')
# hs_user = User.objects.create_user(username='head_support_1', password='Proverka1', email="head_support_1@test.com", first_name='Head', last_name='Sup')
# s_user = User.objects.create_user(username='support', password='Proverka1', email="head_support_1@test.com", first_name='Head', last_name='Sup')
#
# a1 = Balance.objects.create(type=0)
# f1 = Balance.objects.create(type=1)
#
# m = Merchant.objects.create(user=m_user, balance=a1, frozen_balance=f1, language=test_language)
#
#
# hs = SupportMember.objects.create(language=test_language, user=hs_user, is_head=True)
# hs.controlled_teams.add(test_team)
# hs.controlled_merchants.add(m)
#
# s = SupportMember.objects.create(language=test_language, user=s_user, is_head=True)
# s.controlled_teams.add(test_team)
# s.controlled_merchants.add(m)

class TestNotBossTrader(TestCase):
    def setUp(self):
        self.client = Client(headers={"GATE": os.getenv("PLATFORM_GATE")})
        self.user = User.objects.create_user(username='testuser', password='testpass', email="test@test.com", first_name='Test', last_name='Test')
        self.client.login(username='testuser', password='testpass')

        test_currency = Currency.objects.create(name="Ruble", symbol="RUB")
        test_language = Language.objects.create(name="Russian")

        user_boss = User.objects.create_user(username='testuserboss', password='testpassboss', email="testboss@test.com",
                                             first_name='Testboss', last_name='Testboss')
        user_not_boss = User.objects.create_user(username='testtrader', password='testtraderpass', email="testtrader@test.com",
                                             first_name='Testtrader', last_name='Testtrader')

        test_team = TraderTeam.objects.create(name="TestTeam", rate_in=4, rate_out=1)

        ba1 = Balance.objects.create(type=0)
        bf1 = Balance.objects.create(type=1)
        ba2 = Balance.objects.create(type=0)
        bf2 = Balance.objects.create(type=1)
        ba3 = Balance.objects.create(type=0)
        bf3 = Balance.objects.create(type=1)

        self.trader_boss = Trader.objects.create(user=user_boss, language=test_language, telegram="durov", phone="+7952812", boss=None, is_boss=True, team=test_team, currency=test_currency, balance_usdt=ba1, frozen_balance_usdt=bf1)

        self.trader = Trader.objects.create(user=self.user, language=test_language, phone="+7952813", telegram="t", boss=self.trader_boss, is_boss=False, team=test_team, currency=test_currency, balance_usdt=ba2, frozen_balance_usdt=bf2)
        self.trader2 = Trader.objects.create(user=user_not_boss, language=test_language, telegram="test2", phone="+7952814", boss=self.trader_boss, is_boss=False, team=test_team, currency=test_currency, balance_usdt=ba3, frozen_balance_usdt=bf3)

        self.gamble = TrafficType.objects.create(name="Gamble")
        details_description = {"card number": {"regex": "^\d{16}$", "pattern": "XXXXXXXXXXXXXXXX"}}
        self.sberbank = PaymentSystem.objects.create(name=SBER_NAME, currency=test_currency, required_fields=details_description)

        Address.objects.create(balance=self.trader_boss.balance_usdt, address_public="0x02")

    def test_transfer_targets(self):
        response = self.client.get('/api/v1/base/transfer-targets/')
        print(response.content)
        self.assertEqual(response.status_code, 200)

    def test_get_trader(self):
        response = self.client.get(f'/api/v1/base/trader/{self.trader.id}/')
        print(response.content)
        self.assertEqual(response.status_code, 200)

    def test_trading_team_trader(self):
        response = self.client.get('/api/v1/base/trading-team/trader/')
        print(response.content)
        self.assertEqual(response.status_code, 200)

    def test_trading_team_support(self):
        response = self.client.get('/api/v1/base/trading-team/support/')
        print(response.content)
        self.assertEqual(response.status_code, 403)

    def test_get_payment_system(self):
        response = self.client.get('/api/v1/base/payment-system/')
        print(response.content)
        self.assertEqual(response.status_code, 200)

    def test_get_trading_teams(self):
        response = self.client.get('/api/v1/base/trader-team/')
        print(response.content)
        self.assertEqual(response.status_code, 200*int(DEBUG)+403*(1-int(DEBUG)))

    def test_create_pd_group(self):
        data = {
            'owner': 'Иван Иванов',
            'currency': str(Currency.objects.get(name="Ruble").id),
            'payment_system': str(self.sberbank.id),
            'min_amount_out': 10000,
            'max_amount_out': 200000,
            'in_active': True,
            'out_active': True,
            'allowed_traffic': [str(self.gamble.id)],
        }

        request = self.client.post(f'/api/v1/base/details/', data, format='json')
        print(json.loads(request.content))

        pd = PaymentDetailsGroup.objects.all().first()

        request = self.client.get(f'/api/v1/base/details/{str(pd.id)}/')
        print(json.loads(request.content))

        data_1 = {
            'sberpay_enabled': False,
            'card_number': "0000111122223333",
            'phone': "+79031112233",
            'deposit_number': "0001",
            'group': str(pd.id)
        }

        request = self.client.post(f'/api/v1/base/details/{str(pd.id)}/add-details/', data_1, format='json')

        request = self.client.get(f'/api/v1/base/details/{str(pd.id)}/')
        # request = self.client.get(f'/api/v1/base/details/')
        iid = json.loads(request.content)['details'][0]['id']

        data_2 = {
            'details': iid,
            'status': 2,
        }

        request = self.client.post(f'/api/v1/base/details/{str(pd.id)}/change-details-status/', data_2, format='json')
        print(request.content)

    def test_get_pdgroup_cr_data(self):
        response = self.client.get('/api/v1/base/pdgroup-creation-data/')
        print(response.content)
        self.assertEqual(response.status_code, 200)

    def test_get_pd_cr_data(self):
        response = self.client.get('/api/v1/base/pd-creation-data/')
        print(response.content)
        self.assertEqual(response.status_code, 200)