import hashlib
import json
import os
from decimal import Decimal
from rest_framework.authtoken.models import Token
from django.test import TestCase, Client
from django.contrib.auth.models import User
from basics.models import Trader, TraderTeam, Currency, Language, PaymentSystem, TrafficType, PaymentDetailsGroup, \
    Balance, PaymentDetails
from payments.models import PayOutStatus, PayInStatus, PayIn, PayOut
from payments.utils import UUIDEncoder
from sms.models import SMS, TraderDevice
from trade.models import TransactionType, Address, InOrder, InOrderStatus, OutOrderStatus, OutOrder, Transaction
from titanpay.settings import DEBUG, SBER_NAME, SBP_NAME, SBERPAY_NAME
from basics.utils import get_usdt_rate

from usermanagement.models import SupportMember
from merchant.models import Merchant, MerchantSolution


class TestHeadSupCreations(TestCase):
    def setUp(self):
        self.client = Client(headers={"GATE": os.getenv("PLATFORM_GATE")})

        self.currency = Currency.objects.create(name="Ruble", symbol="RUB")
        Language.objects.create(name="English")
        self.language = Language.objects.create(name="Russian")

        self.gamble = TrafficType.objects.create(name="Gamble")
        details_description = {"card_number": {"regex": "^\d{16}$", "pattern": "XXXXXXXXXXXXXXXX"}}
        details_description_sbp = {"phone": {"regex": "^\+79\d{9}$", "pattern": "+79XXXXXXXXX"}, "bank": {"regex": "^.+$", "pattern": "Bank"}}
        details_description_sberpay = {"phone": {"regex": "^\+79\d{9}$", "pattern": "+79XXXXXXXXX"}}
        self.sberbank = PaymentSystem.objects.create(name=SBER_NAME, currency=self.currency, required_fields=details_description, sbp_compatible=True)
        self.sbp = PaymentSystem.objects.create(name=SBP_NAME, currency=self.currency, required_fields=details_description_sbp, sbp_compatible=False)
        self.sberpay = PaymentSystem.objects.create(name=SBERPAY_NAME, currency=self.currency, required_fields=details_description_sberpay, sbp_compatible=False)

        hs_user = User.objects.create_user(username='head_support_1', password='Proverka1',
                                           email="head_support_1@test.com", first_name='Head', last_name='Sup')
        s_user = User.objects.create_user(username='support', password='Proverka1', email="head_support_1@test.com",
                                          first_name='Head', last_name='Sup')

        hs = SupportMember.objects.create(language=self.language, user=hs_user, is_head=True)

        s = SupportMember.objects.create(language=self.language, user=s_user, is_head=True)

        self.client.login(username='head_support_1', password='Proverka1')


    def test_create_team(self):
        url = '/api/v1/base/trader-team/'
        data = {
            "name": "Team1",
            "in_rate": 4,
            "out_rate": 1
        }

        request = self.client.post(url, data, format='json')
        # print(json.loads(request.content))

    def test_create_trader(self):
        url = '/api/v1/base/trader-team/'
        data = {
            "name": "Team1",
            "in_rate": 4,
            "out_rate": 1
        }

        request = self.client.post(url, data, format='json')

        url = '/api/v1/auth/register-trader/'
        data = {
            "username": "username",
            "first_name": "first_name",
            "password": "password11!Q",
            "password2": "password11!Q",
            "email": "email@mail.ru",

            "team": str(TraderTeam.objects.all().first().id),
            "currency": str(self.currency.id),
            "address": "0x00400440"
        }

        request = self.client.post(url, data, format='json')

    def test_create_merchant(self):
        url = '/api/v1/auth/register-merchant/'
        data = {
            "username": "username",
            "first_name": "first_name",
            "password": "password11!Q",
            "password2": "password11!Q",
            "email": "email@mail.ru",
            "address": "0x00400440"
        }
        request = self.client.post(url, data, format='json')


