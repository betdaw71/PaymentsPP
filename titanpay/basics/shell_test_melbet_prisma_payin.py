"""
Тестовая Melbet KGS deposit → Prisma (prisma1).

  METHOD=card2card_kgs AMOUNT=5000 \\
  docker compose exec -T -e METHOD -e AMOUNT app \\
    python manage.py shell < titanpay/basics/shell_test_melbet_prisma_payin.py

METHOD: card2card_kgs | phone_kgs | qr_kgs
MERCHANT: melbet | melbet_test (default melbet)
FORCE_PRISMA=1 — временно выключить in_active у не-prisma групп; всегда восстанавливает
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from basics.models import PaymentDetailsGroup
from payments.integrations.melbet.models import MelbetIntegrationConfig
from payments.integrations.melbet.services import create_melbet_deposit, deposit_response
from payments.models import PrismaPayInSession
from payments.prisma_client import prisma_map_requisite, prisma_trader_username

MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip() or "melbet"
METHOD = (os.environ.get("METHOD") or "card2card_kgs").strip() or "card2card_kgs"
AMOUNT = Decimal(os.environ.get("AMOUNT", "5000") or "5000")
FORCE_PRISMA = (os.environ.get("FORCE_PRISMA") or "0").strip().lower() in ("1", "true", "yes")
PS_BY_METHOD = {
    "card2card_kgs": "C2CKGS",
    "card_kgs": "C2CKGS",
    "phone_kgs": "PHONEKGS",
    "mobile_kgs": "PHONEKGS",
    "qr_kgs": "QRKGS",
    "lkq": "QRKGS",
    "elqr": "QRKGS",
    "default_kgs": "QRKGS",
}


def _force_prisma_only(ps_name: str) -> list[str]:
    """Disable competing IN groups; returns group ids to restore."""
    prisma = prisma_trader_username().lower()
    disabled_ids: list[str] = []
    qs = PaymentDetailsGroup.objects.filter(
        status=1,
        in_active=True,
        payment_system__name=ps_name,
        currency__symbol="KGS",
    ).select_related("trader__user")
    for g in qs:
        uname = (g.trader.user.username if g.trader and g.trader.user else "") or ""
        if uname.lower() == prisma:
            continue
        g.in_active = False
        g.save(update_fields=["in_active", "updated_at"])
        disabled_ids.append(str(g.id))
        print(f"  FORCE_PRISMA off {uname}:{g.id}")
    return disabled_ids


def _restore_groups(group_ids: list[str]) -> None:
    if not group_ids:
        return
    n = PaymentDetailsGroup.objects.filter(id__in=group_ids).update(in_active=True)
    print(f"  FORCE_PRISMA restored in_active=True for {n} groups")


print("=== Melbet → Prisma KGS payin test ===")
cfg = MelbetIntegrationConfig.objects.filter(
    merchant__user__username=MERCHANT, active=True
).select_related("merchant__user").first()
if cfg is None:
    raise SystemExit(f"No active MelbetIntegrationConfig for {MERCHANT!r}")

ps_name = PS_BY_METHOD.get(METHOD.lower(), "C2CKGS")
disabled_ids: list[str] = []
exit_code = 0
try:
    if FORCE_PRISMA:
        disabled_ids = _force_prisma_only(ps_name)
        print(f"  FORCE_PRISMA disabled count={len(disabled_ids)}")

    payload = {
        "order_id": f"kgs-prisma-{uuid.uuid4().hex[:12]}",
        "amount": str(AMOUNT),
        "currency": "KGS",
        "method": METHOD,
        "customer_account_id": f"test-prisma-{uuid.uuid4().hex[:8]}",
        "callback_url": "https://example.invalid/melbet/cb",
        "success_url": "https://example.invalid/ok",
        "pending_url": "https://example.invalid/pending",
        "fail_url": "https://example.invalid/fail",
    }
    print(f"  merchant={MERCHANT} method={METHOD} amount={AMOUNT} order_id={payload['order_id']}")

    try:
        pay_in = create_melbet_deposit(cfg, payload)
    except Exception as exc:
        print(f"FAIL create: {type(exc).__name__}: {exc}")
        exit_code = 1
        pay_in = None

    if pay_in is not None:
        pay_in.refresh_from_db()
        trader = None
        if pay_in.order_id and pay_in.order and pay_in.order.payment_details_id:
            trader = pay_in.order.payment_details.group.trader.user.username
        print("response:", deposit_response(pay_in))
        print(
            f"pay_in={pay_in.id} status={pay_in.status.name if pay_in.status_id else None} "
            f"order={pay_in.order.status.name if pay_in.order_id and pay_in.order.status_id else None} "
            f"trader={trader}"
        )

        session = PrismaPayInSession.objects.filter(pay_in=pay_in).first()
        if session is None:
            print("PrismaPayInSession: NONE — check routing or PRISMA_API_TOKEN")
        else:
            cr = session.create_response or {}
            req = prisma_map_requisite(cr)
            print(f"PrismaPayInSession provider_id={session.provider_order_id!r}")
            print(f"  create keys={list(cr.keys())[:12]}")
            print(f"  mapped requisite={req}")
            if cr.get("error") or cr.get("message"):
                print(f"  upstream: {cr.get('error') or cr.get('message')}")

        print("\ntrace:")
        print(f"  docker compose exec -T app python manage.py diagnose_payin {pay_in.id}")
        print(f"  docker compose exec -T app python manage.py payin_trace {pay_in.id}")
finally:
    _restore_groups(disabled_ids)

raise SystemExit(exit_code)
