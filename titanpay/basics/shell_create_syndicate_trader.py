"""
Django shell: трейдер Syndicate Pay PSP (username syndicate1) + виртуальные группы C2C и SBP (RUB).

Документация: syndicate-pay-api.pdf (H2H POST /api/orders/create)
Webhook: {PUBLIC_API_URL}/api/v1/webhooks/psp/syndicate/

После run() в .env:
  SYNDICATE_API_BASE=https://api.syndicate-pay.com
  SYNDICATE_MERCHANT_ID=<ID из ЛК>
  SYNDICATE_MERCHANT_LOGIN=<Login из ЛК>
  SYNDICATE_API_KEY=<API-ключ>
  SYNDICATE_TRADER_USERNAME=syndicate1
  SYNDICATE_BANK_MAP={"C2C":"any-bank","SBP":"sbp","SBER":"sberbank"}
  PUBLIC_API_URL=https://api.avapay.net

В кабинете Syndicate укажите callback:
  https://api.avapay.net/api/v1/webhooks/psp/syndicate/

Справочник кодов банков: payments/data/syndicate_banks.json (из banks-*.xlsx, 259 шт.)
Перегенерация:
  python3 titanpay/basics/generate_syndicate_banks_json.py /path/to/banks-*.xlsx
SYNDICATE_BANK_MAP в .env только для переопределения (не обязателен).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_create_syndicate_trader.py
"""
from decimal import Decimal
import datetime
import uuid

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
from titanpay.settings import C2C_NAME, SBP_NAME

TEAM_NAME = "Syndicate Agg"
TRADER_USERNAME = "syndicate1"
TRADER_PASSWORD = "ChangeMe_Syndicate_1!"
TRADER_EMAIL = "syndicate1@example.com"
GROUP_OWNER = "Syndicate Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAMES = (C2C_NAME, SBP_NAME)
PSP_FLOAT_USDT = Decimal("50000")


def ensure_virtual_group(trader, currency, payment_system, traffic, label: str):
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group:
        changed = False
        if group.status != 1:
            group.status = 1
            changed = True
        if not group.in_active:
            group.in_active = True
            changed = True
        if group.amount < Decimal("999999"):
            group.amount = Decimal("999999")
            changed = True
        if changed:
            group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ virtual group {label} ({group.id})")
        return group
    group = PaymentDetailsGroup.objects.create(
        owner=f"{GROUP_OWNER} {label}",
        trader=trader,
        currency=currency,
        payment_system=payment_system,
        status=1,
        amount=Decimal("999999"),
        in_active=True,
        out_active=False,
        min_amount_out=Decimal("100"),
        max_amount_out=Decimal("500000"),
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
        amount=Decimal("999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"  + virtual group {label} ({group.id})")
    return group


def ensure_virtual_detail(group, label: str):
    detail = PaymentDetails.objects.filter(group=group, status=1).first()
    if detail:
        print(f"  ~ virtual detail {label} ({detail.id})")
        return detail
    card = "4" + uuid.uuid4().hex[:15]
    card = "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")
    detail = PaymentDetails.objects.create(
        group=group,
        status=1,
        amount=Decimal("999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"  + virtual detail {label} ({detail.id})")
    return detail


def ensure_payment_system(currency, name: str):
    ps = PaymentSystem.objects.filter(name=name, currency=currency).first()
    if ps:
        print(f"  ~ PaymentSystem {name} ({ps.id})")
        return ps
    ps = PaymentSystem.objects.create(
        name=name,
        currency=currency,
        usdt_exchange_rate=Decimal("100"),
        expired_time_in=datetime.timedelta(minutes=30),
        expired_time_out=datetime.timedelta(minutes=15),
        confirm_time_out=datetime.timedelta(minutes=15),
        constrain_time_out=datetime.timedelta(hours=4),
        in_on=True,
        out_on=False,
        sbp_compatible=(name == SBP_NAME),
        required_fields={
            "card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"},
            "owner": {"regex": r"^.+$", "pattern": "Card holder"},
            "bank": {"regex": r"^.+$", "pattern": "Bank"},
        },
    )
    print(f"  + PaymentSystem {name} ({ps.id})")
    return ps


def run():
    rub = Currency.objects.filter(symbol="RUB").first()
    if rub is None:
        raise SystemExit("Currency RUB not found")
    traffic = TrafficType.objects.filter(name=TRAFFIC_NAME).first()
    if traffic is None:
        raise SystemExit(f"TrafficType {TRAFFIC_NAME} not found")

    lang = Language.objects.first()
    user = User.objects.filter(username=TRADER_USERNAME).first()
    if user is None:
        user = User.objects.create_user(
            username=TRADER_USERNAME,
            email=TRADER_EMAIL,
            password=TRADER_PASSWORD,
            first_name="Syndicate",
            last_name="PSP",
        )
        print(f"  + user {TRADER_USERNAME}")
    else:
        print(f"  ~ user {TRADER_USERNAME}")

    team = TraderTeam.objects.filter(name=TEAM_NAME).first()
    if team is None:
        team = TraderTeam.objects.create(name=TEAM_NAME, rate_in=Decimal("1"), rate_out=Decimal("1"))
        print(f"  + team {TEAM_NAME}")

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=PSP_FLOAT_USDT)
        frozen = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            team=team,
            balance_usdt=bal,
            frozen_balance_usdt=frozen,
            language=lang,
            blocked=False,
        )
        print(f"  + trader {TRADER_USERNAME}")
    else:
        if trader.team_id != team.id:
            trader.team = team
            trader.save(update_fields=["team"])
        print(f"  ~ trader {TRADER_USERNAME}")

    for ps_name in PS_NAMES:
        ps = ensure_payment_system(rub, ps_name)
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("1"), "mdr_out": Decimal("1")},
        )
        group = ensure_virtual_group(trader, rub, ps, traffic, ps_name)
        ensure_virtual_detail(group, ps_name)

    print("\nDone. Next:")
    print("  1) Add MerchantSolution for target merchant (C2C / SBP RUB)")
    print("  2) Route merchant to syndicate1 group (or sole PSP group)")
    print("  3) Set .env SYNDICATE_* and rebuild app")
    print("  4) Callback in Syndicate LK → /api/v1/webhooks/psp/syndicate/")


run()