class TestHeadSupOrders(TestCase):
    def setUp(self):
        self.client = Client(headers={"GATE": os.getenv("PLATFORM_GATE")})

        self.currency = Currency.objects.create(name="Ruble", symbol="RUB")
        Language.objects.create(name="English")
        self.language = Language.objects.create(name="Russian")

        self.gamble = TrafficType.objects.create(name="Gamble")
        details_description = {"card_number": {"regex": "^\d{16}$", "pattern": "XXXXXXXXXXXXXXXX"}}
        details_description_sbp = {"phone": {"regex": "^\+79\d{9}$", "pattern": "+79XXXXXXXXX"},
                                   "bank": {"regex": "^.+$", "pattern": "Bank"}}
        details_description_sberpay = {"phone": {"regex": "^\+79\d{9}$", "pattern": "+79XXXXXXXXX"}}
        self.sberbank = PaymentSystem.objects.create(name=SBER_NAME, currency=self.currency,
                                                     required_fields=details_description, sbp_compatible=True)
        self.sbp = PaymentSystem.objects.create(name=SBP_NAME, currency=self.currency,
                                                required_fields=details_description_sbp, sbp_compatible=False)
        self.sberpay = PaymentSystem.objects.create(name=SBERPAY_NAME, currency=self.currency,
                                                    required_fields=details_description_sberpay, sbp_compatible=False)

        hs_user = User.objects.create_user(username='head_support_1', password='Proverka1',
                                           email="head_support_1@test.com", first_name='Head', last_name='Sup')
        s_user = User.objects.create_user(username='support', password='Proverka1', email="head_support_1@test.com",
                                          first_name='Head', last_name='Sup')

        hs = SupportMember.objects.create(language=self.language, user=hs_user, is_head=True)

        s = SupportMember.objects.create(language=self.language, user=s_user, is_head=True)

        self.client.login(username='head_support_1', password='Proverka1')

    def create_trader(self):
        url = '/api/v1/base/trader-team/'
        data = {
            "name": "Team1",
            "rate_in": 4,
            "rate_out": 1
        }

        request = self.client.post(url, data, format='json')

        url = '/api/v1/auth/register-trader/'
        data = {
            "username": "trader",
            "first_name": "traderfirst_name",
            "password": "password11!Q",
            "password2": "password11!Q",
            "email": "trader@mail.ru",

            "team": str(TraderTeam.objects.all().first().id),
            "currency": str(self.currency.id),
            "address": "0x00400440"
        }

        request = self.client.post(url, data, format='json')

    def create_merchant(self):
        url = '/api/v1/auth/register-merchant/'
        data = {
            "username": "merchant",
            "first_name": "merchantfirst_name",
            "password": "password11!Q",
            "password2": "password11!Q",
            "email": "merchant@mail.ru",
            "address": "0x00400440"
        }
        request = self.client.post(url, data, format='json')

    def test_create_solution(self):
        self.create_trader()
        self.create_merchant()

        merchant = Merchant.objects.all().first()

        url = '/api/v1/merchant/merchant-fees/'
        data = {
            "payment_system": str(self.sberbank.id),
            "merchant": str(merchant.id),
            "mdr_in": 6,
            "mdr_out": 3,
            "traffic": str(self.gamble.id),
            "ftd": False
        }
        request = self.client.post(url, data, format='json')

    def create_statuses(self):
        InOrderStatus.objects.create(name="New")
        TransactionType.objects.create(name="Freeze")

    def create_pay_in_statuses(self):
        for name in ["New", "In Progress", "Success", "Failed", "Declined"]:
            if not PayInStatus.objects.filter(name=name).exists():
                PayInStatus.objects.create(name=name)

    def create_pay_out_statuses(self):
        for name in ["New", "In Progress", "Success", "Failed", "Declined"]:
            if not PayOutStatus.objects.filter(name=name).exists():
                PayOutStatus.objects.create(name=name)

    def create_inorder_statuses(self):
        for name in ["New", "Money sent by user", "Expired", "Cancelled", "Arbitrage", "Completed",
                     "Cancelled by support", "Cannot process"]:
            if not InOrderStatus.objects.filter(name=name).exists():
                InOrderStatus.objects.create(name=name)

    def create_outorder_statuses(self):
        for name in ["New", "Money sent by trader", "Expired", "Cancelled", "Arbitrage", "Completed",
                     "Cancelled by support", "Cannot process", 'Failed']:
            if not OutOrderStatus.objects.filter(name=name).exists():
                OutOrderStatus.objects.create(name=name)

    def create_transaction_types(self):
        for name in ["Charge", "Deposit", "Freeze", "Withdrawal", "Transfer"]:
            if not TransactionType.objects.filter(name=name).exists():
                TransactionType.objects.create(name=name)

    def create_balances(self):
        for _type in [2, 3]:
            if not Balance.objects.filter(type=_type).exists():
                Balance.objects.create(type=_type)

    def create_currencies(self):
        if not Currency.objects.filter(symbol="TJS").exists():
            Currency.objects.create(name="Tajikistani Somoni", symbol="TJS")
        if not Currency.objects.filter(symbol="INR").exists():
            Currency.objects.create(name="Indian Rupee", symbol="INR")

    def create_languages(self):
        if not Language.objects.filter(name="Russian").exists():
            Language.objects.create(name="Russian")
        if not Language.objects.filter(name="English").exists():
            Language.objects.create(name="English")

    def create_defaults(self):
        self.create_currencies()
        self.create_languages()
        self.create_balances()
        self.create_transaction_types()
        self.create_inorder_statuses()
        self.create_pay_in_statuses()
        self.create_pay_out_statuses()
        self.create_outorder_statuses()

    def create_objects(self):
        self.create_trader()
        self.create_merchant()
        self.create_defaults()

        merchant = Merchant.objects.all().first()
        trader = Trader.objects.all().first()

        url = '/api/v1/merchant/merchant-fees/'
        data = {
            "payment_system": str(self.sberbank.id),
            "merchant": str(merchant.id),
            "mdr_in": 6,
            "mdr_out": 3,
            "traffic": str(self.gamble.id),
            "ftd": False
        }
        request = self.client.post(url, data, format='json')

        url = '/api/v1/merchant/merchant-fees/'
        data = {
            "payment_system": str(self.sbp.id),
            "merchant": str(merchant.id),
            "mdr_in": 6,
            "mdr_out": 3,
            "traffic": str(self.gamble.id),
            "ftd": False
        }
        request = self.client.post(url, data, format='json')

        url = '/api/v1/merchant/merchant-fees/'
        data = {
            "payment_system": str(self.sberpay.id),
            "merchant": str(merchant.id),
            "mdr_in": 6,
            "mdr_out": 3,
            "traffic": str(self.gamble.id),
            "ftd": False
        }

        request = self.client.post(url, data, format='json')

        merchant.balance.amount += Decimal(50000)
        trader.balance_usdt.amount += Decimal(10000)
        merchant.balance.save()
        trader.balance_usdt.save()

        self.gr = PaymentDetailsGroup.objects.create(owner="Иванов Иван Иванович", trader=trader, currency=self.currency, payment_system=self.sberbank, status=1)
        self.gr.allowed_traffic.add(self.gamble)
        self.gr.save()

        pd = PaymentDetails.objects.create(group=self.gr, card_number="1111000022223333", phone="+79863013344", deposit_number="1100", sberpay_enabled=True, sbp_enabled=True)

    def test_inorder(self):
        self.create_objects()
        solution = MerchantSolution.objects.all().first()
        order = InOrder.create(amount=1000, solution=solution, client_deposit_count=10, merchant_order_id="200202")
        sms = SMS.objects.create(status='success', text='fnjjfnf', device=self.gr)
        order.auto_sms(sms)

        balances = Balance.objects.all()

        for balance in balances:
            print(balance.amount, balance.type)

        order.recalculate(2000)

        balances = Balance.objects.all()
        print("-----")
        for balance in balances:
            print(balance.amount, balance.type)

        url = '/api/v1/trade/order/in/'
        request = self.client.get(url)
        print(request.content)
        # txs = Transaction.objects.all()
        # for tx in txs:
        #     print(tx.value)

    def test_move_order(self):

        self.create_objects()

        pd = PaymentDetails.objects.create(group=self.gr, card_number="0000121122223333", phone="+79863011344",
                                           deposit_number="0002")

        solution = MerchantSolution.objects.all().first()

        order = InOrder.create(amount=1000, solution=solution, client_deposit_count=10, merchant_order_id="200202")
        balance = order.payment_details.group.trader.balance_usdt
        frozen_balance = order.payment_details.group.trader.frozen_balance_usdt
        sms = SMS.objects.create(status='success', text='fnjjfnf', device=self.gr)
        order.automatically_complete(sms)


        team = TraderTeam.objects.all().first()
        team.rate_in = 5
        team.save()

        balances = Balance.objects.all()

        for balance in balances:
            print(balance.amount, balance.type)

        print(order.payment_details.card_number)

        order.move(pd)
        order.refresh_from_db()
        print(order.payment_details.card_number)
        balances = Balance.objects.all()
        print("-----")
        for balance in balances:
            print(balance.amount, balance.type)

    def test_outorder(self):
        self.create_objects()
        solution = MerchantSolution.objects.all().first()
        self.gr.amount += 50000
        self.gr.save()

        order = OutOrder.create(amount=1000, solution=solution, merchant_order_id="200202", details={"card_number": "0000111122223333"})
        print(order.status.name)
        print(order.payment_details)

        order.deal_expired()

        orders = OutOrder.objects.all()
        for order in orders:
            print(order.status.name, order.payment_details.group.trader)
        # order.money_sent()
        # sms = SMS.objects.create(status='success', text='fnjjfnf', device=self.gr)
        # order.auto_sms(sms)
        #
        # balances = Balance.objects.all()
        #
        # for balance in balances:
        #     print(balance.amount, balance.type)



        # order.recalculate(2000)

        # balances = Balance.objects.all()
        # print("-----")
        # for balance in balances:
        #     print(balance.amount, balance.type)
        #
        # response = self.client.get(f"/api/v1/trade/order/out/export/")
        # print(response.content)
        # data = json.loads(response.content)

    def create_api_keys(self):
        self.client = Client(headers={"GATE": os.getenv("PLATFORM_GATE")})
        self.client.login(username='merchant', password='password11!Q')
        response = self.client.post(f"/api/v1/payments/keys/")
        data = json.loads(response.content)
        return data.get('token'), data.get('private_key')

    def sign_request(self, public_key, private_key, data):
        sorted_data = json.dumps(data, sort_keys=True, cls=UUIDEncoder, separators=(',', ':')).encode()
        signature = hashlib.sha256(sorted_data + private_key.encode()).hexdigest()

        headers = {"Authorization": f"Token {public_key}", "Signature": signature}
        return headers

    def test_payin(self):
        self.create_objects()
        public_key, private_key = self.create_api_keys()
        print(PaymentDetails.objects.first().card_number)
        print(PaymentDetails.objects.first().deposit_number)
        print(PaymentDetails.objects.first().phone)
        print(PaymentDetails.objects.first().sberpay_enabled)
        url = '/api/v1/payments/in/invoice/'
        data = {
            "currency": "RUB",
            "amount": 10000,
            "payment_system": "SBP",
            "ftd": False,
            "merchant_order_id": "020202",
            "callback_url": "https://webhook.site/10250792-f6d1-45e7-ac35-d7fb827d0b04",
            "client": {"client_id": "0101"}
        }
        headers = self.sign_request(public_key, private_key, data)

        request = self.client.post(url, data=json.dumps(data), content_type="application/json", headers=headers)
        print(request.content)

        inorder = InOrder.objects.all().first()

        print(inorder.pay_in.exists())

        for tx in Transaction.objects.all():
            print(tx.value)

        device = TraderDevice.objects.all().first()
        token = Token.objects.get(user=device.user)
        url = '/api/v1/sms/process-sms/'
        headers = {"Authorization": f"Token {token}"}

        data = {'deposit_number': '1100', 'amount': 10000.0, 'balance': 12400.0, 'direction': 'in',
                'payment_system': 'Sber', 'methods': ['Sber'], 'success': True, 'blocked': False,
                'text': 'СЧЁТ1100 15:04 Перевод 10 000р от Альберт Б. Баланс: 2400р',
                'group': str(self.gr.id)}

        request = self.client.post(url, data=json.dumps(data), content_type="application/json", headers=headers)
        print(request.content)

        # inorder.complete()
        #
        # for tx in Transaction.objects.all():
        #     print(tx.value)
        #
        # pay_in = PayIn.objects.all().first()
        # print(pay_in.status.name)

        inorder.refresh_from_db()

        # print(inorder.payment_details.group.current_volume)

    def test_payout(self):
        self.create_objects()
        public_key, private_key = self.create_api_keys()
        self.gr.amount += 50000
        self.gr.save()
        url = '/api/v1/payments/out/h2h/'
        data = {
            "currency": "RUB",
            "amount": 5000,
            "payment_system": "SBP",
            "ftd": False,
            "merchant_order_id": "020202",
            "callback_url": "https://webhook.site/10250792-f6d1-45e7-ac35-d7fb827d0b04",
            "client": {"client_id": "0101"},
            "details": {"bank": "Сбер", "phone": "+79012234567"}
        }
        headers = self.sign_request(public_key, private_key, data)

        request = self.client.post(url, data=json.dumps(data), content_type="application/json", headers=headers)
        print(request.content)

        outorder = OutOrder.objects.all().first()
        print(outorder.payment_details.card_number)

        for tx in Transaction.objects.all():
            print(tx.value)

        outorder.complete()

        for tx in Transaction.objects.all():
            print(tx.value)

        pay_out = PayOut.objects.all().first()
        print(pay_out.status.name)

        outorder.refresh_from_db()

        print(outorder.payment_details.group.current_out_volume)

    def test_sms(self):
        self.create_objects()
        device = TraderDevice.objects.all().first()
        token = Token.objects.get(user=device.user)
        url = '/api/v1/sms/process-sms/'
        headers = {"Authorization": f"Token {token}"}

        data = {'card_number': '1100', 'amount': 10000.0, 'balance': 2400.0, 'direction': 'in', 'payment_system': 'Sber', 'methods': ['SBP'], 'success': True, 'blocked': False, 'text': 'СЧЁТ1100 15:04 Перевод 10 000р от Альберт Б. Баланс: 2400р', 'group': '546e3600-ae85-4f12-9be2-025c65be91e1'}

        request = self.client.post(url, data=json.dumps(data), content_type="application/json", headers=headers)
        print(request.content)


    def test_deposit(self):
        self.create_objects()
        from trade.utils2 import update_balances
        tr = Trader.objects.all().first()

        # Address.objects.create(address_public="010101", balance=tr.balance_usdt)
        update_balances()
        print(tr.balance_usdt.amount)


class TestProtocolWebhookPaidAmount(TestCase):
    def test_recalc_uses_amount_over_init(self):
        from payments.protocol_client import parse_protocol_webhook_paid_amount

        body = {
            "state": "pending",
            "amount": "3050.00",
            "init_amount": "3000.00",
            "orderId": "uuid",
        }
        self.assertEqual(parse_protocol_webhook_paid_amount(body), Decimal("3050.00"))

    def test_same_amounts(self):
        from payments.protocol_client import parse_protocol_webhook_paid_amount

        body = {"amount": "3000.00", "init_amount": "3000.00"}
        self.assertEqual(parse_protocol_webhook_paid_amount(body), Decimal("3000.00"))

    def test_psp_parser_detects_protocol_body(self):
        from payments.psp_payin import parse_psp_webhook_paid_amount

        body = {
            "state": "finished",
            "amount": "3100",
            "init_amount": "3000",
            "orderId": "pay-in-id",
        }
        self.assertEqual(parse_psp_webhook_paid_amount(body), Decimal("3100"))




