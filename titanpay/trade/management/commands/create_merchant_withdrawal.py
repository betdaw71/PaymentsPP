"""Создать заявку на вывод (WithdrawalRequest) для мерчанта с сервера."""
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from trade.models import WithdrawalRequest


class Command(BaseCommand):
    help = (
        "Создать заявку на вывод мерчанту: заморозка баланса + WithdrawalRequest (status=0). "
        "Пример: python manage.py create_merchant_withdrawal aggrepay 5000 --address Txxx"
    )

    def add_arguments(self, parser):
        parser.add_argument("merchant_username", type=str, help="User.username мерчанта")
        parser.add_argument("amount", type=str, help="Сумма вывода (USD), например 5000")
        parser.add_argument(
            "--address",
            type=str,
            default="",
            help="Адрес назначения (USDT TRC20 и т.п.), max 50 символов",
        )
        parser.add_argument(
            "--reuse-last-address",
            action="store_true",
            help="Взять address_to из последней заявки этого мерчанта",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только проверить мерчанта/баланс/адрес, ничего не создавать",
        )

    def handle(self, *args, **options):
        username = (options["merchant_username"] or "").strip()
        address = (options.get("address") or "").strip()
        dry_run = bool(options.get("dry_run"))

        try:
            amount = Decimal(str(options["amount"]).strip())
        except (InvalidOperation, AttributeError) as exc:
            raise CommandError(f"Некорректная сумма: {options['amount']!r}") from exc

        if amount <= 0:
            raise CommandError("Сумма должна быть больше нуля")

        try:
            user = User.objects.select_related("merchant", "merchant__balance").get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Пользователь {username!r} не найден") from exc

        if not hasattr(user, "merchant") or user.merchant is None:
            raise CommandError(f"У пользователя {username!r} нет профиля Merchant")

        merchant = user.merchant
        balance = merchant.balance
        if balance is None:
            raise CommandError(f"У мерчанта {username!r} нет баланса")

        if options.get("reuse_last_address"):
            last = (
                WithdrawalRequest.objects.filter(from_user=user)
                .exclude(address_to="")
                .order_by("-date")
                .first()
            )
            if last is None:
                raise CommandError(
                    f"У мерчанта {username!r} нет прошлых заявок с адресом — укажите --address"
                )
            address = (last.address_to or "").strip()
            self.stdout.write(f"Адрес из последней заявки {last.id}: {address}")

        if not address:
            raise CommandError("Нужен --address или --reuse-last-address")
        if len(address) > 50:
            raise CommandError(f"Адрес длиннее 50 символов ({len(address)})")

        self.stdout.write(f"Мерчант: {username}")
        self.stdout.write(f"Баланс:  {balance.amount}")
        self.stdout.write(f"Сумма:   {amount}")
        self.stdout.write(f"Адрес:   {address}")

        if balance.amount < amount:
            raise CommandError(
                f"Недостаточно средств: нужно {amount}, доступно {balance.amount}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: заявка не создана"))
            return

        try:
            with transaction.atomic():
                wr = WithdrawalRequest.create(
                    amount=amount,
                    _from=balance,
                    address_to=address,
                    from_user=user,
                )
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc

        balance.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Заявка создана: id={wr.id} status={wr.status} "
                f"amount={wr.amount} новый_баланс={balance.amount}"
            )
        )
