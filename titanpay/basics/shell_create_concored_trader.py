"""
Django shell: команда + трейдер Concored PSP (MMK — KBZPay, WavePay).

После run() в .env (токены не коммитить):
  CONCORDED_API_BASE=https://<host от Concored>
  CONCORDED_TRADER_USERNAME=concored_mmk
  CONCORDED_KBZPAY_TOKEN=...        # MID-0000011 MYA KBZPay
  CONCORDED_WAVEPAY_TOKEN=...       # MID-0000012 MYA WavePay
  CONCORDED_PAYMENT_METHOD_MAP={"KBZPay":"<code>","WavePay":"<code>"}

Callback: {PUBLIC_API_URL}/api/v1/webhooks/psp/concored/

Запуск:
  docker compose exec app python manage.py shell < basics/shell_create_concored_trader.py
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)

TEAM_NAME = "Concored MMK"
TRADER_USERNAME = "concored_mmk"
TRADER_PASSWORD = "ChangeMe_Concored_MMK_1!"
TRADER_EMAIL = "concored_mmk@example.com"
GROUP_OWNER = "Concored Virtual"
TRAFFIC_NAME = "Standard"
PS_NAMES = ("KBZPay", "WavePay")


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str):
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group:
        if group.status != 1 or not group.in_active:
            group.status = 1
            group.in_active = True
            group.amount = Decimal("999999999")
            group.save(update_fields=["status", "in_active", "amount"])
        print(f"  ~ virtual group {label} ({group.id})")
        return
    group = PaymentDetailsGroup.objects.create(
        owner=f"{GROUP_OWNER} {label}",
        trader=trader,
        currency=currency,
        payment_system=payment_system,
        status=1,
        amount=Decimal("999999999"),
        in_active=True,
        out_active=False,
        min_amount_out=Decimal("5000"),
        max_amount_out=Decimal("5000000"),
        work_type="by_card",
        deposit_number_on=False,
        auto_live=timezone.now(),
    )
    group.allowed_traffic.add(traffic)
    card = "4" + uuid.uuid4().hex[:15]
    card = "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")
    PaymentDetails.objects.create(
        group=group,
        status=1,
        amount=Decimal("999999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"  + Virtual group {label} ({group.id})")


def run():
    print("=== Concored MMK trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="English")
    mmk = Currency.objects.filter(symbol="MMK").first()
    if mmk is None:
        mmk = Currency.objects.create(symbol="MMK", name="Myanmar Kyat")
        print("  + Currency MMK")
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"in_rate": Decimal("5"), "out_rate": Decimal("2")}
    )
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=mmk).first()
        if ps is None:
            required = (
                {"phone": {"regex": r"^\+95\d{7,12}$", "pattern": "Myanmar phone (+95...)"}}
                if ps_name in ("KBZPay", "WavePay")
                else {"card_number": {"regex": r"^\d{16}$", "pattern": "16-digit card"}}
            )
            ps = PaymentSystem.objects.create(
                name=ps_name,
                currency=mmk,
                required_fields=required,
                usdt_exchange_rate=Decimal("3500"),
                expired_time_in=datetime.timedelta(minutes=10),
                expired_time_out=datetime.timedelta(minutes=10),
                confirm_time_out=datetime.timedelta(minutes=10),
                constrain_time_out=datetime.timedelta(hours=4),
                in_on=True,
                out_on=True,
            )
            print(f"  + PaymentSystem {ps_name}")
        TraderTeamRates.objects.get_or_create(
            team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")}
        )

    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Concored MMK"},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
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
            currency=mmk,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.get(name=ps_name, currency=mmk)
        ensure_virtual_group(trader, mmk, ps, traffic, ps_name)

    print("Done.")
    print("  1) Head support: controlled_teams → Concored MMK")
    print("  2) MerchantSolution: KBZPay / WavePay, лимиты MMK")
    print("  3) CONCORDED_* в .env + migrate payments 0014")
    print("  4) В Concored указать callbackUrl → /api/v1/webhooks/psp/concored/")


import sys

# `manage.py shell < this_file.py` — __name__ не __main__, но argv содержит shell
if __name__ == "__main__" or (len(sys.argv) >= 2 and sys.argv[1] == "shell"):
    run()
else:
    print("Запустите: run()")
