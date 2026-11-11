"""TronGrid-watched team wallet deposits → trader balance_usdt."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from basics.models import Balance, Currency, Language, Trader, TraderTeam
from trade.crypto_deposit_watch import credit_incoming_for_wallet, deposit_address_for_trader, parse_wallet_map
from trade.models import CryptoDepositCredit, TransactionType, WatchedDepositWallet


class CryptoDepositWatchTest(TestCase):
    def setUp(self):
        Language.objects.create(name="Russian")
        TransactionType.objects.get_or_create(name="Deposit")
        Balance.objects.create(type=3, amount=Decimal("0"))
        self.kzt = Currency.objects.create(name="Tenge CDW", symbol="KZT_CDW")
        team = TraderTeam.objects.create(name="cdw-team")
        user = User.objects.create_user(username="resdfe", password="x")
        self.trader = Trader.objects.create(
            user=user,
            team=team,
            currency=self.kzt,
            is_boss=True,
            balance_usdt=Balance.objects.create(type=0, amount=Decimal("10.00")),
            frozen_balance_usdt=Balance.objects.create(type=1, amount=Decimal("0")),
        )
        self.wallet = WatchedDepositWallet.objects.create(
            address_public="TTr5G2wrtchVEF4DfMRbNZZeZppHxyyWyL",
            trader=self.trader,
            enabled=True,
            watch_from=timezone.now() - timedelta(minutes=5),
        )

    def test_parse_wallet_map(self):
        rows = parse_wallet_map("TTr5G2wrtchVEF4DfMRbNZZeZppHxyyWyL:resdfe, other:xx")
        self.assertEqual(rows[0][1], "resdfe")

    def test_deposit_address_prefers_watched(self):
        self.assertEqual(
            deposit_address_for_trader(self.trader),
            "TTr5G2wrtchVEF4DfMRbNZZeZppHxyyWyL",
        )

    @patch("trade.crypto_deposit_watch.fetch_trc20_incoming")
    def test_credits_new_transfer(self, fetch):
        ts = int((timezone.now() - timedelta(minutes=1)).timestamp() * 1000)
        fetch.return_value = [
            {
                "transaction_id": "abc123txid",
                "to": self.wallet.address_public,
                "from": "TFromSomewhere",
                "value": "1500000",
                "block_timestamp": ts,
                "token_info": {"decimals": 6},
            }
        ]
        stats = credit_incoming_for_wallet(self.wallet)
        self.assertEqual(stats["credited"], 1)
        self.trader.balance_usdt.refresh_from_db()
        self.assertEqual(self.trader.balance_usdt.amount, Decimal("11.50"))
        self.assertTrue(CryptoDepositCredit.objects.filter(tx_id="abc123txid", credited=True).exists())

        # idempotent
        stats2 = credit_incoming_for_wallet(self.wallet)
        self.assertEqual(stats2["credited"], 0)
        self.trader.balance_usdt.refresh_from_db()
        self.assertEqual(self.trader.balance_usdt.amount, Decimal("11.50"))

    @patch("trade.crypto_deposit_watch.fetch_trc20_incoming")
    def test_skips_before_watch_from(self, fetch):
        old_ts = int((timezone.now() - timedelta(hours=2)).timestamp() * 1000)
        fetch.return_value = [
            {
                "transaction_id": "oldtx",
                "to": self.wallet.address_public,
                "from": "TFrom",
                "value": "5000000",
                "block_timestamp": old_ts,
                "token_info": {"decimals": 6},
            }
        ]
        self.wallet.watch_from = timezone.now() - timedelta(minutes=10)
        self.wallet.save(update_fields=["watch_from"])
        stats = credit_incoming_for_wallet(self.wallet)
        self.assertEqual(stats["credited"], 0)
        self.trader.balance_usdt.refresh_from_db()
        self.assertEqual(self.trader.balance_usdt.amount, Decimal("10.00"))
