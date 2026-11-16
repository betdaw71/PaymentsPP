"""
Melbet PAY-OUT (вывод): Cannot process → тестовый трейдер → Success + callback.

ID ищем как есть и с/без префикса w (Melbet часто шлёт w5547812021).

Создать тестового трейдера + inspect:
  MERCHANT_ORDER_ID=w5547812021 \\
  docker compose exec -T -e MERCHANT_ORDER_ID app \\
    python manage.py shell < titanpay/basics/shell_force_melbet_payout_success.py

Применить:
  MERCHANT_ORDER_ID=w5547812021 APPLY=1 \\
  docker compose exec -T -e MERCHANT_ORDER_ID -e APPLY app \\
    python manage.py shell < titanpay/basics/shell_force_melbet_payout_success.py

Опционально: TRADER=melbet_kgs_payout_test  MDR_OUT=2.5
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
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
from merchant.kzt_settlement import ensure_kzt_balances
from payments.integrations.melbet.callbacks import try_send_melbet_payout_callback
from payments.models import PayOut, PayOutStatus
from trade.models import OutOrder, OutOrderStatus
from trade.utils import calculate_fees

MOID_RAW = (os.environ.get("MERCHANT_ORDER_ID") or os.environ.get("ORDER_ID") or "").strip()
TRADER = (os.environ.get("TRADER") or "melbet_kgs_payout_test").strip() or "melbet_kgs_payout_test"
TEAM_NAME = (os.environ.get("TEAM_NAME") or "Melbet KGS Payout Test").strip()
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
SEND_CB = (os.environ.get("SEND_CALLBACK") or "1").strip().lower() not in {"0", "false", "no"}
MDR_OUT = Decimal(os.environ.get("MDR_OUT", "2.5") or "2.5")
MDR_IN = Decimal(os.environ.get("MDR_IN", "7") or "7")
PASSWORD = (os.environ.get("PASSWORD") or "KgPayout_Test_2026!").strip()
USDT_BALANCE = Decimal(os.environ.get("USDT_BALANCE", "50000") or "50000")


def _moid_candidates(raw: str) -> list[str]:
    raw = (raw or "").strip()
    out: list[str] = []
    for x in (raw, raw.lstrip("wW"), f"w{raw.lstrip('wW')}", f"W{raw.lstrip('wW')}"):
        if x and x not in out:
            out.append(x)
    return out


def find_payout(raw: str) -> PayOut | None:
    related = (
        "status",
        "currency",
        "payment_system",
        "merchant__user",
        "order__status",
        "order__solution__merchant__user",
        "order__solution__payment_system",
        "order__payment_details__group__trader__user",
    )
    for cand in _moid_candidates(raw):
        po = (
            PayOut.objects.filter(merchant_order_id=cand)
            .select_related(*related)
            .order_by("-created_at")
            .first()
        )
        if po:
            return po
        po = PayOut.objects.filter(id=cand).select_related(*related).first()
        if po:
            return po
        od = OutOrder.objects.filter(id=cand).first()
        if od:
            po = PayOut.objects.filter(order=od).select_related(*related).first()
            if po:
                return po
    # fuzzy contains
    digits = "".join(c for c in raw if c.isdigit())
    if digits:
        po = (
            PayOut.objects.filter(merchant_order_id__icontains=digits)
            .select_related(*related)
            .order_by("-created_at")
            .first()
        )
        if po:
            return po
    return None


def _virtual_card() -> str:
    return ("5" + uuid.uuid4().hex[:15]).ljust(16, "0")[:16]


def ensure_test_trader(ps: PaymentSystem) -> Trader:
    """Отдельный тестовый трейдер (не resdfe): out_active группы + реки."""
    kgs = Currency.objects.filter(symbol="KGS").first() or ps.currency
    lang = Language.objects.order_by("id").first()
    traffic, _ = TrafficType.objects.get_or_create(name="Standard", defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(name=TEAM_NAME)

    for name in ("QRKGS", "C2CKGS", "PHONEKGS"):
        p = PaymentSystem.objects.filter(name=name, currency=kgs).first()
        if p is None:
            continue
        TraderTeamRates.objects.get_or_create(
            team=team,
            payment_system=p,
            defaults={"mdr_in": MDR_IN, "mdr_out": MDR_OUT},
        )

    user = User.objects.filter(username=TRADER).first()
    if user is None:
        user = User.objects.create_user(
            username=TRADER,
            email=f"{TRADER}@test.local",
            password=PASSWORD,
        )
        print(f"  + user {TRADER} password={PASSWORD}")
    else:
        print(f"  ~ user {TRADER}")

    trader = Trader.objects.filter(user=user).select_related("balance_usdt", "team").first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=USDT_BALANCE)
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            team=team,
            currency=kgs,
            language=lang,
            balance_usdt=bal,
            frozen_balance_usdt=fr,
            is_boss=True,
            manual_mode=True,
            telegram=f"@{TRADER}",
            phone="+996700000001",
        )
        print(f"  + trader {TRADER}")
    else:
        fields = []
        if trader.team_id != team.id:
            trader.team = team
            fields.append("team")
        if not trader.manual_mode:
            trader.manual_mode = True
            fields.append("manual_mode")
        if fields:
            trader.save(update_fields=fields)
        if trader.balance_usdt and trader.balance_usdt.amount < USDT_BALANCE:
            trader.balance_usdt.amount = USDT_BALANCE
            trader.balance_usdt.save(update_fields=["amount"])
        print(f"  ~ trader {TRADER}")

    # Группа именно под PS заявки + запасные KGS PS.
    names = {ps.name, "C2CKGS", "PHONEKGS", "QRKGS"}
    for name in names:
        p = PaymentSystem.objects.filter(name=name, currency=kgs).first() or (
            ps if ps.name == name else None
        )
        if p is None:
            continue
        group = PaymentDetailsGroup.objects.filter(
            trader=trader, payment_system=p, currency=kgs
        ).first()
        if group is None:
            group = PaymentDetailsGroup.objects.create(
                owner=f"{TRADER} {p.name} OUT",
                trader=trader,
                currency=kgs,
                payment_system=p,
                status=1,
                amount=Decimal("999999"),
                in_active=False,
                out_active=True,
                min_amount_out=Decimal("1"),
                max_amount_out=Decimal("5000000"),
                work_type="by_card",
                deposit_number_on=False,
                auto_live=timezone.now(),
                current_volume=Decimal("0"),
                current_out_volume=Decimal("0"),
                limit_per_period=Decimal("999999999"),
            )
            group.allowed_traffic.add(traffic)
            print(f"    + group {p.name} {group.id}")
        else:
            group.status = 1
            group.out_active = True
            group.in_active = False
            group.auto_live = timezone.now()
            group.save(update_fields=["status", "out_active", "in_active", "auto_live", "updated_at"])
            group.allowed_traffic.add(traffic)
            print(f"    ~ group {p.name} {group.id}")

        detail = PaymentDetails.objects.filter(group=group, status=1).first()
        if detail is None:
            # unique_active_phone / unique_active_card_number — разные значения на каждый PS.
            suffix = uuid.uuid4().int % 10**7
            kwargs = {
                "group": group,
                "status": 1,
                "amount": Decimal("999999"),
                "deposit_number": str(uuid.uuid4().int % 10**20).zfill(20),
                "sberpay_enabled": False,
                "sbp_enabled": False,
                "bank_name": "MBank",
            }
            if p.name.upper() in {"PHONEKGS", "QRKGS"}:
                kwargs["phone"] = f"+9967{suffix:07d}"
                if p.name.upper() == "QRKGS":
                    kwargs["qr_payload"] = "https://example.invalid/media/pd_qr/test.png"
            else:
                kwargs["card_number"] = _virtual_card()
            detail = PaymentDetails.objects.create(**kwargs)
            print(f"      + detail {detail.id}")
        else:
            print(f"      ~ detail {detail.id}")

    print(f"  NOTE: не добавляйте {TRADER} в PSP_TRADER_USERNAMES")
    return trader


def _pick_out_detail(trader: Trader, ps: PaymentSystem) -> PaymentDetails | None:
    return (
        PaymentDetails.objects.filter(
            status=1,
            group__status=1,
            group__out_active=True,
            group__trader=trader,
            group__payment_system=ps,
        )
        .select_related("group", "group__trader", "group__payment_system")
        .order_by("-creation_date")
        .first()
    )


def _has_out_freeze(order: OutOrder) -> bool:
    from trade.models import Transaction

    return Transaction.objects.filter(
        linked_out_order=order, transaction_type__name="Freeze"
    ).exists()


def inspect(po: PayOut) -> None:
    od = po.order
    print("=== payout inspect ===")
    print(f"  PayOut={po.id} status={po.status.name if po.status_id else None}")
    print(f"  merchant_order_id={po.merchant_order_id!r}")
    print(f"  amount={po.amount} {po.currency.symbol if po.currency_id else '?'}")
    print(f"  ps={po.payment_system.name if po.payment_system_id else None}")
    print(f"  merchant={po.merchant.user.username if po.merchant_id else None}")
    print(f"  details={po.details}")
    if od is None:
        print("  OutOrder: NONE")
        return
    print(f"  OutOrder={od.id} status={od.status.name if od.status_id else None}")
    print(f"  usd={od.usd_amount} merchant_fee={od.merchant_fee} trader_fee={od.trader_fee}")
    if od.payment_details_id:
        t = od.payment_details.group.trader.user.username
        print(f"  trader={t} detail={od.payment_details_id}")
    else:
        print("  trader/detail=None")


def apply(po: PayOut, trader: Trader) -> None:
    if po.order_id is None:
        raise RuntimeError("PayOut has no OutOrder")
    ps = po.payment_system or po.order.solution.payment_system
    detail = _pick_out_detail(trader, ps)
    if detail is None:
        raise RuntimeError(f"No out detail for {TRADER} / {ps.name}")

    ensure_kzt_balances(po.merchant)

    with transaction.atomic():
        # of=("self",): иначе PG падает на nullable OUTER JOIN (payment_details).
        od = (
            OutOrder.objects.select_for_update(of=("self",))
            .select_related("status", "solution", "solution__merchant", "solution__payment_system")
            .get(pk=po.order_id)
        )
        st = od.status.name if od.status_id else None
        if st == "Completed":
            print("Already Completed")
        elif st not in {"Cannot process", "New", "Money sent by trader"}:
            raise RuntimeError(f"Refuse from OutOrder status={st}")
        else:
            from merchant.kzt_settlement import uses_melbet_fiat_settlement

            rate = ps.get_rate()
            usd_amount = (od.amount / Decimal(str(rate))).quantize(Decimal("0.01"))
            if uses_melbet_fiat_settlement(od.solution.merchant, ps):
                for_merchant, for_trader, _ = calculate_fees(
                    od.amount, od.solution, trader, direction="out"
                )
                merchant_fee = for_merchant - od.amount
                trader_fee = for_trader - od.amount
            else:
                for_merchant, for_trader, _ = calculate_fees(
                    usd_amount, od.solution, trader, direction="out"
                )
                merchant_fee = for_merchant - usd_amount
                trader_fee = for_trader - usd_amount

            need_attach = st == "Cannot process" or od.payment_details_id is None
            if not need_attach and od.payment_details_id:
                cur = PaymentDetails.objects.filter(pk=od.payment_details_id).select_related(
                    "group"
                ).first()
                if cur is None or cur.group.trader_id != trader.id:
                    need_attach = True

            if need_attach or st == "Cannot process":
                new_st = OutOrderStatus.objects.get(name="New")
                od.status = new_st
                od.payment_details = detail
                od.usd_amount = usd_amount
                od.merchant_fee = merchant_fee
                od.trader_fee = trader_fee
                od.updated_date = timezone.now()
                od.save(
                    update_fields=[
                        "status",
                        "payment_details",
                        "usd_amount",
                        "merchant_fee",
                        "trader_fee",
                        "updated_date",
                    ]
                )
                group = PaymentDetailsGroup.objects.select_for_update().get(pk=detail.group_id)
                group.current_out_volume += od.amount
                group.updated_at = timezone.now()
                group.save(update_fields=["current_out_volume", "updated_at"])
                if not _has_out_freeze(od):
                    od.freeze("Shell: Melbet payout test freeze")
                    print("  + merchant freeze")
                print(f"  attached detail={detail.id} status=New")

            od.refresh_from_db()
            if od.status.name == "New":
                od.money_sent()
            od.refresh_from_db()
            if od.status.name in {"Money sent by trader", "New", "Arbitrage"}:
                od.complete_after_money_sent()
            print("  -> OutOrder Completed")

        locked_po = PayOut.objects.select_for_update(of=("self",)).get(pk=po.pk)
        if not locked_po.status_id or locked_po.status.name != "Success":
            locked_po.success()
            print("  -> PayOut Success")

    po.refresh_from_db()
    od = po.order
    od.refresh_from_db()
    print(
        f"DONE PayOut={po.status.name} OutOrder={od.status.name} "
        f"trader={od.payment_details.group.trader.user.username}"
    )
    if SEND_CB:
        sent = try_send_melbet_payout_callback(po, status_name="Success")
        print(f"  melbet payout callback={sent}")


def run() -> None:
    if not MOID_RAW:
        print("ERROR: set MERCHANT_ORDER_ID=w5547812021")
        return
    print(f"MERCHANT_ORDER_ID={MOID_RAW!r} TRADER={TRADER} APPLY={APPLY}")
    print(f"  lookup candidates={_moid_candidates(MOID_RAW)}")

    po = find_payout(MOID_RAW)
    if po is None:
        print("NOT FOUND PayOut — проверь ID (часто с префиксом w: w5547812021)")
        # show recent melbet outs
        recent = (
            PayOut.objects.filter(merchant__user__username__icontains="melbet")
            .order_by("-created_at")[:10]
        )
        print("  last melbet payouts:")
        for r in recent:
            print(
                f"    moid={r.merchant_order_id!r} status={r.status.name if r.status_id else None} "
                f"ps={r.payment_system.name if r.payment_system_id else None} amount={r.amount}"
            )
        return

    inspect(po)
    ps = po.payment_system
    if ps is None:
        print("ERROR: no payment_system")
        return
    trader = ensure_test_trader(ps)
    detail = _pick_out_detail(trader, ps)
    print(f"  test detail ready={detail.id if detail else None}")
    if not APPLY:
        print("DRY-RUN — set APPLY=1 to assign test trader + Success")
        return
    apply(po, trader)


run()
