"""
Django shell: виртуальная группа payment_system=C2C (KZT) для трейдера Bitzone (bitzone1).

Заявки с payment_system=C2C и currency=KZT смогут попадать в роутинг на bitzone1
(наряду с expayone и др., если у них тоже есть группы C2C).

Предварительно: bitzone1 уже создан (shell_create_bitzone_trader.py).

В .env при разных method у Bitzone для C2C vs C2CKZT:
  BITZONE_METHOD_MAP={"C2C":"cross_card","C2CKZT":"cross_card"}
  # или card / cross_sbp — по договору с Bitzone

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_bitzone_add_c2c_group.py
"""
from decimal import Decimal
import datetime
import uuid

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Currency,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeamRates,
    TrafficType,
)
from titanpay.settings import C2C_NAME

TRADER_USERNAME = "bitzone1"
GROUP_OWNER = "Bitzone Virtual Drop"
TRAFFIC_NAME = "Standard"
PS_NAME = C2C_NAME  # "C2C"
CURRENCY_SYMBOL = "KZT"


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
        min_amount_out=Decimal("1000"),
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
        amount=Decimal("999999"),
        card_number=card,
        deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
        sberpay_enabled=False,
        sbp_enabled=False,
    )
    print(f"  + virtual group {label} ({group.id})")
    return group


def run():
    print("=== Bitzone: add C2C (KZT) virtual group ===")

    user = User.objects.filter(username=TRADER_USERNAME).first()
    if user is None:
        print(f"  ERROR: user {TRADER_USERNAME} not found — run shell_create_bitzone_trader.py first")
        return
    trader = Trader.objects.filter(user=user).select_related("team").first()
    if trader is None:
        print(f"  ERROR: trader for {TRADER_USERNAME} not found")
        return
    print(f"  ~ Trader {TRADER_USERNAME} team={trader.team.name if trader.team else '?'}")

    kzt = Currency.objects.filter(symbol=CURRENCY_SYMBOL).first()
    if kzt is None:
        print(f"  ERROR: currency {CURRENCY_SYMBOL} not found")
        return

    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        ps = PaymentSystem.objects.filter(name=PS_NAME).first()
        if ps is not None and ps.currency_id != kzt.id:
            print(
                f"  WARN: PaymentSystem C2C exists for {ps.currency.symbol}, "
                f"not {CURRENCY_SYMBOL} — создайте C2C+KZT в админке или поправьте CURRENCY_SYMBOL"
            )
    if ps is None:
        ps = PaymentSystem.objects.create(
            name=PS_NAME,
            currency=kzt,
            required_fields={"card_number": {"regex": r"^\d{16}$", "pattern": "16 digits"}},
            usdt_exchange_rate=Decimal("520"),
            expired_time_in=datetime.timedelta(minutes=15),
            expired_time_out=datetime.timedelta(minutes=10),
            confirm_time_out=datetime.timedelta(minutes=10),
            constrain_time_out=datetime.timedelta(hours=4),
        )
        print(f"  + PaymentSystem {ps.name} ({ps.id})")
    else:
        print(f"  ~ PaymentSystem {ps.name} ({ps.id}) currency={ps.currency.symbol}")

    if trader.team_id:
        TraderTeamRates.objects.get_or_create(
            team=trader.team,
            payment_system=ps,
            defaults={"mdr_in": Decimal("7"), "mdr_out": Decimal("2.5")},
        )

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    ensure_virtual_group(trader, kzt, ps, traffic, f"KZT {PS_NAME}")

    print("")
    print("Done.")
    print("  1) У мерчанта должен быть MerchantSolution: payment_system=C2C, currency=KZT")
    print("  2) diagnose_routing: python manage.py diagnose_routing --merchant <name> --ps C2C")
    print("  3) При необходимости в .env: BITZONE_METHOD_MAP с ключом C2C")


run()
