import uuid
import logging
from basics.models import Language, Currency, PaymentSystem, Balance, TrafficType, Trader, PaymentDetails, \
    PaymentDetailsGroup, TraderTeamRates
from django.contrib.auth.models import User
from sms.models import SMS
from merchant.models import Merchant, MerchantSolution
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from rest_framework.exceptions import ValidationError
from trade.utils import choose_trader_in, choose_trader_out, check_details, calculate_fees
from django.utils import timezone
from decimal import Decimal
from titanpay.settings import SYSTEM_INTERVAL_VALUE, ARBITRAGE_LIMIT


class TransactionType(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class InOrderStatus(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, default="New", unique=True)

    def __str__(self):
        return self.name


class OutOrderStatus(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    name = models.CharField(max_length=64, default="New")

    def __str__(self):
        return self.name


class InOrder(models.Model):
    REJECTION_CHOICES = [
        ("no-pay", "No payment"),
        ("inc-check", "Incorrect check"),
        ("wr-req", "Wrong reqs"),
        ("wr-dir", "Wrong SBP direction"),
    ]
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    status = models.ForeignKey(to=InOrderStatus, on_delete=models.SET_NULL, null=True)

    completion_date = models.DateTimeField(null=True)
    updated_date = models.DateTimeField(null=True)

    rejection_reason = models.CharField(max_length=10, choices=REJECTION_CHOICES, null=True, blank=True)

    amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    usd_amount = models.DecimalField(default=0, editable=False, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    solution = models.ForeignKey(to=MerchantSolution, on_delete=models.CASCADE)

    payment_details = models.ForeignKey(to=PaymentDetails, on_delete=models.SET_NULL, null=True, related_name="inorders")

    arbitrage_comment = models.CharField(max_length=63)
    merchant_order_id = models.CharField(default="", max_length=256)

    pic = models.URLField()

    recalculated_amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    creation_date = models.DateTimeField(default=timezone.now, editable=False)

    merchant_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    trader_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    agent_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    recalculated = models.BooleanField(default=False)

    auto_closed = models.BooleanField(default=False)
    sms = models.ForeignKey(to=SMS, null=True, blank=True, on_delete=models.SET_NULL, related_name="inorder")

    @classmethod
    def create(cls, amount: float, solution: MerchantSolution, client_deposit_count, merchant_order_id: str = ""):
        amount = Decimal.from_float(amount) if isinstance(amount, float) else amount

        active_orders = cls.objects.filter(status__name__in=["New", "Money sent by user"], amount=amount, solution__payment_system=solution.payment_system)

        chosen_detail, usd_amount, payment_system_obj, success = choose_trader_in(
            amount, solution.payment_system, solution.traffic, active_orders, client_deposit_count, merchant=solution.merchant,
        )

        if not success:
            status = InOrderStatus.objects.get(name="Cannot process")
            order_obj = cls(status=status, amount=amount, usd_amount=usd_amount,
                            solution=solution, payment_details=None,
                            merchant_order_id=merchant_order_id, agent_fee=Decimal(0))
            order_obj.save()
            return order_obj

        status = InOrderStatus.objects.get(name="New")

        from merchant.tiered_mdr import merchant_payin_fee

        merchant_fee = merchant_payin_fee(solution=solution, amount=amount, usd_amount=usd_amount)
        team_rate = TraderTeamRates.objects.get(team=chosen_detail.group.trader.team, payment_system=payment_system_obj)
        trader_fee = team_rate.mdr_in * usd_amount / Decimal(100)

        order_obj = cls(status=status, amount=amount, usd_amount=usd_amount, solution=solution, payment_details=chosen_detail, merchant_order_id=merchant_order_id, merchant_fee=merchant_fee, trader_fee=trader_fee, agent_fee=Decimal(0))
        order_obj.save()

        try:
            order_obj.freeze(comment="New in-order received")
        except ValidationError:
            order_obj.payment_details = None
            order_obj.status = InOrderStatus.objects.get(name="Cannot process")
            order_obj.updated_date = timezone.now()
            order_obj.save(update_fields=["payment_details", "status", "updated_date"])
            return order_obj

        group = PaymentDetailsGroup.objects.select_for_update().get(id=order_obj.payment_details.group.id)
        group.current_volume += amount
        group.updated_at = timezone.now()
        group.save()

        return order_obj

    def freeze(self, comment=""):
        trader = self.payment_details.group.trader
        value = self.usd_amount
        from payments.psp_payin import is_psp_trader, psp_order_usd_ledger_amount

        if is_psp_trader(trader):
            value = psp_order_usd_ledger_amount(self)

        transaction_type = TransactionType.objects.get(name="Freeze")
        Transaction.create(_from=trader.balance_usdt, _to=trader.frozen_balance_usdt,
                           value=value, _transaction_type=transaction_type, _linked_in_order=self,
                           _comment=comment)

    def unfreeze(self, comment=""):
        """Разморозка всех неоткатанных Freeze по заявке (PSP может иметь несколько freeze)."""
        from basics.models import Balance

        logger = logging.getLogger(__name__)
        transaction_type_2 = TransactionType.objects.get(name="Deposit")
        max_passes = 10

        for _ in range(max_passes):
            unreversed = None
            for freeze_tx in (
                Transaction.objects.filter(
                    linked_in_order=self,
                    transaction_type__name="Freeze",
                )
                .select_related("from_balance", "to_balance")
                .order_by("creation_date")
            ):
                already = Transaction.objects.filter(
                    linked_in_order=self,
                    transaction_type__name="Deposit",
                    from_balance=freeze_tx.to_balance,
                    to_balance=freeze_tx.from_balance,
                    creation_date__gte=freeze_tx.creation_date,
                ).exists()
                if not already:
                    unreversed = freeze_tx
                    break
            if unreversed is None:
                return

            from_balance = Balance.objects.select_for_update().get(pk=unreversed.to_balance_id)
            value = unreversed.value
            if from_balance.amount < value:
                logger.warning(
                    "InOrder %s unfreeze: frozen %.2f < freeze %.2f (%s); releasing available frozen",
                    self.id,
                    from_balance.amount,
                    value,
                    comment,
                )
                value = from_balance.amount
            if value <= 0:
                continue
            Transaction.create(
                _from=unreversed.to_balance,
                _to=unreversed.from_balance,
                value=value,
                _transaction_type=transaction_type_2,
                _linked_in_order=self,
                _comment=comment,
            )
        logger.warning("InOrder %s unfreeze: max passes reached (%s)", self.id, comment)

    def decrease_current_volume(self):
        group = PaymentDetailsGroup.objects.select_for_update().get(id=self.payment_details.group.id)
        if self.creation_date.timestamp() // SYSTEM_INTERVAL_VALUE == int(timezone.now().timestamp()) // SYSTEM_INTERVAL_VALUE:
            group.current_volume -= self.amount
            group.updated_at = timezone.now()
            group.save()

    def complete(self):
        from payments.psp_payin import ensure_psp_frozen_for_complete

        ensure_psp_frozen_for_complete(self)
        trader = self.payment_details.group.trader
        from payments.psp_payin import is_psp_trader, psp_order_usd_ledger_amount

        charge_usd = self.usd_amount
        if is_psp_trader(trader):
            charge_usd = psp_order_usd_ledger_amount(self)

        status = InOrderStatus.objects.get(name="Completed")
        self.status = status
        self.updated_date = timezone.now()
        self.completion_date = timezone.now()

        aggregator_balance = Balance.objects.get(type=2)

        transaction_type_1 = TransactionType.objects.get(name="Charge")
        transaction_type_2 = TransactionType.objects.get(name="Deposit")

        from merchant.kzt_settlement import (
            in_order_credit_kzt,
            merchant_available_balance,
            uses_melbet_kzt_settlement,
        )

        for_trader = self.trader_fee
        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            for_merchant = in_order_credit_kzt(self)
            merchant_balance = merchant_available_balance(self.solution.merchant)
        else:
            for_merchant = self.usd_amount - self.merchant_fee
            merchant_balance = self.solution.merchant.balance

        to_aggregator = Transaction.create(_from=trader.frozen_balance_usdt, _to=aggregator_balance,
                                           value=charge_usd, _transaction_type=transaction_type_1,
                                           _linked_in_order=self, _comment="In-order completed")

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            # KZT merchant leg: не списываем USDT-агрегатор на сумму в тенге (только USDT от трейдера выше).
            blockchain = Balance.objects.get(type=3)
            from_aggregator_to_merchant = Transaction.create(
                _from=blockchain,
                _to=merchant_balance,
                value=for_merchant,
                _transaction_type=transaction_type_2,
                _linked_in_order=self,
                _comment="In-order completed",
            )
        else:
            from_aggregator_to_merchant = Transaction.create(_from=aggregator_balance, _to=merchant_balance,
                                                         value=for_merchant, _transaction_type=transaction_type_2,
                                                         _linked_in_order=self, _comment="In-order completed")

        from_aggregator_to_trader = Transaction.create(_from=aggregator_balance, _to=trader.balance_usdt,
                                                       value=for_trader,
                                                       _transaction_type=transaction_type_2, _linked_in_order=self,
                                                       _comment="Commission")

        if trader.team.teamlead is not None:
            teamlead_share = self.trader_fee * trader.team.teamlead_percentage / Decimal(100)
            from_trader_to_teamlead = Transaction.create(_from=trader.balance_usdt, _to=trader.team.teamlead.balance, value=teamlead_share, _transaction_type=transaction_type_1, _linked_in_order=self, _comment="Teamlead commission")

        self.payment_details.group.total_volume += self.amount
        self.payment_details.group.save()
        InOrderStatusChange.create(order=self, status=status)
        self.save()

    def automatically_complete(self, sms, balance=None):
        if self.status.name != "Money sent by user" and self.status.name != "New" and self.status.name != "Arbitrage":
            raise ValidationError({"error": f"Current status is {self.status.name}"})

        if balance is not None:
            self.payment_details.update_balance(Decimal(balance))

        self.auto_closed = True
        self.sms = sms
        self.complete()

        sms.status = 'success'
        sms.save()

        return "Success"

    def automatically_complete_arbitrage(self, sms, balance=None):
        if self.status.name != "Arbitrage":
            raise ValidationError({"error": f"Current status is {self.status.name}"})

        self.auto_closed = True
        self.sms = sms
        self.complete_after_arbitrage()

        if balance is not None:
            self.payment_details.update_balance(Decimal(balance))

        return "Success"

    def change_to_money_sent_by_user(self):
        if self.status.name != "New":
            raise ValidationError({
                                      'error': 'Wrong method is used. This method is for changing status from "New" to "Money sent by user"'})
        status = InOrderStatus.objects.get(name="Money sent by user")
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        InOrderStatusChange.create(order=self, status=status)

    def complete_after_new(self):
        if self.status.name != "New" and self.status.name != "Money sent by user":
            raise ValidationError({'error': 'Wrong status'})
        self.complete()

    def deal_time_expired(self):
        if self.status.name != "New" and self.status.name != "Money sent by user":
            raise ValidationError({'error': 'Wrong method is used. This method is for changing status from "New" to "Expired"'})
        status = InOrderStatus.objects.get(name="Expired")
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        self.decrease_current_volume()

        self.unfreeze("In-order expired")

        InOrderStatusChange.create(order=self, status=status)

    def apply_psp_paid_amount_recalc(self, paid_amount: Decimal) -> bool:
        """PSP подтвердил сумму, отличную от заявки (перерасчёт)."""
        paid_amount = Decimal(str(paid_amount)).quantize(Decimal("0.01"))
        if paid_amount <= 0 or paid_amount == self.amount:
            return False
        new_usd = paid_amount / self.solution.payment_system.get_rate()
        team_rate = TraderTeamRates.objects.get(
            team=self.payment_details.group.trader.team,
            payment_system=self.solution.payment_system,
        )
        from merchant.tiered_mdr import merchant_payin_fee

        self.amount = paid_amount
        self.usd_amount = new_usd
        self.merchant_fee = merchant_payin_fee(
            solution=self.solution, amount=paid_amount, usd_amount=new_usd
        )
        self.trader_fee = team_rate.mdr_in * new_usd / Decimal(100)
        self.recalculated = True
        self.recalculated_amount = paid_amount
        self.save()
        pay_in = self.pay_in.get()
        pay_in.amount = paid_amount
        pay_in.recalculated = True
        pay_in.save(update_fields=["amount", "recalculated", "updated_at"])
        return True

    def _merchant_credit_amount(self) -> Decimal:
        from merchant.kzt_settlement import in_order_credit_kzt, uses_melbet_kzt_settlement

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            return in_order_credit_kzt(self)
        return self.usd_amount - self.merchant_fee

    def _apply_completed_recalc_ledger(
        self,
        trader,
        *,
        old_charge_usd: Decimal,
        old_for_merchant: Decimal,
        old_for_trader: Decimal,
        new_charge_usd: Decimal,
        new_for_merchant: Decimal,
        new_for_trader: Decimal,
    ) -> None:
        from decimal import ROUND_HALF_UP

        from basics.models import Balance
        from merchant.kzt_settlement import merchant_available_balance, uses_melbet_kzt_settlement
        from payments.psp_payin import ensure_psp_frozen_for_complete, is_psp_trader

        aggregator = Balance.objects.get(type=2)
        tx_charge = TransactionType.objects.get(name="Charge")
        tx_deposit = TransactionType.objects.get(name="Deposit")
        comment = "PSP completed recalculation"

        if is_psp_trader(trader):
            d_charge = (new_charge_usd - old_charge_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if d_charge > 0:
                ensure_psp_frozen_for_complete(self)
                Transaction.create(
                    _from=trader.frozen_balance_usdt,
                    _to=aggregator,
                    value=d_charge,
                    _transaction_type=tx_charge,
                    _linked_in_order=self,
                    _comment=comment,
                )
            elif d_charge < 0:
                Transaction.create(
                    _from=aggregator,
                    _to=trader.frozen_balance_usdt,
                    value=-d_charge,
                    _transaction_type=tx_deposit,
                    _linked_in_order=self,
                    _comment=comment,
                )

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            merchant_balance = merchant_available_balance(self.solution.merchant)
            blockchain = Balance.objects.get(type=3)
            d_merchant = (new_for_merchant - old_for_merchant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if d_merchant > 0:
                Transaction.create(
                    _from=blockchain,
                    _to=merchant_balance,
                    value=d_merchant,
                    _transaction_type=tx_deposit,
                    _linked_in_order=self,
                    _comment=comment,
                )
            elif d_merchant < 0:
                Transaction.create(
                    _from=merchant_balance,
                    _to=blockchain,
                    value=-d_merchant,
                    _transaction_type=tx_charge,
                    _linked_in_order=self,
                    _comment=comment,
                )
        else:
            merchant_balance = self.solution.merchant.balance
            d_merchant = (new_for_merchant - old_for_merchant).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if d_merchant > 0:
                Transaction.create(
                    _from=aggregator,
                    _to=merchant_balance,
                    value=d_merchant,
                    _transaction_type=tx_deposit,
                    _linked_in_order=self,
                    _comment=comment,
                )
            elif d_merchant < 0:
                Transaction.create(
                    _from=merchant_balance,
                    _to=aggregator,
                    value=-d_merchant,
                    _transaction_type=tx_charge,
                    _linked_in_order=self,
                    _comment=comment,
                )

        d_trader = (new_for_trader - old_for_trader).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if d_trader > 0:
            Transaction.create(
                _from=aggregator,
                _to=trader.balance_usdt,
                value=d_trader,
                _transaction_type=tx_deposit,
                _linked_in_order=self,
                _comment=comment,
            )
        elif d_trader < 0:
            Transaction.create(
                _from=trader.balance_usdt,
                _to=aggregator,
                value=-d_trader,
                _transaction_type=tx_charge,
                _linked_in_order=self,
                _comment=comment,
            )

    def apply_psp_completed_recalc(self, paid_amount: Decimal) -> bool:
        """Перерасчёт после Completed (Bitzone re_calculation после closed)."""
        from decimal import ROUND_HALF_UP

        from payments.psp_payin import is_psp_trader, psp_order_usd_ledger_amount

        if self.status.name != "Completed":
            raise ValidationError({"error": "Wrong status for completed PSP recalc"})
        paid_amount = Decimal(str(paid_amount)).quantize(Decimal("0.01"))
        if paid_amount <= 0 or paid_amount == self.amount:
            return False

        trader = self.payment_details.group.trader
        old_amount = self.amount
        old_charge = psp_order_usd_ledger_amount(self) if is_psp_trader(trader) else self.usd_amount
        old_for_merchant = self._merchant_credit_amount()
        old_for_trader = self.trader_fee

        rate = self.solution.payment_system.get_rate()
        new_usd = paid_amount / rate
        team_rate = TraderTeamRates.objects.get(
            team=trader.team,
            payment_system=self.solution.payment_system,
        )
        from merchant.tiered_mdr import merchant_payin_fee

        new_merchant_fee = merchant_payin_fee(
            solution=self.solution, amount=paid_amount, usd_amount=new_usd
        )
        new_trader_fee = team_rate.mdr_in * new_usd / Decimal(100)

        self.amount = paid_amount
        self.usd_amount = new_usd
        self.merchant_fee = new_merchant_fee
        self.trader_fee = new_trader_fee
        new_charge = psp_order_usd_ledger_amount(self) if is_psp_trader(trader) else new_usd
        new_for_merchant = self._merchant_credit_amount()
        new_for_trader = new_trader_fee

        self._apply_completed_recalc_ledger(
            trader,
            old_charge_usd=old_charge,
            old_for_merchant=old_for_merchant,
            old_for_trader=old_for_trader,
            new_charge_usd=new_charge,
            new_for_merchant=new_for_merchant,
            new_for_trader=new_for_trader,
        )

        self.recalculated = True
        self.recalculated_amount = paid_amount
        self.save()

        group = self.payment_details.group
        group.total_volume += paid_amount - old_amount
        group.save(update_fields=["total_volume"])

        pay_in = self.pay_in.get()
        pay_in.amount = paid_amount
        pay_in.recalculated = True
        pay_in.save(update_fields=["amount", "recalculated", "updated_at"])
        pay_in.send_callback({"status": pay_in.status.name})
        return True

    def complete_from_psp_success(self, paid_amount: Decimal | None = None) -> None:
        """Завершение pay-in по success webhook PSP (в т.ч. Expired + перерасчёт)."""
        state = self.status.name if self.status else None
        needs_recalc = (
            paid_amount is not None
            and paid_amount > 0
            and paid_amount != self.amount
        )
        if state in ("New", "Money sent by user"):
            if needs_recalc:
                self.recalculate(paid_amount)
            else:
                self.complete_after_new()
        elif state == "Expired":
            if needs_recalc:
                self.apply_psp_paid_amount_recalc(paid_amount)
            self.complete_after_expired()
        elif state == "Cancelled":
            if needs_recalc:
                self.apply_psp_paid_amount_recalc(paid_amount)
            self.complete_after_cancelled()
        elif state == "Arbitrage":
            if needs_recalc:
                self.recalculate(paid_amount)
            else:
                self.complete_after_arbitrage()
        else:
            raise ValidationError({"error": f"Cannot complete from PSP in state {state}"})

    def complete_after_expired(self):

        if self.status.name != "Expired":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status from "Expired" to "Completed"'})

        self.save()
        self.freeze("Complete expired order")
        self.complete()

    def complete_after_cancelled(self):
        """Оплата подтверждена PSP после локальной отмены (rollback create, cancel_order, fail webhook)."""
        if self.status.name != "Cancelled":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status from "Cancelled" to "Completed"'})

        self.save()
        self.freeze("Complete cancelled order (PSP paid)")
        self.complete()

    def arbitrage(self):
        if self.status.name not in ["Cancelled", "Expired", "Cancelled by support", "Cancelled by trader"]:
            raise ValidationError({'error': 'Wrong status for this action.'})

        status = InOrderStatus.objects.get(name="Arbitrage")
        arbitrage_count = InOrderStatusChange.objects.filter(status=status, order=self).count()

        if arbitrage_count >= ARBITRAGE_LIMIT:
            raise ValidationError({'error': 'Arbitrage limit exceeded for this order'})

        self.freeze("Arbitrage")
        self.arbitrage_comment = "Arbitrage called by client"
        self.payment_details.group.status = 4
        self.payment_details.group.save()

        self.status = status
        self.payment_details.save()
        self.updated_date = timezone.now()
        self.save()
        InOrderStatusChange.create(order=self, status=status)

    def arbitrage_support(self):
        if self.status.name != "Expired":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status to "Arbitrage"'})

        self.freeze("Freeze for arbitrage")

        status = InOrderStatus.objects.get(name="Arbitrage")
        self.arbitrage_comment = "Arbitrage called by support"
        self.payment_details.group.status = 4
        self.payment_details.group.save()
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        InOrderStatusChange.create(order=self, status=status)

    def arbitrage_expired(self):
        if self.status.name != "Money sent by user":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status to "Arbitrage"'})
        status = InOrderStatus.objects.get(name="Arbitrage")
        self.arbitrage_comment = "Arbitrage due to inactivity"
        self.payment_details.group.status = 4
        self.payment_details.group.save()
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        InOrderStatusChange.create(order=self, status=status)

    def complete_after_recalc(self):
        if self.status.name != "Recalculation":
            raise ValidationError({'error': 'Wrong status'})

        self.complete()

    def complete_after_arbitrage(self):
        if self.status.name != "Arbitrage":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status from "Arbitrage" to "Completed"'})

        arbitrage_orders = InOrder.objects.filter(status__name="Arbitrage", payment_details__group=self.payment_details.group)
        if arbitrage_orders.count() == 1 and self.payment_details.group.status == 4:
            self.payment_details.group.status = 1
            self.payment_details.group.save()
        self.complete()

        try:
            from appeals.notify import resolve_pending_appeals_for_order
            resolve_pending_appeals_for_order(self, approved=True)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("appeal approve notify failed order=%s", self.id)

    def cancel_order(self):
        if self.status.name != "New":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status from "New" to "Cancelled"'})
        status = InOrderStatus.objects.get(name="Cancelled")

        self.status = status
        self.updated_date = timezone.now()
        self.decrease_current_volume()
        self.save()

        self.unfreeze("In-order cancelled by user")

        InOrderStatusChange.create(order=self, status=status)

    def cancel_by_support(self):
        if self.status.name != "Recalculation":
            raise ValidationError({
                'error': 'Wrong status"'})
        status = InOrderStatus.objects.get(name="Cancelled by support")
        self.status = status
        self.updated_date = timezone.now()
        self.decrease_current_volume()
        self.save()

        self.unfreeze("In-order cancelled by support")

        InOrderStatusChange.create(order=self, status=status)

    def cancel_by_trader(self, rejection_reason):
        if self.status.name != "Arbitrage":
            raise ValidationError({
                'error': 'Wrong method is used. This method is for changing status from "Arbitrage" to "Cancelled by support"'})
        status = InOrderStatus.objects.get(name="Cancelled by trader")

        arbitrage_orders = InOrder.objects.filter(status__name="Arbitrage",
                                                  payment_details__group=self.payment_details.group)
        if arbitrage_orders.count() == 1 and self.payment_details.group.status == 4:
            self.payment_details.group.status = 1
            self.payment_details.group.save()

        self.status = status
        self.updated_date = timezone.now()
        self.rejection_reason = rejection_reason
        self.decrease_current_volume()
        self.save()

        self.unfreeze("In-order cancelled by trader")

        InOrderStatusChange.create(order=self, status=status)

        try:
            from appeals.notify import resolve_pending_appeals_for_order
            resolve_pending_appeals_for_order(self, approved=False)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("appeal reject notify failed order=%s", self.id)

    def trader_recalculate(self, new_amount: Decimal):
        if self.status.name != "Arbitrage":
            raise ValidationError({'error': 'Wrong status!'})
        self.recalculated_amount = new_amount

        arbitrage_orders = InOrder.objects.filter(status__name="Arbitrage",
                                                  payment_details__group=self.payment_details.group)
        if arbitrage_orders.count() == 1 and self.payment_details.group.status == 4:
            self.payment_details.group.status = 1
            self.payment_details.group.save()
        status = InOrderStatus.objects.get(name="Recalculation")
        self.status = status
        self.save()
        InOrderStatusChange.create(order=self, status=status)
        return

        # self.recalculate(new_amount)

    def support_recalculate(self, new_amount: Decimal):
        if self.status.name != "Recalculation":
            raise ValidationError({'error': 'Wrong status!'})
        self.recalculate(new_amount)
        return

    def recalculate(self, new_amount: Decimal):
        new_usd_amount = new_amount / self.solution.payment_system.get_rate()
        from merchant.tiered_mdr import merchant_payin_fee

        new_merchant_fee = merchant_payin_fee(
            solution=self.solution, amount=new_amount, usd_amount=new_usd_amount
        )
        new_trader_fee = self.payment_details.group.trader.team.rate_in * new_usd_amount / Decimal(100)

        if self.creation_date.timestamp() // SYSTEM_INTERVAL_VALUE == int(timezone.now().timestamp()) // SYSTEM_INTERVAL_VALUE:
            self.payment_details.group.current_volume -= self.amount + new_amount
            self.payment_details.group.updated_at = timezone.now()
            self.payment_details.group.save()

        self.unfreeze("Recalculation")

        self.amount = new_amount
        self.usd_amount = new_usd_amount
        self.merchant_fee = new_merchant_fee
        self.trader_fee = new_trader_fee
        self.recalculated = True
        self.save()

        self.freeze("Recalculation")

        self.pay_in.get().recalculate(new_amount)
        self.complete()

    def move(self, new_details):

        if self.status.name not in ["New", "Cancelled", "Cancelled by trader", "Cancelled by support", "Expired"]:
            raise ValidationError({'error': 'Wrong status for this action'})

        new_trader_fee = new_details.group.trader.team.rate_in * self.usd_amount / Decimal(100)

        if self.status.name == "New":
            self.decrease_current_volume()
            self.unfreeze("In-order moved")

        self.trader_fee = new_trader_fee
        self.payment_details = new_details
        self.save()

        new_details.group.current_volume += self.amount
        new_details.group.updated_at = timezone.now()
        new_details.group.save()

        self.freeze("In-order moved")
        self.complete()


class InOrderStatusChange(models.Model):
    status = models.ForeignKey(to=InOrderStatus, on_delete=models.DO_NOTHING, related_name="change")
    order = models.ForeignKey(to=InOrder, on_delete=models.CASCADE, related_name="status_change")
    timedelta = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    @classmethod
    def create(cls, order: InOrder, status: InOrderStatus):
        last_change = cls.objects.filter(order=order)

        if not last_change.exists():
            timedelta = (timezone.now() - order.creation_date).total_seconds()
        else:
            last_change_obj = last_change.latest('created_at')
            timedelta = (timezone.now() - last_change_obj.created_at).total_seconds()

        status_change_obj = cls(status=status, order=order, timedelta=timedelta)
        status_change_obj.save()

        if status.name == "Completed":
            order.pay_in.get().success()
        elif status.name in ["Money sent by user", "Arbitrage", "Recalculation", "New"]:
            order.pay_in.get().in_progress()
        else:
            order.pay_in.get().failed()
        return status_change_obj


class OutOrder(models.Model):
    REJECTION_CHOICES = [
        ("wrong_reqs", "Wrong Requisites"),
        ("red_scr", "Red Screen"),
    ]

    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)

    creation_date = models.DateTimeField(default=timezone.now, editable=False)
    first_creation_date = models.DateTimeField(default=timezone.now, editable=False)

    status = models.ForeignKey(to=OutOrderStatus, on_delete=models.SET_NULL, null=True)
    rejection_reason = models.CharField(max_length=10, choices=REJECTION_CHOICES, null=True, blank=True)

    completion_date = models.DateTimeField(null=True)
    updated_date = models.DateTimeField(null=True)

    amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    usd_amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    recalculated_amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32,
                                              decimal_places=2)

    solution = models.ForeignKey(to=MerchantSolution, on_delete=models.CASCADE)

    payment_details = models.ForeignKey(to=PaymentDetails, on_delete=models.SET_NULL, null=True, related_name="outorders")

    destination_details = models.JSONField(default=dict)

    merchant_order_id = models.CharField(max_length=255, default="")

    pic = models.URLField()
    previous_orders = models.ManyToManyField(to='self')

    merchant_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    trader_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    agent_fee = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)

    recalculated = models.BooleanField(default=False)

    auto_closed = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    pdf_sent = models.BooleanField(default=False)
    pdf_comment = models.CharField(max_length=32)
    sms = models.ForeignKey(to=SMS, null=True, blank=True, on_delete=models.SET_NULL, related_name="outorder")

    @classmethod
    def create(cls, amount: float, solution: MerchantSolution, details: dict, merchant_order_id: str = "", time=timezone.now(), excluded_orders=None):
        details_correct = check_details(solution.payment_system, details)
        amount = Decimal.from_float(amount) if isinstance(amount, float) else amount

        if not details_correct:
            return ValidationError({"error": "Wrong details format!"})

        if excluded_orders is not None:
            excluded = [order.payment_details.group.trader for order in excluded_orders]
        else:
            excluded = None

        chosen_detail, usd_amount, success = choose_trader_out(
            amount, solution.payment_system, solution.traffic, excluded, merchant=solution.merchant,
        )

        if not success:
            status = OutOrderStatus.objects.get(name="Cannot process")
            order_obj = cls(status=status, amount=amount, usd_amount=usd_amount,
                            solution=solution,
                            payment_details=None, destination_details=details,
                            merchant_order_id=merchant_order_id, agent_fee=Decimal(0))
            order_obj.save()
            return order_obj

        trader = chosen_detail.group.trader
        from merchant.kzt_settlement import (
            merchant_available_balance,
            uses_melbet_kzt_settlement,
        )

        if uses_melbet_kzt_settlement(solution.merchant, solution.payment_system):
            for_merchant, for_trader, for_platform = calculate_fees(amount, solution, trader, direction="out")
            merchant_fee = for_merchant - amount
            trader_fee = for_trader - amount
            merchant_bal = merchant_available_balance(solution.merchant)
            from merchant.kzt_settlement import balance_allows_negative_ledger

            kzt_insufficient = (
                merchant_bal.amount < for_merchant
                and not balance_allows_negative_ledger(merchant_bal)
            )
            if kzt_insufficient or time > solution.payment_system.constrain_time_out + timezone.now():
                status = OutOrderStatus.objects.get(name="Cannot process")
                order_obj = cls(status=status, amount=amount, usd_amount=usd_amount,
                                solution=solution,
                                payment_details=None, destination_details=details,
                                merchant_order_id=merchant_order_id, agent_fee=Decimal(0))
                order_obj.save()
                return order_obj
        else:
            for_merchant, for_trader, for_platform = calculate_fees(usd_amount, solution, trader, direction="out")
            merchant_fee = for_merchant - usd_amount
            trader_fee = for_trader - usd_amount

            if solution.merchant.balance.amount < for_merchant or time > solution.payment_system.constrain_time_out + timezone.now():
                status = OutOrderStatus.objects.get(name="Cannot process")
                order_obj = cls(status=status, amount=amount, usd_amount=usd_amount,
                                solution=solution,
                                payment_details=None, destination_details=details,
                                merchant_order_id=merchant_order_id, agent_fee=Decimal(0))
                order_obj.save()
                return order_obj

        status = OutOrderStatus.objects.get(name="New")
        order_obj = cls(status=status, amount=amount, usd_amount=usd_amount,
                        payment_details=chosen_detail, solution=solution, destination_details=details,
                        merchant_order_id=merchant_order_id, first_creation_date=time, merchant_fee=merchant_fee, trader_fee=trader_fee, agent_fee=Decimal(0))

        order_obj.save()

        group = PaymentDetailsGroup.objects.select_for_update().get(id=chosen_detail.group.id)
        group.current_out_volume += amount
        group.updated_at = timezone.now()
        group.save()

        order_obj.freeze("New out-order received")

        if excluded_orders is not None:
            for order in excluded_orders:
                order_obj.previous_orders.add(order)
            order_obj.save()

        return order_obj

    def freeze(self, comment=""):
        transaction_type = TransactionType.objects.get(name="Freeze")
        from merchant.kzt_settlement import (
            merchant_available_balance,
            merchant_frozen_balance,
            out_order_freeze_kzt,
            uses_melbet_kzt_settlement,
        )

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            for_merchant = out_order_freeze_kzt(self)
            Transaction.create(
                _from=merchant_available_balance(self.solution.merchant),
                _to=merchant_frozen_balance(self.solution.merchant),
                value=for_merchant,
                _transaction_type=transaction_type,
                _linked_out_order=self,
                _comment=comment,
            )
        else:
            for_merchant = self.usd_amount + self.merchant_fee
            Transaction.create(_from=self.solution.merchant.balance, _to=self.solution.merchant.frozen_balance,
                               value=for_merchant, _transaction_type=transaction_type,
                               _linked_out_order=self,
                               _comment=comment)

    def unfreeze(self, comment=""):
        transaction_type_2 = TransactionType.objects.get(name="Deposit")
        from merchant.kzt_settlement import (
            merchant_available_balance,
            merchant_frozen_balance,
            out_order_freeze_kzt,
            uses_melbet_kzt_settlement,
        )

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            for_merchant = out_order_freeze_kzt(self)
            Transaction.create(
                _from=merchant_frozen_balance(self.solution.merchant),
                _to=merchant_available_balance(self.solution.merchant),
                value=for_merchant,
                _transaction_type=transaction_type_2,
                _linked_out_order=self,
                _comment=comment,
            )
        else:
            for_merchant = self.usd_amount + self.merchant_fee
            Transaction.create(_from=self.solution.merchant.frozen_balance,
                               _to=self.solution.merchant.balance,
                               value=for_merchant, _transaction_type=transaction_type_2,
                               _linked_out_order=self, _comment=comment)

    def decrease_current_volume(self):
        group = PaymentDetailsGroup.objects.select_for_update().get(id=self.payment_details.group.id)
        if self.creation_date.timestamp() // SYSTEM_INTERVAL_VALUE == int(timezone.now().timestamp()) // SYSTEM_INTERVAL_VALUE:
            group.current_out_volume -= self.amount
            group.updated_at = timezone.now()
            group.save()

    def complete(self):
        status = OutOrderStatus.objects.get(name="Completed")
        self.status = status
        self.updated_date = timezone.now()
        self.completion_date = timezone.now()

        aggregator_balance = Balance.objects.get(type=2)
        transaction_type_1 = TransactionType.objects.get(name="Charge")
        transaction_type_2 = TransactionType.objects.get(name="Deposit")

        trader = self.payment_details.group.trader
        merchant = self.solution.merchant

        from merchant.kzt_settlement import (
            merchant_frozen_balance,
            out_order_freeze_kzt,
            uses_melbet_kzt_settlement,
        )

        if uses_melbet_kzt_settlement(merchant, self.solution.payment_system):
            for_merchant = out_order_freeze_kzt(self)
            for_trader = self.usd_amount + self.trader_fee
            frozen_kzt = merchant_frozen_balance(merchant)
        else:
            for_merchant, for_trader = self.usd_amount + self.merchant_fee, self.usd_amount + self.trader_fee
            frozen_kzt = merchant.frozen_balance

        to_aggregator = Transaction.create(_from=frozen_kzt, _to=aggregator_balance,
                                           value=for_merchant, _transaction_type=transaction_type_1,
                                           _linked_out_order=self, _comment="Out-order completed")

        unfreeze = Transaction.create(_from=aggregator_balance, _to=trader.balance_usdt, value=for_trader, _transaction_type=transaction_type_2, _linked_out_order=self, _comment="Out-order completed")

        self.save()

        if trader.team.teamlead is not None:
            teamlead_share = self.trader_fee * trader.team.teamlead_percentage / Decimal(100)
            from_trader_to_teamlead = Transaction.create(_from=trader.balance_usdt, _to=trader.team.teamlead.balance,
                                                         value=teamlead_share, _transaction_type=transaction_type_1,
                                                         _linked_out_order=self, _comment="Teamlead commission")

        OutOrderStatusChange.create(order=self, status=status)

    def money_sent(self):
        if self.status.name != "New":
            raise ValidationError({'details': 'Wrong method is used. This method is for changing status from "New" to "Money sent by trader"'})
        status = OutOrderStatus.objects.get(name="Money sent by trader")
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        OutOrderStatusChange.create(order=self, status=status)

    def auto_sms(self, sms, balance=None):
        self.sms_sent = True
        self.sms = sms
        self.save()

        if balance is not None:
            self.payment_details.update_balance(Decimal(balance))

        if (self.status.name == "Money sent by trader" or self.status.name == "New") and self.pdf_sent:
            self.complete()

        return "Success"

    def add_pdf(self, pdf_url, success, comment):
        if self.status.name != "Money sent by trader" and self.status.name != "New":
            raise ValidationError({"error": f"Current status is {self.status.name}"})
        self.pic = pdf_url

        if not success:
            manual_check = OutOrderStatus.objects.get(name='Manual check')
            self.status = manual_check
            self.pdf_comment = comment
            self.pdf_sent = True
            self.save()
            return

        self.pdf_sent = True
        self.save()

        if self.sms_sent:
            self.complete()

        return

    def arbitrage(self):
        if self.status.name != "Completed":
            raise ValidationError({
                'details': 'Wrong method is used. This method is for changing status from "Completed" to "Arbitrage"'})

        status = OutOrderStatus.objects.filter(name="Arbitrage").first()
        arbitrage_count = OutOrderStatusChange.objects.filter(status=status, order=self).count()

        if arbitrage_count >= ARBITRAGE_LIMIT:
            raise ValidationError({'details': 'Arbitrage limit exceeded for this order'})

        trader = self.payment_details.group.trader

        transaction_type = TransactionType.objects.get(name="Freeze")

        aggregator_balance = Balance.objects.get(type=2)

        from merchant.kzt_settlement import (
            merchant_available_balance,
            merchant_frozen_balance,
            out_order_freeze_kzt,
            uses_melbet_kzt_settlement,
        )

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            for_merchant = out_order_freeze_kzt(self)
            for_trader = self.usd_amount + self.trader_fee
            merchant_fr = merchant_frozen_balance(self.solution.merchant)
        else:
            for_merchant, for_trader = self.usd_amount + self.merchant_fee, self.usd_amount + self.trader_fee
            merchant_bal = self.solution.merchant.balance
            merchant_fr = self.solution.merchant.frozen_balance

        Transaction.create(_from=trader.balance_usdt, _to=aggregator_balance, value=for_trader, _transaction_type=transaction_type, _linked_out_order=self, _comment="Out-order arbitrage")
        Transaction.create(_from=aggregator_balance, _to=merchant_fr, value=for_merchant,
                           _transaction_type=transaction_type, _linked_out_order=self, _comment="Out-order arbitrage")

        self.payment_details.group.status = 4
        self.payment_details.group.save()
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        OutOrderStatusChange.create(order=self, status=status)

    def deal_expired(self):
        if self.status.name != "New":
            raise ValidationError({
                'details': 'Wrong method is used. This method is for changing status from "New" to "Expired"'})
        status = OutOrderStatus.objects.get(name="Expired")
        self.status = status
        self.updated_date = timezone.now()
        self.save()

        self.unfreeze("Out-order expired")

        self.decrease_current_volume()

        excluded = [order for order in self.previous_orders.all()] if self.previous_orders.all().exists() else []

        excluded.append(self)

        new_instance = self.create(float(self.amount), self.solution, self.destination_details, self.merchant_order_id, self.first_creation_date, excluded_orders=excluded)

        new_instance.previous_orders.add(self)
        new_instance.save()

        pay_out_obj = self.pay_out.first()
        OutOrderStatusChange.create(order=self, status=status)

        pay_out_obj.order = new_instance
        pay_out_obj.save()

        if new_instance.status.name == "Cannot process":
            pay_out_obj.failed()

    def complete_after_arbitrage(self):
        if self.status.name != "Recalculation" and self.status.name != "Manual check":
            raise ValidationError({"error": "Wrong status"})
        self.complete()

    def cannot_process(self, reason):
        if self.status.name != "New":
            raise ValidationError({
                'details': 'Wrong method is used. This method is for changing status from "New" to "Cannot process"'})
        status = OutOrderStatus.objects.get(name="Cannot process")
        self.rejection_reason = reason
        self.status = status
        self.updated_date = timezone.now()
        self.save()

        self.unfreeze("Out-order cannot be processed")
        self.decrease_current_volume()

        OutOrderStatusChange.create(order=self, status=status)

        if reason in ["wrong_reqs"]:
            return

        # If the order is rejected due to other reasons, we move it along cascade

        excluded = [order for order in self.previous_orders.all()] if self.previous_orders.all().exists() else None

        if excluded is not None:
            excluded.append(self)
        else:
            excluded = [self]

        new_instance = self.create(float(self.amount), self.solution, self.destination_details, self.merchant_order_id,
                                   self.first_creation_date, excluded_orders=excluded)

        new_instance.previous_orders.add(self)
        new_instance.save()

        pay_out_obj = self.pay_out.first()

        pay_out_obj.order = new_instance
        pay_out_obj.save()

        if new_instance.status.name == "Cannot process":
            pay_out_obj.failed()

    def complete_after_money_sent(self):
        if self.status.name not in ["Money sent by trader", "New", "Arbitrage"]:
            raise ValidationError({
                'details': 'Wrong method is used. This method is for changing status from "Money sent by trader" to "Completed"'})
        self.complete()

    def cancel_support(self):
        if self.status.name == "Completed":
            transaction_type_1 = TransactionType.objects.get(name="Charge")
            transaction_type_2 = TransactionType.objects.get(name="Deposit")
            aggregator_balance = Balance.objects.get(type=2)
            trader = self.payment_details.group.trader

            if trader.team.teamlead is not None:
                teamlead_share = self.trader_fee * trader.team.teamlead_percentage / Decimal(100)
                from_teamlead_to_trader = Transaction.create(_from=trader.team.teamlead.balance,
                                                             _to=trader.balance_usdt,
                                                             value=teamlead_share, _transaction_type=transaction_type_1,
                                                             _linked_out_order=self, _comment="Order cancelled")

            Transaction.create(_from=trader.balance_usdt, _to=aggregator_balance,
                               value=self.usd_amount + self.trader_fee, _transaction_type=transaction_type_1,
                               _linked_out_order=self, _comment="Order cancelled")

            from merchant.kzt_settlement import (
                merchant_available_balance,
                out_order_freeze_kzt,
                uses_melbet_kzt_settlement,
            )

            if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
                refund = out_order_freeze_kzt(self)
                merchant_bal = merchant_available_balance(self.solution.merchant)
            else:
                refund = self.usd_amount + self.merchant_fee
                merchant_bal = self.solution.merchant.balance

            Transaction.create(_from=aggregator_balance, _to=merchant_bal,
                               value=refund, _transaction_type=transaction_type_2,
                               _linked_out_order=self, _comment="Order cancelled")

            status = OutOrderStatus.objects.get(name="Cancelled by support")
            self.status = status
            self.updated_date = timezone.now()
            self.save()
            OutOrderStatusChange.create(order=self, status=status)
            return

        if self.status.name != "Manual check" and self.status.name != "Recalculation":
            raise ValidationError({'error': 'Wrong status."'})
        status = OutOrderStatus.objects.get(name="Cancelled by support")
        self.status = status
        self.updated_date = timezone.now()
        self.save()

        self.unfreeze("Cancelled by support")
        self.decrease_current_volume()

        OutOrderStatusChange.create(order=self, status=status)

    def reset(self):
        if self.status.name != "Manual check":
            raise ValidationError({'error': 'Wrong status."'})

        status = OutOrderStatus.objects.get(name="New")
        self.status = status
        self.pdf_sent = False
        self.creation_date = timezone.now()
        self.pdf_comment = ""
        self.save()
        OutOrderStatusChange.create(order=self, status=status)

    def cancel_after_arbitrage(self):
        if self.status.name != "Arbitrage":
            raise ValidationError({
                'details': 'Wrong method is used. This method is for changing status from "Arbitrage" to "Cancelled by support"'})
        status = OutOrderStatus.objects.get(name="Cancelled by support")
        self.status = status
        self.updated_date = timezone.now()
        self.save()

        self.unfreeze("Cancelled by support")
        self.decrease_current_volume()

        OutOrderStatusChange.create(order=self, status=status)

    def trader_recalculation(self, new_amount: Decimal):
        if self.status.name != "New":
            raise ValidationError({'details': 'Cannot send to recalculation'})

        status = OutOrderStatus.objects.get(name="Recalculation")
        self.status = status
        self.updated_date = timezone.now()
        self.recalculated_amount = new_amount
        self.save()
        OutOrderStatusChange.create(order=self, status=status)

    def recalculate(self, new_amount: Decimal):
        if self.status.name != "Recalculation":
            raise ValidationError({
                'details': 'Cannot recalculate not completed order'})

        new_usd_amount = new_amount / self.solution.payment_system.get_rate()
        from merchant.kzt_settlement import merchant_fee_in_kzt, uses_melbet_kzt_settlement

        if uses_melbet_kzt_settlement(self.solution.merchant, self.solution.payment_system):
            new_merchant_fee = merchant_fee_in_kzt(new_amount, self.solution.mdr_out)
        else:
            new_merchant_fee = self.solution.mdr_out * new_usd_amount / Decimal(100)
        new_trader_fee = self.payment_details.group.trader.team.rate_out * new_usd_amount / Decimal(100)

        self.unfreeze("Recalculation")

        self.amount = new_amount
        self.usd_amount = new_usd_amount
        self.merchant_fee = new_merchant_fee
        self.trader_fee = new_trader_fee
        self.recalculated = True
        self.save()

        self.freeze("Recalculation")
        self.pay_out.get().recalculate(new_amount)
        self.complete()

    def manual_check(self):
        status = OutOrderStatus.objects.get(name="Manual check")
        self.status = status
        self.updated_date = timezone.now()
        self.save()
        OutOrderStatusChange.create(self, status=status)


class OutOrderStatusChange(models.Model):
    status = models.ForeignKey(to=OutOrderStatus, on_delete=models.DO_NOTHING, related_name="change")
    order = models.ForeignKey(to=OutOrder, on_delete=models.CASCADE, related_name="status_change")
    timedelta = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    @classmethod
    def create(cls, order: OutOrder, status: OutOrderStatus):
        last_change = cls.objects.filter(order=order)

        if not last_change.exists():
            timedelta = (timezone.now() - order.creation_date).total_seconds()
        else:
            last_change_obj = last_change.latest('created_at')
            timedelta = (timezone.now() - last_change_obj.created_at).total_seconds()

        status_change_obj = cls(status=status, order=order, timedelta=timedelta)
        status_change_obj.save()

        if not order.pay_out.exists():
            return status_change_obj

        if status.name == "Completed":
            order.pay_out.get().success()
        elif status.name == "Expired":
            pass
        elif status.name in ["Money sent by trader", "Arbitrage", "New", "Recalculation", "Manual check"]:
            order.pay_out.get().in_progress()
        else:
            order.pay_out.get().failed()

        return status_change_obj


class Transaction(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    from_balance = models.ForeignKey(to=Balance, null=True, on_delete=models.SET_NULL,
                                     related_name='outcoming_transactions', editable=False)
    to_balance = models.ForeignKey(to=Balance, null=True, on_delete=models.SET_NULL,
                                   related_name='incoming_transactions', editable=False)
    transaction_type = models.ForeignKey(to=TransactionType, null=True, on_delete=models.SET_NULL, editable=False)
    linked_in_order = models.ForeignKey(to=InOrder, null=True, on_delete=models.SET_NULL, editable=False)
    linked_out_order = models.ForeignKey(to=OutOrder, null=True, on_delete=models.SET_NULL, editable=False)
    creation_date = models.DateTimeField(default=timezone.now, editable=False)
    comment = models.CharField(default="-", max_length=256, editable=False)
    value = models.DecimalField(default=0, validators=[MinValueValidator(0)], editable=False, max_digits=32, decimal_places=2)

    @classmethod
    def create(cls, _from: Balance, _to: Balance, value: Decimal, _transaction_type=None, _linked_in_order=None,
               _linked_out_order=None, _comment="-"):

        from_balance = Balance.objects.select_for_update().get(id=_from.id)
        to_balance = Balance.objects.select_for_update().get(id=_to.id)

        # from_balance = Balance.objects.get(id=_from.id)
        # to_balance = Balance.objects.get(id=_to.id)

        if from_balance.type != 3 and from_balance.amount < value and _comment != "Crypto deposit":
            from merchant.kzt_settlement import balance_allows_negative_ledger

            if not balance_allows_negative_ledger(from_balance):
                raise ValidationError({'details': 'Not enough funds to transfer money'})

        from_balance.amount -= value
        to_balance.amount += value

        from_balance.save()
        to_balance.save()

        transaction_obj = cls(from_balance=_from, to_balance=_to, transaction_type=_transaction_type,
                              linked_in_order=_linked_in_order, linked_out_order=_linked_out_order, comment=_comment, value=value)
        transaction_obj.save()

        return transaction_obj

    def is_incoming(self, user_balance):
        return self.to_balance == user_balance

    def get_from(self):
        if self.from_balance.type == 3:
            return "Blockchain"
        elif self.from_balance.type == 2:
            return "Platform's balance"
        elif self.from_balance.type == 1:
            if self.from_balance.trader_frozen.exists():
                name = self.from_balance.trader_frozen.get().user.username
            elif self.from_balance.teamlead.exists():
                name = self.from_balance.teamlead.get().user.username
            else:
                name = self.from_balance.frozen_merchant.get().user.username
            return f"{name}-frozen"
        else:
            if self.from_balance.available.exists():
                name = self.from_balance.available.get().user.username
            elif self.from_balance.teamlead.exists():
                name = self.from_balance.teamlead.get().user.username
            else:
                name = self.from_balance.available_merchant.get().user.username
            return f"{name}-available"

    def get_to(self):
        if self.to_balance.type == 3:
            return "Blockchain"
        elif self.to_balance.type == 2:
            return "Platform's balance"
        elif self.to_balance.type == 1:
            if self.to_balance.trader_frozen.exists():
                name = self.to_balance.trader_frozen.get().user.username
            elif self.from_balance.teamlead.exists():
                name = self.from_balance.teamlead.get().user.username
            else:
                name = self.to_balance.frozen_merchant.get().user.username
            return f"{name}-frozen"
        else:
            if self.to_balance.available_merchant_kzt.exists():
                name = self.to_balance.available_merchant_kzt.get().user.username
                return f"{name}-kzt-available"
            if self.to_balance.frozen_merchant_kzt.exists():
                name = self.to_balance.frozen_merchant_kzt.get().user.username
                return f"{name}-kzt-frozen"
            if self.to_balance.available.exists():
                name = self.to_balance.available.get().user.username
            elif self.to_balance.available_merchant.exists():
                name = self.to_balance.available_merchant.get().user.username
            elif self.from_balance.teamlead.exists():
                name = self.from_balance.teamlead.get().user.username
            else:
                name = self.to_balance.teamlead.get().user.username
            return f"{name}-available"


class WithdrawalRequest(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    status = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(2)])  # 0 -requested, 1 - approved, 2 - rejected
    amount = models.DecimalField(default=0, validators=[MinValueValidator(0)], max_digits=32, decimal_places=2)
    balance = models.ForeignKey(to=Balance, on_delete=models.SET_NULL, null=True)
    address_to = models.CharField(max_length=50)
    comment = models.CharField(max_length=256)
    from_user = models.ForeignKey(to=User, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(default=timezone.now, editable=False)

    @classmethod
    def create(cls, amount, _from: Balance, address_to, from_user: User):
        if _from.type != 0:
            raise ValidationError({'details': 'Cannot withdraw from this balance'})
        if _from.amount < amount:
            raise ValidationError({'details': 'Not enough funds to withdraw'})
        if 0 >= amount:
            raise ValidationError({'details': 'Amount should be more than zero!'})
        if hasattr(from_user, 'merchant'):
            frozen_balance = from_user.merchant.frozen_balance
        else:
            frozen_balance = from_user.trader.frozen_balance_usdt

        tx_type = TransactionType.objects.get(name="Freeze")

        Transaction.create(_from=_from, _to=frozen_balance, value=amount, _transaction_type=tx_type, _comment="Freeze before the withdrawal")
        withdraw_req = cls(status=0, amount=amount, balance=_from, address_to=address_to, comment="", from_user=from_user)
        withdraw_req.save()
        return withdraw_req

    def approve(self, withdraw_tx_id):
        if self.status != 0:
            raise ValidationError({'details': 'Wrong status'})

        transfer_balance = Balance.objects.get(type=3)
        tx_type = TransactionType.objects.get(name="Withdrawal")

        if hasattr(self.from_user, 'merchant'):
            frozen_balance = self.from_user.merchant.frozen_balance
        else:
            frozen_balance = self.from_user.trader.frozen_balance_usdt

        if self.amount > frozen_balance.amount:
            raise ValidationError({'details': 'Not enough funds to withdraw'})

        Transaction.create(_from=frozen_balance, _to=transfer_balance, value=self.amount, _transaction_type=tx_type,
                           _comment=withdraw_tx_id)
        self.status = 1
        self.comment = withdraw_tx_id
        self.save()

    def reject(self, comment):
        if self.status != 0:
            raise ValidationError({'details': 'Wrong status'})
        tx_type = TransactionType.objects.get(name="Deposit")

        if hasattr(self.from_user, 'merchant'):
            frozen_balance = self.from_user.merchant.frozen_balance
        else:
            frozen_balance = self.from_user.trader.frozen_balance_usdt

        Transaction.create(_from=frozen_balance, _to=self.balance, value=self.amount, _transaction_type=tx_type,
                           _comment="Withdrawal request declined")

        self.status = 2
        self.comment = comment
        self.save()


class Address(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    address_public = models.CharField(default="", max_length=42)
    balance = models.ForeignKey(to=Balance, on_delete=models.CASCADE, related_name="address")

    def update_balance(self, new_balance):
        from merchant.models import Merchant
        from merchant.kzt_settlement import credit_melbet_crypto_deposit, is_melbet_merchant

        merchant = Merchant.objects.filter(balance_id=self.balance_id).first()
        if merchant is not None and is_melbet_merchant(merchant):
            return credit_melbet_crypto_deposit(merchant, Decimal(str(new_balance)))
        _from = Balance.objects.get(type=3)
        _type = TransactionType.objects.get(name="Deposit")
        Transaction.create(_from, self.balance, _transaction_type=_type, value=new_balance, _comment="Crypto deposit")
        return True
