"""
Mostbet C2CKZT pay-out → astrum_kzt.

- Клонирует MerchantSolution C2C ftd=false на C2CKZT, если нет.
- Добавляет traffic решения mostbet в группу astrum_kzt.
- Проверяет choose_trader_out.

Запуск:
  docker compose exec -T app python manage.py shell < basics/shell_ensure_mostbet_c2ckzt_astrum.py

После деплоя кода в .env (rebuild app):
  PAYOUT_PREFERRED_TRADER_BY_MERCHANT={"mostbet":"astrum_kzt"}
  ASTRUM_TRADER_USERNAME=astrum_kzt
  ASTRUM_C2C_NAME=C2CKZT
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User

from basics.models import PaymentDetailsGroup, PaymentSystem, TrafficType, Trader
from merchant.models import Merchant, MerchantSolution
from titanpay.settings import ASTRUM_C2C_NAME, ASTRUM_TRADER_USERNAME

MERCHANT_USERNAME = "mostbet"
ASTRUM_USERNAME = ASTRUM_TRADER_USERNAME or "astrum_kzt"
C2CKZT_NAME = ASTRUM_C2C_NAME or "C2CKZT"
PROBE_AMOUNT = Decimal("20000")


def _print_solution(label, sol):
    if sol is None:
        print(f"  {label}: MISSING")
        return
    traffic = sol.traffic.name if sol.traffic else "?"
    print(
        f"  {label}: status={sol.status} ftd={sol.ftd} traffic={traffic} "
        f"out=[{sol.min_limit_out} .. {sol.max_limit_out}] mdr_out={sol.mdr_out}"
    )


def ensure_c2ckzt_solution(merchant, c2ckzt):
    sol = MerchantSolution.objects.filter(
        merchant=merchant, payment_system=c2ckzt, ftd=False, status=1
    ).first()
    if sol is not None:
        _print_solution("C2CKZT existing", sol)
        return sol

    source = MerchantSolution.objects.filter(
        merchant=merchant, payment_system__name="C2C", ftd=False, status=1
    ).first()
    if source is None:
        source = MerchantSolution.objects.filter(
            merchant=merchant, payment_system__name="C2C", ftd=False
        ).first()
    if source is None:
        print("  ! no C2C ftd=false MerchantSolution to clone")
        return None

    sol = MerchantSolution.objects.create(
        merchant=merchant,
        payment_system=c2ckzt,
        status=1,
        ftd=False,
        mdr_in=source.mdr_in,
        mdr_out=source.mdr_out,
        traffic=source.traffic,
        autoclose_arbitrage=source.autoclose_arbitrage,
        min_limit_in=source.min_limit_in,
        max_limit_in=source.max_limit_in,
        min_limit_out=source.min_limit_out,
        max_limit_out=source.max_limit_out,
    )
    _print_solution("C2CKZT cloned from C2C", sol)
    return sol


def ensure_astrum_traffic(astrum: Trader, traffic: TrafficType):
    groups = PaymentDetailsGroup.objects.filter(trader=astrum, payment_system__name=C2CKZT_NAME)
    if not groups.exists():
        print(f"  ! no C2CKZT group on {ASTRUM_USERNAME} — run shell_create_astrum_trader.py")
        return None
    for group in groups:
        changed = []
        if group.status != 1:
            group.status = 1
            changed.append("status")
        if not group.out_active:
            group.out_active = True
            changed.append("out_active")
        if group.deposit_number_on:
            group.deposit_number_on = False
            changed.append("deposit_number_on")
        if group.min_amount_out > PROBE_AMOUNT:
            group.min_amount_out = Decimal("1000")
            changed.append("min_amount_out")
        if group.max_amount_out < PROBE_AMOUNT:
            group.max_amount_out = Decimal("5000000")
            changed.append("max_amount_out")
        if (group.amount or Decimal("0")) < PROBE_AMOUNT:
            group.amount = Decimal("9999999")
            changed.append("amount")
        if changed:
            group.save()
            print(f"  ~ group {group.id} updated {changed}")
        if traffic and not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
            print(f"  + traffic {traffic.name} on group {group.id}")
        else:
            names = list(group.allowed_traffic.values_list("name", flat=True))
            print(f"  ~ group {group.id} traffic={names} out_active={group.out_active}")
    return groups.first()


def run():
    print("=== Mostbet C2CKZT → astrum_kzt ===")
    merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if merchant is None:
        raise SystemExit(f"Merchant {MERCHANT_USERNAME} not found")

    c2ckzt = PaymentSystem.objects.filter(name=C2CKZT_NAME).first()
    if c2ckzt is None:
        raise SystemExit(f"PaymentSystem {C2CKZT_NAME} not found")

    astrum_user = User.objects.filter(username=ASTRUM_USERNAME).first()
    astrum = Trader.objects.filter(user=astrum_user).first() if astrum_user else None
    if astrum is None:
        raise SystemExit(f"Trader {ASTRUM_USERNAME} not found — run shell_create_astrum_trader.py")
    if astrum.blocked:
        astrum.blocked = False
        astrum.save(update_fields=["blocked"])
        print(f"  ~ unblocked {ASTRUM_USERNAME}")

    c2c = PaymentSystem.objects.filter(name="C2C").first()
    if c2c:
        _print_solution(
            "C2C",
            MerchantSolution.objects.filter(
                merchant=merchant, payment_system=c2c, ftd=False, status=1
            ).first(),
        )

    sol = ensure_c2ckzt_solution(merchant, c2ckzt)
    if sol is None:
        raise SystemExit("Cannot create C2CKZT MerchantSolution")

    if not merchant.payment_systems.filter(pk=c2ckzt.pk).exists():
        merchant.payment_systems.add(c2ckzt)
        print(f"  + merchant.payment_systems += {C2CKZT_NAME}")

    ensure_astrum_traffic(astrum, sol.traffic)

    test_c2c = Trader.objects.filter(user__username="mostbet_c2c_out_test").first()
    if test_c2c:
        n = PaymentDetailsGroup.objects.filter(trader=test_c2c, out_active=True).update(out_active=False)
        print(f"  ~ mostbet_c2c_out_test out_active=False ({n} groups) — leftover C2C must not take payouts")

    from trade.utils import choose_trader_out

    detail, usd, ok = choose_trader_out(PROBE_AMOUNT, c2ckzt, sol.traffic, merchant=merchant)
    trader_name = detail.group.trader.user.username if detail else None
    print(f"  choose_trader_out {PROBE_AMOUNT} {C2CKZT_NAME}: ok={ok} trader={trader_name} usd={usd}")
    if not ok or trader_name != ASTRUM_USERNAME:
        print(f"  ! expected {ASTRUM_USERNAME}. Check group out_active/limits/cards and PAYOUT_PREFERRED_TRADER_BY_MERCHANT")
    else:
        print("Done. Mostbet C2CKZT payouts pin to astrum_kzt.")


if __name__ == "__main__":
    run()
else:
    print("Run: run()")
