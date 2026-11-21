"""Создать агентов и начислить 0.2% с completed in одним платежом (не по ордеру).

  APPLY=1 AGENT_PASSWORD=... BACKFILL=1
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum

from basics.models import Balance, Language
from merchant.models import Agent, Merchant
from trade.models import InOrder, Transaction, TransactionType

PLAN = (
    ("L_payments", "melbet"),
    ("CardsMG", "pandapay"),
)
PCT = Decimal("0.002")


def ensure_agents(apply_flag: bool, password: str):
    lang = Language.objects.filter(name="Russian").first()
    for agent_name, merchant_name in PLAN:
        merchant = Merchant.objects.filter(user__username__iexact=merchant_name).first()
        agent = Agent.objects.filter(user__username=agent_name).first()
        print(f"{agent_name} exists={bool(agent)} merchant={merchant_name} exists={bool(merchant)}", flush=True)
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
            print(f"+ agent {agent_name}", flush=True)
        if merchant is not None and merchant.agent_id != agent.id:
            merchant.agent = agent
            merchant.save(update_fields=["agent"])
            print(f"+ {merchant_name} → {agent_name}", flush=True)


def backfill(apply_flag: bool):
    chain = Balance.objects.get(type=3)
    deposit = TransactionType.objects.get(name="Deposit")
    for agent_name, merchant_name in PLAN:
        merchant = Merchant.objects.filter(user__username__iexact=merchant_name).select_related(
            "agent", "agent__balance"
        ).first()
        if merchant is None:
            print(f"skip {merchant_name}: no merchant", flush=True)
            continue
        usd = InOrder.objects.filter(
            solution__merchant=merchant, status__name="Completed"
        ).aggregate(s=Sum("usd_amount"))["s"] or Decimal("0")
        gross = (Decimal(str(usd)) * PCT).quantize(Decimal("0.01"))
        agent = merchant.agent
        already = Decimal("0")
        if agent and agent.balance_id:
            already = Transaction.objects.filter(
                to_balance_id=agent.balance_id,
                comment__startswith="Agent commission",
            ).aggregate(s=Sum("value"))["s"] or Decimal("0")
            already = Decimal(str(already))
        delta = gross - already
        if delta < 0:
            delta = Decimal("0")
        print(
            f"{agent_name}/{merchant_name}: completed_usd={usd} gross_0.2%={gross} "
            f"already={already} to_add={delta}",
            flush=True,
        )
        if not apply_flag or delta <= 0 or agent is None or agent.balance_id is None:
            continue
        with transaction.atomic():
            Transaction.create(
                _from=chain,
                _to=agent.balance,
                value=delta,
                _transaction_type=deposit,
                _comment="Agent commission backfill",
            )
        agent.balance.refresh_from_db()
        print(f"  applied balance={agent.balance.amount}", flush=True)


def run():
    apply_flag = os.environ.get("APPLY", "").strip() in ("1", "true", "yes")
    backfill_flag = os.environ.get("BACKFILL", "").strip() in ("1", "true", "yes")
    password = os.environ.get("AGENT_PASSWORD", "").strip()
    ensure_agents(apply_flag, password)
    if backfill_flag or apply_flag:
        backfill(apply_flag)
    if not apply_flag:
        print("DRY-RUN. APPLY=1 AGENT_PASSWORD=... BACKFILL=1", flush=True)


run()
