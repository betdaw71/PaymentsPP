"""Касса = активы − пассивы. День = MDR + FX-спред − комиссия PSP − агент − расходы бота."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
ZERO = Decimal("0.00")
DEC = DecimalField(max_digits=32, decimal_places=2)


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def money_str(raw) -> str:
    return str(money(raw))


def _bal(obj, field: str) -> Decimal:
    rel = getattr(obj, field, None) if obj is not None else None
    if rel is None:
        return ZERO
    return money(getattr(rel, "amount", 0))


def c2ckzt_usdt_rate() -> Decimal:
    from basics.models import PaymentSystem

    ps = PaymentSystem.objects.filter(name="C2CKZT").only("usdt_exchange_rate").first()
    rate = money(getattr(ps, "usdt_exchange_rate", 0) if ps is not None else 0)
    return rate if rate > 0 else Decimal("1")


def kzt_to_usd(kzt, *, rate=None) -> Decimal:
    fx = c2ckzt_usdt_rate() if rate is None else money(rate)
    if fx <= 0:
        return ZERO
    return money(money(kzt) / fx)


def merchant_usdt_net(available, frozen, rolling) -> Decimal:
    """Mostbet: available − rolling. >0 мы должны мерчу, <0 предоплата нам."""
    return money(money(available) + money(frozen) - money(rolling))


def psp_held_usdt(available, frozen=0) -> Decimal:
    """Баланс в ЛК PSP: минус = деньги на сайте провайдера, их можно вывести. В кассу — модуль."""
    return money(abs(money(available)))


def psp_deposit_owed(deposit, available) -> Decimal:
    """Неизрасходованная предоплата в ЛК PSP (остаток), не «депозит − баланс».

    PayPlat 12000, в ЛК 4146.93 → в пассив 4146.93 (деньги ещё у провайдера).
    Уже прогнанные 7853 в долг не ставим: они ушли в оборот.
    """
    dep = money(deposit)
    avail = money(available)
    if dep <= 0 or avail <= 0:
        return ZERO
    return money(min(dep, avail))


def fetch_platform_wallet_usdt(address=None) -> tuple[Decimal, str]:
    """USDT TRC-20 на кошельке площадки через TronGrid. Сбой сети → 0, кассу не роняем."""
    from django.conf import settings

    wallet = (address or getattr(settings, "CASH_REGISTER_TRC20_WALLET", "") or "").strip()
    if not wallet:
        return ZERO, ""
    contract = (getattr(settings, "USDT_TRC20_CONTRACT", None) or "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t").strip()
    headers = {}
    api_key = (getattr(settings, "TRONGRID_API_KEY", None) or "").strip()
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    try:
        import requests

        response = requests.get(
            f"https://api.trongrid.io/v1/accounts/{wallet}",
            headers=headers,
            timeout=12,
        )
        response.raise_for_status()
        rows = (response.json() or {}).get("data") or []
        account = rows[0] if rows else {}
        for item in account.get("trc20") or []:
            if not isinstance(item, dict):
                continue
            raw = item.get(contract)
            if raw is None:
                continue
            return money(Decimal(str(raw)) / Decimal("1000000")), wallet
    except Exception:
        logger.warning("cash register wallet fetch failed for %s", wallet, exc_info=True)
    return ZERO, wallet


def fx_spread(usd_amount, psp_usd_amount) -> Decimal:
    merchant_usd = money(usd_amount)
    psp_usd = money(psp_usd_amount)
    if psp_usd <= 0:
        psp_usd = merchant_usd
    return money(psp_usd - merchant_usd)


def payin_pnl(*, merchant_fee, trader_fee, agent_fee, usd_amount, psp_usd_amount) -> Decimal:
    return money(
        money(merchant_fee)
        + fx_spread(usd_amount, psp_usd_amount)
        - money(trader_fee)
        - money(agent_fee)
    )


def payout_pnl(*, merchant_fee, trader_fee) -> Decimal:
    return money(money(merchant_fee) - money(trader_fee))


def moscow_bounds(now=None):
    current = (now or timezone.now()).astimezone(MSK)
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return current, day_start, month_start


def _psp_effective_usd():
    return Case(
        When(psp_usd_amount__gt=0, then=F("psp_usd_amount")),
        default=F("usd_amount"),
        output_field=DEC,
    )


def _period_pnl(start: datetime, end: datetime) -> dict:
    from basics.models import PlatformExpense
    from trade.models import InOrder, OutOrder

    in_agg = InOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    ).aggregate(
        merchant_fee=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        agent_fee=Coalesce(Sum("agent_fee"), Value(ZERO, output_field=DEC)),
        fx_spread=Coalesce(
            Sum(ExpressionWrapper(_psp_effective_usd() - F("usd_amount"), output_field=DEC)),
            Value(ZERO, output_field=DEC),
        ),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )
    out_agg = OutOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=start,
        completion_date__lt=end,
    ).aggregate(
        merchant_fee=Coalesce(Sum("merchant_fee"), Value(ZERO, output_field=DEC)),
        trader_fee=Coalesce(Sum("trader_fee"), Value(ZERO, output_field=DEC)),
        turnover=Coalesce(Sum("usd_amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )
    expenses = PlatformExpense.objects.filter(created_at__gte=start, created_at__lt=end).aggregate(
        total=Coalesce(Sum("amount"), Value(ZERO, output_field=DEC)),
        count=Count("id"),
    )
    payin_mdr = money(in_agg["merchant_fee"])
    payin_fx = money(in_agg["fx_spread"])
    payin_trader = money(in_agg["trader_fee"])
    agent = money(in_agg["agent_fee"])
    payout_mdr = money(out_agg["merchant_fee"])
    payout_trader = money(out_agg["trader_fee"])
    expense_total = money(expenses["total"])
    net = money(
        payin_mdr
        + payin_fx
        + payout_mdr
        - payin_trader
        - payout_trader
        - agent
        - expense_total
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "orders_in": in_agg["count"],
        "orders_out": out_agg["count"],
        "turnover_in": money_str(in_agg["turnover"]),
        "turnover_out": money_str(out_agg["turnover"]),
        "payin_mdr": money_str(payin_mdr),
        "payin_fx": money_str(payin_fx),
        "payout_mdr": money_str(payout_mdr),
        "trader_fee": money_str(payin_trader + payout_trader),
        "agent_fee": money_str(agent),
        "expenses": money_str(expense_total),
        "expense_count": expenses["count"],
        "net": money_str(net),
    }


def snapshot(now=None) -> dict:
    from basics.models import TeamLead, Trader
    from merchant.models import Agent, Merchant
    from payments.psp_payin import is_psp_trader

    current, day_start, month_start = moscow_bounds(now)

    psp_rows = []
    trader_rows = []
    psp_deposit_rows = []
    psp_total = ZERO
    trader_total = ZERO
    deposit_total = ZERO
    psp_deposit_owed_total = ZERO
    traders = Trader.objects.select_related("user", "balance_usdt", "frozen_balance_usdt")
    for trader in traders:
        available = _bal(trader, "balance_usdt")
        frozen = _bal(trader, "frozen_balance_usdt")
        row = {
            "username": trader.user.username if trader.user_id else "",
            "available": money_str(available),
            "frozen": money_str(frozen),
            "credit_limit": money_str(trader.credit_limit),
            "working_deposit": money_str(trader.working_deposit),
        }
        deposit_total += money(trader.working_deposit)
        if is_psp_trader(trader):
            held = psp_held_usdt(available, frozen)
            owed = psp_deposit_owed(trader.working_deposit, available)
            if owed > 0:
                held = money(max(held - owed, ZERO))
            row["held"] = money_str(held)
            row["deposit_owed"] = money_str(owed)
            psp_rows.append(row)
            psp_total += held
            if owed > 0:
                psp_deposit_owed_total += owed
                psp_deposit_rows.append({
                    "username": row["username"],
                    "available": money_str(available),
                    "working_deposit": money_str(trader.working_deposit),
                    "net": money_str(owed),
                    "frozen": "0.00",
                    "rolling_reserve": "0.00",
                    "note": "psp_prepaid",
                })
        else:
            trader_rows.append(row)
            trader_total += money(available + frozen)

    from merchant.kzt_settlement import is_melbet_merchant

    merchant_rows = []
    receivable_rows = []
    merchant_total = ZERO
    receivable_total = ZERO
    rolling_total = ZERO
    kzt_rate = c2ckzt_usdt_rate()
    merchants = Merchant.objects.select_related(
        "user",
        "balance",
        "frozen_balance",
        "balance_kzt",
        "frozen_balance_kzt",
        "balance_kgs",
        "frozen_balance_kgs",
    )
    for merchant in merchants:
        available = _bal(merchant, "balance")
        frozen = _bal(merchant, "frozen_balance")
        rolling = money(merchant.rolling_reserve)
        rolling_total += rolling
        username = merchant.user.username if merchant.user_id else ""
        if is_melbet_merchant(merchant):
            kzt = money(_bal(merchant, "balance_kzt") + _bal(merchant, "frozen_balance_kzt"))
            kgs = money(_bal(merchant, "balance_kgs") + _bal(merchant, "frozen_balance_kgs"))
            kzt_usd = kzt_to_usd(kzt, rate=kzt_rate)
            frozen_kzt = money_str(_bal(merchant, "frozen_balance_kzt"))
            # KZT < 0: prepaid/оборот, нам должны (актив). KZT > 0: мы должны Melbet (пассив).
            if kzt_usd < 0:
                owed = money(-kzt_usd)
                receivable_total += owed
                receivable_rows.append({
                    "username": username,
                    "kind": "melbet_kzt",
                    "kzt": money_str(kzt),
                    "kgs": money_str(kgs),
                    "rate": money_str(kzt_rate),
                    "available": money_str(owed),
                    "frozen": frozen_kzt,
                    "rolling_reserve": "0.00",
                    "net": money_str(owed),
                    "note": "melbet_owes_us",
                })
            elif kzt_usd > 0:
                merchant_total += kzt_usd
                merchant_rows.append({
                    "username": username,
                    "available": "0.00",
                    "frozen": "0.00",
                    "rolling_reserve": "0.00",
                    "net": money_str(kzt_usd),
                    "kzt": money_str(kzt),
                    "kzt_usd": money_str(kzt_usd),
                    "note": "we_owe_melbet",
                })
            continue
        net = merchant_usdt_net(available, frozen, rolling)
        row = {
            "username": username,
            "available": money_str(available),
            "frozen": money_str(frozen),
            "rolling_reserve": money_str(rolling),
            "net": money_str(net),
        }
        if net >= 0:
            merchant_total += net
            merchant_rows.append(row)
        else:
            receivable_total += money(-net)
            receivable_rows.append({
                **row,
                "kind": "rolling_prepaid",
                "available": money_str(-net),
                "note": "rolling_gt_available",
            })

    agent_rows = []
    agent_total = ZERO
    for agent in Agent.objects.select_related("user", "balance", "frozen_balance"):
        available = _bal(agent, "balance")
        frozen = _bal(agent, "frozen_balance")
        agent_total += money(available + frozen)
        agent_rows.append({
            "username": agent.user.username if agent.user_id else "",
            "available": money_str(available),
            "frozen": money_str(frozen),
        })

    teamlead_rows = []
    teamlead_total = ZERO
    for teamlead in TeamLead.objects.select_related("user", "balance", "frozen_balance"):
        available = _bal(teamlead, "balance")
        frozen = _bal(teamlead, "frozen_balance")
        teamlead_total += money(available + frozen)
        teamlead_rows.append({
            "username": teamlead.user.username if teamlead.user_id else "",
            "available": money_str(available),
            "frozen": money_str(frozen),
        })

    wallet_usdt, wallet_address = fetch_platform_wallet_usdt()
    wallet_rows = []
    if wallet_address:
        wallet_rows.append({
            "username": "platform_wallet",
            "address": wallet_address,
            "available": money_str(wallet_usdt),
            "kind": "trc20_usdt",
        })

    assets_total = money(psp_total + trader_total + receivable_total + wallet_usdt)
    liabilities_total = money(merchant_total + agent_total + teamlead_total + psp_deposit_owed_total)
    cash = money(assets_total - liabilities_total)
    end = current
    return {
        "as_of": current.isoformat(),
        "timezone": "Europe/Moscow",
        "cash": money_str(cash),
        "kzt_usdt_rate": money_str(kzt_rate),
        "assets": {
            "total": money_str(assets_total),
            "psp_total": money_str(psp_total),
            "traders_total": money_str(trader_total),
            "receivables_total": money_str(receivable_total),
            "wallet_total": money_str(wallet_usdt),
            "psp": sorted(psp_rows, key=lambda row: row["username"]),
            "traders": sorted(trader_rows, key=lambda row: row["username"]),
            "receivables": sorted(receivable_rows, key=lambda row: row["username"]),
            "wallets": wallet_rows,
        },
        "liabilities": {
            "total": money_str(liabilities_total),
            "merchants_total": money_str(merchant_total),
            "agents_total": money_str(agent_total),
            "teamleads_total": money_str(teamlead_total),
            "psp_deposits_total": money_str(psp_deposit_owed_total),
            "merchants": sorted(merchant_rows, key=lambda row: row["username"]),
            "agents": sorted(agent_rows, key=lambda row: row["username"]),
            "teamleads": sorted(teamlead_rows, key=lambda row: row["username"]),
            "psp_deposits": sorted(psp_deposit_rows, key=lambda row: row["username"]),
        },
        "memo": {
            "rolling_reserve": money_str(rolling_total),
            "working_deposit": money_str(deposit_total),
        },
        "pnl": {
            "day": _period_pnl(day_start, end),
            "month": _period_pnl(month_start, end),
        },
    }


def format_telegram(data: dict | None = None) -> str:
    data = data or snapshot()
    day = data["pnl"]["day"]
    month = data["pnl"]["month"]
    return (
        f"Касса {data['cash']} USDT ({data['timezone']})\n"
        f"активы {data['assets']['total']} − пассивы {data['liabilities']['total']}\n"
        f"PSP {data['assets']['psp_total']} (|баланс| на сайте) · "
        f"кошелёк {data['assets'].get('wallet_total', '0.00')} · "
        f"трейдеры {data['assets']['traders_total']} · "
        f"Melbet KZT {data['assets'].get('receivables_total', '0.00')}\n"
        f"мерчи {data['liabilities']['merchants_total']} (net − rolling) · "
        f"депозит PSP {data['liabilities'].get('psp_deposits_total', '0.00')} · "
        f"агенты {data['liabilities']['agents_total']} · "
        f"тимлиды {data['liabilities']['teamleads_total']}\n"
        f"день {day['net']} (MDR {day['payin_mdr']}+{day['payout_mdr']} · FX {day['payin_fx']} · "
        f"PSP {day['trader_fee']} · агент {day['agent_fee']} · расход {day['expenses']})\n"
        f"месяц {month['net']}"
    )
