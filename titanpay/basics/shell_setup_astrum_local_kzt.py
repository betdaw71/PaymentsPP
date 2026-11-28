"""Второй кабинет Asterisk: трейдер astrum_local_kzt, только C2C KZT, свои креды.

Группа out_active=False (выплаты трансграна не забирает).
in_active=True только если в .env есть ASTRUM_LOCAL_API_KEY, PRIVATE_KEY, METHOD_TYPE_ID
и передан APPLY=1. Иначе аккаунт создаётся выключенным.

Каскад: только мерчанты из ASTRUM_LOCAL_MERCHANTS
(по умолчанию pandapay_local_kzt,pandapay_kz_local). Остальные C2C эту группу не видят.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_setup_astrum_local_kzt.py

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_setup_astrum_local_kzt.py
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.conf import settings
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
from payments.astrum_client import (
    astrum_local_merchant_usernames,
    astrum_local_trader_username,
    profile_for_username,
)

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
USERNAME = (os.environ.get("TRADER_USERNAME") or astrum_local_trader_username() or "astrum_local_kzt").strip()
PS_NAME = (os.environ.get("PS") or getattr(settings, "ASTRUM_LOCAL_PS_NAME", None) or "C2C").strip()
TEAM_NAME = "Astrum Local KZT"
PASSWORD = os.environ.get("TRADER_PASSWORD") or "ChangeMe_Astrum_Local_KZT_1!"
MDR_IN = Decimal(str(os.environ.get("MDR") or "6.00"))
PSP_FLOAT = Decimal(os.environ.get("FLOAT_USDT") or "50000")
TRAFFIC_NAME = "Standard"


def _card() -> str:
    raw = "4" + uuid.uuid4().hex[:15]
    return "".join(c for c in raw if c.isdigit())[:16].ljust(16, "0")


def run() -> None:
    profile = profile_for_username(USERNAME)
    keys_ok = bool(profile and profile.api_key and profile.private_key and profile.method_type_id)
    print(f"=== astrum local {USERNAME} PS={PS_NAME} APPLY={int(APPLY)} keys_ok={int(keys_ok)} ===")
    print(f"merchants: {sorted(astrum_local_merchant_usernames())}")
    if profile is None:
        print("! local profile missing — username совпал с трансгран astrum_kzt или пустой")
        return
    print(
        f"api_key={int(bool(profile.api_key))} private_key={int(bool(profile.private_key))} "
        f"method_type_id={profile.method_type_id or '-'}"
    )
    if not keys_ok:
        print("ключи пустые: аккаунт можно создать, pay-in останется выключенным")
        print("в .env нужны ASTRUM_LOCAL_API_KEY, ASTRUM_LOCAL_PRIVATE_KEY, ASTRUM_LOCAL_METHOD_TYPE_ID")

    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        print("! no KZT currency")
        return
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        print(f"! PaymentSystem {PS_NAME} KZT not found — не создаю метод")
        return
    print(f"PS {ps.name} {ps.id}")

    if not APPLY:
        exists = User.objects.filter(username=USERNAME).exists()
        print(f"dry-run. user exists={int(exists)}. APPLY=1 создаст трейдера и группу.")
        print("DONE")
        return

    lang = Language.objects.first() or Language.objects.create(name="Russian")
    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": MDR_IN, "rate_out": Decimal("0")}
    )
    rate, _ = TraderTeamRates.objects.get_or_create(
        team=team,
        payment_system=ps,
        defaults={"mdr_in": MDR_IN, "mdr_out": Decimal("0")},
    )
    if rate.mdr_in != MDR_IN:
        rate.mdr_in = MDR_IN
        rate.save(update_fields=["mdr_in"])
    print(f"team {team.name} mdr_in={rate.mdr_in}")

    user, created = User.objects.get_or_create(
        username=USERNAME,
        defaults={"email": f"{USERNAME}@example.com", "first_name": "Astrum Local KZT"},
    )
    if created:
        user.set_password(PASSWORD)
        user.save()
        print(f"  + user {USERNAME} / {PASSWORD}")
    else:
        print(f"  ~ user {USERNAME}")

    trader = Trader.objects.filter(user=user).select_related("balance_usdt").first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=PSP_FLOAT)
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
            credit_limit=PSP_FLOAT,
        )
        print(f"  + trader {trader.id}")
    else:
        fields = []
        if trader.team_id != team.id:
            trader.team = team
            fields.append("team")
        if trader.currency_id != kzt.id:
            trader.currency = kzt
            fields.append("currency")
        if trader.blocked:
            trader.blocked = False
            fields.append("blocked")
        if trader.credit_limit < PSP_FLOAT:
            trader.credit_limit = PSP_FLOAT
            fields.append("credit_limit")
        if fields:
            trader.save(update_fields=fields)
        if trader.balance_usdt_id and trader.balance_usdt.amount < PSP_FLOAT:
            trader.balance_usdt.amount = PSP_FLOAT
            trader.balance_usdt.save(update_fields=["amount"])
            print(f"  + float {PSP_FLOAT}")
        print(f"  ~ trader {trader.id}")

    turn_on = keys_ok
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=ps, currency=kzt).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner="Astrum Local KZT",
            trader=trader,
            currency=kzt,
            payment_system=ps,
            status=1,
            amount=Decimal("9999999"),
            in_active=turn_on,
            out_active=False,
            min_amount_in=Decimal("1000"),
            max_amount_in=Decimal("1000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            limit_per_period=Decimal("50000000"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {group.id} in_active={turn_on} out_active=False")
    else:
        group.status = 1
        group.in_active = turn_on
        group.out_active = False
        group.auto_live = timezone.now()
        group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {group.id} in_active={turn_on} out_active=False")

    if not PaymentDetails.objects.filter(
        group=group, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
    ).exists():
        card = _card()
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=card,
            deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + stub ****{card[-4:]}")

    print(f"\nPSP_XE_MARKUP_BY_TRADER сейчас: {getattr(settings, 'PSP_XE_MARKUP_BY_TRADER', '')}")
    print(f'добавь "{USERNAME}":"1.03" если этого ключа нет, и перезапусти app')
    print("LIVENESS_EXEMPT_TRADER_USERNAMES должен содержать", USERNAME)
    if not keys_ok:
        print("pay-in не включён: нет локальных кредов")
    print("DONE")


run()
