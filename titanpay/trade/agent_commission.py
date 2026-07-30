"""Начисление агентской комиссии (% от оборота мерчанта) на баланс TeamLead."""
from decimal import Decimal

AGENT_COMMISSION_COMMENT = "Agent commission"
AGENT_COMMISSION_REVERSAL = "Agent commission reversal"


def calculate_agent_fee(usd_amount: Decimal, percent: Decimal) -> Decimal:
    if usd_amount <= 0 or percent <= 0:
        return Decimal("0.00")
    return (usd_amount * percent / Decimal(100)).quantize(Decimal("0.01"))


def get_active_merchant_agent_assignment(merchant):
    from merchant.models import MerchantAgentAssignment

    return (
        MerchantAgentAssignment.objects.filter(merchant=merchant, is_active=True)
        .select_related("agent", "agent__balance")
        .first()
    )


def merchant_ids_for_agent(teamlead):
    from merchant.models import MerchantAgentAssignment

    return MerchantAgentAssignment.objects.filter(agent=teamlead, is_active=True).values_list(
        "merchant_id", flat=True
    )


def _accrue(order, *, direction: str, linked_field: str) -> None:
    from basics.models import Balance
    from trade.models import Transaction, TransactionType

    assignment = get_active_merchant_agent_assignment(order.solution.merchant)
    if assignment is None or assignment.agent.balance is None:
        order.agent_fee = Decimal("0.00")
        return

    percent = assignment.turnover_percent_in if direction == "in" else assignment.turnover_percent_out
    fee = calculate_agent_fee(order.usd_amount, percent)
    order.agent_fee = fee
    if fee <= 0:
        return

    aggregator_balance = Balance.objects.get(type=2)
    transaction_type_deposit = TransactionType.objects.get(name="Deposit")
    link_kwargs = {linked_field: order}
    Transaction.create(
        _from=aggregator_balance,
        _to=assignment.agent.balance,
        value=fee,
        _transaction_type=transaction_type_deposit,
        _comment=AGENT_COMMISSION_COMMENT,
        **link_kwargs,
    )


def accrue_agent_commission_for_in_order(order) -> None:
    _accrue(order, direction="in", linked_field="_linked_in_order")


def accrue_agent_commission_for_out_order(order) -> None:
    _accrue(order, direction="out", linked_field="_linked_out_order")


def reverse_agent_commission(order, *, linked_filter: dict) -> None:
    from trade.models import Transaction, TransactionType

    if not order.agent_fee or order.agent_fee <= 0:
        return

    txs = Transaction.objects.filter(comment=AGENT_COMMISSION_COMMENT, **linked_filter)
    if not txs.exists():
        order.agent_fee = Decimal("0.00")
        return

    transaction_type_charge = TransactionType.objects.get(name="Charge")
    for tx in txs:
        Transaction.create(
            _from=tx.to_balance,
            _to=tx.from_balance,
            value=tx.value,
            _transaction_type=transaction_type_charge,
            _comment=AGENT_COMMISSION_REVERSAL,
            _linked_in_order=tx.linked_in_order,
            _linked_out_order=tx.linked_out_order,
        )
    order.agent_fee = Decimal("0.00")


def reverse_agent_commission_for_in_order(order) -> None:
    reverse_agent_commission(order, linked_filter={"linked_in_order": order})


def reverse_agent_commission_for_out_order(order) -> None:
    reverse_agent_commission(order, linked_filter={"linked_out_order": order})


def prepare_in_order_recalc_agent(order) -> None:
    reverse_agent_commission_for_in_order(order)


def prepare_out_order_recalc_agent(order) -> None:
    reverse_agent_commission_for_out_order(order)
