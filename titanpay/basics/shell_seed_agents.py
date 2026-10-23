"""Создать агентов и начислить 0.2% с completed in их мерчей.

  APPLY=1 AGENT_PASSWORD=...   создать L_payments / CardsMG и привязать мерчей
  BACKFILL=1                   начислить комиссию по старым Completed (без двойного начисления)
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum

from basics.models import Balance, Language
from merchant.agent_fee import accrue_agent_commission, compute_in_order_agent_fee
from merchant.models import Agent, Merchant
from trade.models import InOrder, Transaction

PLAN = (
    ("L_payments", "melbet"),
    ("CardsMG", "pandapay"),
)


def ensure_agents(apply_flag: bool, password: str) -> None:
    lang = Language.objects.filter(name="Russian").first()
    for agent_name, merchant_name in PLAN:
        merchant = Merchant.objects.filter(user__username__iexact=merchant_name).first()
        agent = Agent.objects.filter(user__username=agent_name).first()
        print(f"{agent_name} exists={bool(agent)} merchant={merchant_name} exists={bool(merchant)}")
        if not apply_flag:
            continue
        if agent is None:
            if not password:
                raise RuntimeError("AGENT_PASSWORD required to create agent")
            user, created = User.objects.get_or_create(username=agent_name)
            if created or not user.has_usable_password():
                user.set_password(password)
                user.save()
            agent = Agent.objects.create(
                user=user,
                balance=Balance.objects.create(type=0, amount=Decimal("0")),
                frozen_balance=Balance.objects.create(type=1, amount=Decimal("0")),
                commission_percent=Decimal("0.20"),
                language=lang,
            )
            print(f"+ agent {agent_name}")
        if merchant is not None and merchant.agent_id != agent.id:
            merchant.agent = agent
            merchant.save(update_fields=["agent"])
            print(f"+ {merchant_name} → {agent_name}")


def backfill(apply_flag: bool) -> None:
    for agent_name, merchant_name in PLAN:
        merchant = Merchant.objects.filter(user__username__iexact=merchant_name).select_related("agent", "agent__balance").first()
        if merchant is None or merchant.agent_id is None:
            print(f"skip backfill {merchant_name}: no agent")
            continue
        agent = merchant.agent
        qs = (
            InOrder.objects.filter(solution__merchant=merchant, status__name="Completed")
            .select_related("solution__merchant__agent", "solution__payment_system")
            .order_by("completion_date")
        )
        done = set(
            Transaction.objects.filter(
                comment="Agent commission",
                to_balance_id=agent.balance_id,
            ).values_list("linked_in_order_id", flat=True)
        )
        todo = 0
        total = Decimal("0")
        for order in qs.iterator(chunk_size=400):
            if order.id in done:
                continue
            fee = compute_in_order_agent_fee(order)
            if fee <= 0:
                continue
            todo += 1
            total += fee
            if not apply_flag:
                continue
            with transaction.atomic():
                order.agent_fee = fee
                order.save(update_fields=["agent_fee"])
                accrue_agent_commission(order)
        agent.balance.refresh_from_db()
        print(
            f"{agent_name}/{merchant_name}: new_orders={todo} new_usdt={total} "
            f"balance={agent.balance.amount if agent.balance else None}"
        )
        paid = Transaction.objects.filter(
            comment="Agent commission", to_balance_id=agent.balance_id
        ).aggregate(s=Sum("value"))["s"] or 0
        print(f"  ledger_commission_sum={paid}")


def run() -> None:
    apply_flag = os.environ.get("APPLY", "").strip() in ("1", "true", "yes")
    backfill_flag = os.environ.get("BACKFILL", "").strip() in ("1", "true", "yes")
    password = os.environ.get("AGENT_PASSWORD", "").strip()
    ensure_agents(apply_flag, password)
    if backfill_flag or apply_flag:
        backfill(apply_flag)
    if not apply_flag:
        print("DRY-RUN. Создать: APPLY=1 AGENT_PASSWORD=...  Начислить: APPLY=1 BACKFILL=1")


if __name__ == "__main__":
    run()
else:
    run()
