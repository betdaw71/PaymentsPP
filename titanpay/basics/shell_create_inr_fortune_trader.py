"""
Django shell: трейдерская команда India (INR) — Fortune Solomon.

Платёжные системы: RTGS (6% in), IMPS (7% in).
Реквизиты: account number → deposit_number, account name → group.owner, IFSC → group.bic.
work_type: by_deposit_number, deposit_number_on: true.

Запуск:
  docker compose exec app python manage.py migrate
  docker compose exec app python manage.py shell < basics/shell_create_inr_fortune_trader.py

Или:
  exec(open("basics/shell_create_inr_fortune_trader.py").read())
  run()
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)
from titanpay.settings import IMPS_NAME, RTGS_NAME

TEAM_NAME = "Fortune Solomon INR"
TRADER_USERNAME = "fortunesolomon566"
TRADER_EMAIL = "fortunesolomon566@gmail.ru"
TRADER_PASSWORD = "ChangeMe_Fortune_INR_1!"
TRAFFIC_NAME = "Standard"

# TraderTeamRates.mdr_in (%), merchant MDR настраивается отдельно в MerchantSolution
PS_RATES = {
    RTGS_NAME: Decimal("6.00"),
    IMPS_NAME: Decimal("7.00"),
}

# Базовая ставка команды (fallback; фактическая — в TraderTeamRates по PS)
TEAM_RATE_IN = Decimal("6.00")
TEAM_RATE_OUT = Decimal("2.00")

INR_USDT_RATE = Decimal("85.00")

INR_REQUIRED_FIELDS = {
    "deposit_number": {
        "regex": r"^\d{9,20}$",
        "pattern": "Account number (9-20 digits)",
    },
}

DEFAULT_PS = {
    "expired_time_in": datetime.timedelta(minutes=15),
    "arbitrage_time_in": datetime.timedelta(minutes=30),
    "auto_close_amount": Decimal("-1"),
    "expired_time_out": datetime.timedelta(minutes=10),
    "confirm_time_out": datetime.timedelta(minutes=10),
    "constrain_time_out": datetime.timedelta(hours=4),
    "in_on": True,
    "out_on": False,
    "sbp_compatible": False,
    "required_fields": INR_REQUIRED_FIELDS,
}


def _ensure_payment_system(name: str, currency: Currency) -> PaymentSystem:
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    if ps:
        print(f"  ~ PaymentSystem {name} ({ps.id})")
        return ps
    ps = PaymentSystem.objects.create(
        name=name,
        currency=currency,
        usdt_exchange_rate=INR_USDT_RATE,
        **DEFAULT_PS,
    )
    print(f"  + PaymentSystem {name} ({ps.id})")
    return ps


@transaction.atomic
def run():
    print("=== Fortune Solomon INR trader team ===")

    lang = Language.objects.first() or Language.objects.create(name="English")
    inr = Currency.objects.filter(symbol="INR").first()
    if inr is None:
        inr = Currency.objects.create(name="Indian Rupee", symbol="INR")
        print("  + Currency INR")
    else:
        print(f"  ~ Currency INR ({inr.id})")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})

    team, created = TraderTeam.objects.get_or_create(
        name=TEAM_NAME,
        defaults={"rate_in": TEAM_RATE_IN, "rate_out": TEAM_RATE_OUT},
    )
    if not created and (team.rate_in != TEAM_RATE_IN or team.rate_out != TEAM_RATE_OUT):
        team.rate_in = TEAM_RATE_IN
        team.rate_out = TEAM_RATE_OUT
        team.save(update_fields=["rate_in", "rate_out"])
    print(f"  {'+' if created else '~'} TraderTeam {TEAM_NAME} rate_in={team.rate_in}% rate_out={team.rate_out}%")

    for ps_name, mdr_in in PS_RATES.items():
        ps = _ensure_payment_system(ps_name, inr)
        rate, r_created = TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": mdr_in, "mdr_out": Decimal("2.50")},
        )
        if not r_created and rate.mdr_in != mdr_in:
            rate.mdr_in = mdr_in
            rate.save(update_fields=["mdr_in"])
        print(f"    TraderTeamRates {ps_name}: mdr_in={rate.mdr_in}%")

    user = User.objects.filter(username=TRADER_USERNAME).first()
    if user is None:
        user = User.objects.create_user(
            username=TRADER_USERNAME,
            email=TRADER_EMAIL,
            password=TRADER_PASSWORD,
            first_name="Fortune",
            last_name="Solomon",
        )
        print(f"  + User {TRADER_USERNAME}")
    else:
        if user.email != TRADER_EMAIL:
            user.email = TRADER_EMAIL
            user.save(update_fields=["email"])
        print(f"  ~ User {TRADER_USERNAME} ({user.id})")

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("0"))
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            language=lang,
            team=team,
            balance_usdt=bal,
            frozen_balance_usdt=fr,
            currency=inr,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME} ({trader.id})")
    else:
        if trader.team_id != team.id or trader.currency_id != inr.id:
            trader.team = team
            trader.currency = inr
            trader.is_boss = True
            trader.save(update_fields=["team", "currency", "is_boss"])
        print(f"  ~ Trader {TRADER_USERNAME} ({trader.id})")

    print("\nDone.")
    print("  Head support: добавьте команду в controlled_teams для саппорта.")
    print("  MerchantSolution: payment_system RTGS / IMPS, валюта INR, лимиты.")
    print("  Трейдер в UI: Payment Details → work_type «Deposit Number», IFSC в BIC, owner = account name.")
    print("  API мерчанту (RTGS/IMPS): account_number, account_name, ifsc (+ deposit_number, owner, bic).")
    print(f"\n  Login: {TRADER_USERNAME}")
    print(f"  Password (сменить!): {TRADER_PASSWORD}")
    print(f"  Email: {TRADER_EMAIL}")


if __name__ == "__main__":
    run()
else:
    print("Run: run()")
