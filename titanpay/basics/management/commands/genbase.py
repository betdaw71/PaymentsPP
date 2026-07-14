from django.conf import settings
from django.core.management import BaseCommand
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
import uuid
from bots.models import TGBot


class Command(BaseCommand):
    def create_pay_in_statuses(self):
        from payments.models import PayInStatus

        for name in ["New", "In Progress", "Success", "Failed", "Declined"]:
            if not PayInStatus.objects.filter(name=name).exists():
                PayInStatus.objects.create(name=name)

        print('PayInStatuses created')

    def create_pay_out_statuses(self):
        from payments.models import PayOutStatus

        for name in ["New", "In Progress", "Success", "Failed", "Declined"]:
            if not PayOutStatus.objects.filter(name=name).exists():
                PayOutStatus.objects.create(name=name)

        print('PayOutStatuses created')

    def create_inorder_statuses(self):
        from trade.models import InOrderStatus

        for name in ["New", "Money sent by user", "Expired", "Cancelled", "Arbitrage", "Completed", "Cancelled by support", "Cannot process", "Cancelled by trader", 'Recalculation']:
            if not InOrderStatus.objects.filter(name=name).exists():
                InOrderStatus.objects.create(name=name)

        print('InOrderStatuses created')

    def create_outorder_statuses(self):
        from trade.models import OutOrderStatus

        for name in ["New", "Money sent by trader", "Expired", "Cancelled", "Arbitrage", "Completed", "Cancelled by support", "Cannot process", 'Failed', 'Manual check', 'Recalculation']:
            if not OutOrderStatus.objects.filter(name=name).exists():
                OutOrderStatus.objects.create(name=name)

        print('OutOrderStatuses created')

    def create_transaction_types(self):
        from trade.models import TransactionType

        for name in ["Charge", "Deposit", "Freeze", "Withdrawal", "Transfer"]:
            if not TransactionType.objects.filter(name=name).exists():
                TransactionType.objects.create(name=name)

        print('TransactionTypes created')

    def create_balances(self):
        from basics.models import Balance

        for _type in [2, 3]:
            if not Balance.objects.filter(type=_type).exists():
                Balance.objects.create(type=_type)

        print('Balances created')

    def create_currencies(self):
        from basics.models import Currency

        if not Currency.objects.filter(symbol="TJS").exists():
            Currency.objects.create(name="Tajikistani Somoni", symbol="TJS")
        if not Currency.objects.filter(symbol="INR").exists():
            Currency.objects.create(name="Indian Rupee", symbol="INR")

        print('Currencies created')

    def create_languages(self):
        from basics.models import Language

        if not Language.objects.filter(name="Russian").exists():
            Language.objects.create(name="Russian")
        if not Language.objects.filter(name="English").exists():
            Language.objects.create(name="English")

        print('Languages created')

    def create_tgbots(self):
        if not User.objects.filter(username="outorder_bot_user").exists():
            outorder_user = User.objects.create_user(username="outorder_bot_user", password=str(uuid.uuid4()))
            TGBot.objects.create(user=outorder_user)
            Token.objects.create(user=outorder_user)

        if not User.objects.filter(username="smsdata_bot_user").exists():
            smsdata_user = User.objects.create_user(username="smsdata_bot_user", password=str(uuid.uuid4()))
            TGBot.objects.create(user=smsdata_user)
            Token.objects.create(user=smsdata_user)

        print('Bots created')

    def handle(self, *args, **options):
        self.create_currencies()
        self.create_languages()
        self.create_balances()
        self.create_transaction_types()
        self.create_inorder_statuses()
        self.create_pay_in_statuses()
        self.create_pay_out_statuses()
        self.create_outorder_statuses()
