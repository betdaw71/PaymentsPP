"""
Django shell: команда + виртуальный трейдер PayMap PSP (KZT).

Документация: http://docs.paymap.me (v2, базовый URL https://europe.paymap.me)
Колбек: {PUBLIC_API_URL}/api/v1/webhooks/psp/paymap/

После run() в .env (ключ НЕ коммитить):
  PAYMAP_API_BASE=https://europe.paymap.me
  PAYMAP_API_KEY=pk_live_...
  PAYMAP_TRADER_USERNAME=paymap_kzt
  PAYMAP_DEFAULT_INVOICE_TYPE=TRANSGRAN
  PAYMAP_INVOICE_TYPE_MAP={"C2CKZT":"TRANSGRAN"}
  PAYMAP_TRANSGRAN_COUNTRY=KG
  # или PAYMAP_TRANSGRAN_COUNTRY_MAP={"C2CKZT":"KG"}
  # PAYMAP_TRANSGRAN_DETAIL_TYPE=card

Запуск:
  docker compose exec app python manage.py shell < basics/shell_create_paymap_trader.py
"""
from __future__ import annotations

import datetime
import secrets
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

TEAM_NAME = "Paymap KZT"
TRADER_USERNAME = "paymap_kzt"
TRADER_EMAIL = "paymap_kzt@example.com"
GROUP_OWNER = "Paymap Virtual"
TRAFFIC_NAME = "Standard"
PS_NAMES = ("C2CKZT",)


def _generated_password() -> str:
    return secrets.token_urlsafe(14)


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


def run(*, reset_password: bool = False):
    password = _generated_password()
    print("=== PayMap KZT trader setup ===")
    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")
        print("  + Currency KZT")
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.filter(name=ps_name, currency=kzt).first()
        if ps is None:
            ps = PaymentSystem.objects.create(
                name=ps_name,
                currency=kzt,
                required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
                usdt_exchange_rate=Decimal("520"),
                expired_time_in=datetime.timedelta(minutes=15),
                expired_time_out=datetime.timedelta(minutes=10),
                confirm_time_out=datetime.timedelta(minutes=10),
                constrain_time_out=datetime.timedelta(hours=4),
                in_on=True,
                out_on=False,
            )
            print(f"  + PaymentSystem {ps_name}")
        TraderTeamRates.objects.get_or_create(
            team=team, payment_system=ps, defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")}
        )
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "PayMap KZT"},
    )
    if created or reset_password:
        user.set_password(password)
        user.save()
        print("  + User password set (see below)")
    else:
        password = '(unchanged - use reset_password=True to rotate)'
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
            currency=kzt,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    elif trader.team_id != team.id:
        trader.team = team
        trader.save(update_fields=["team"])
    for ps_name in PS_NAMES:
        ps = PaymentSystem.objects.get(name=ps_name, currency=kzt)
        ensure_virtual_group(trader, kzt, ps, traffic, ps_name)
    print("")
    print("=== Trader cabinet login ===")
    print(f"  URL:      https://avapay.net/  (or your frontend host)")
    print(f"  Login:    {TRADER_USERNAME}")
    print(f"  Password: {password}")
    print("")
    print("Next steps:")
    print("  1) migrate (payments 0015_paymap_pay_in_session)")
    print("  2) .env PAYMAP_API_KEY=your pk_live_… (from PayMap)")
    print("  3) Head support: controlled_teams → Paymap KZT")
    print("  4) MerchantSolution: C2CKZT, currency KZT, limits per contract")
    print("  5) PayMap callbackUrl → /api/v1/webhooks/psp/paymap/")


if __name__ == "__main__":
    run()
else:
    print("Run: run()  or  run(reset_password=True)")
