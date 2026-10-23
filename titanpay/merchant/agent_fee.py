from decimal import Decimal

from merchant.kzt_settlement import uses_melbet_fiat_settlement


def compute_in_order_agent_fee(order) -> Decimal:
    """0.2% of KZT turnover for Melbet fiat; 0.2% of USDT for others. Result in USDT."""
    merchant = getattr(getattr(order, "solution", None), "merchant", None)
    agent = getattr(merchant, "agent", None) if merchant is not None else None
    if agent is None:
        return Decimal("0")
    pct = Decimal(str(agent.commission_percent or 0)) / Decimal("100")
    if pct <= 0:
        return Decimal("0")
    amount = Decimal(str(order.amount or 0))
    usd = Decimal(str(order.usd_amount or 0))
    if uses_melbet_fiat_settlement(merchant, order.solution.payment_system):
        kzt_fee = amount * pct
        if amount <= 0:
            return Decimal("0")
        return (kzt_fee * usd / amount).quantize(Decimal("0.01"))
    return (usd * pct).quantize(Decimal("0.01"))


def accrue_agent_commission(order) -> None:
    from basics.models import Balance
    from trade.models import Transaction, TransactionType

    fee = Decimal(str(getattr(order, "agent_fee", 0) or 0))
    merchant = getattr(getattr(order, "solution", None), "merchant", None)
    agent = getattr(merchant, "agent", None) if merchant is not None else None
    if fee <= 0 or agent is None or agent.balance_id is None:
        return
    chain = Balance.objects.get(type=3)
    deposit = TransactionType.objects.get(name="Deposit")
    Transaction.create(
        _from=chain,
        _to=agent.balance,
        value=fee,
        _transaction_type=deposit,
        _linked_in_order=order,
        _comment="Agent commission",
    )
