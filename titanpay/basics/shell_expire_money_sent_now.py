"""Принудительно закрыть просроченные «Деньги отправлены пользователем».

Исход: Expired + unfreeze + PayIn Failed (НЕ Success).

  # только отчёт (с sent_at / deadline / OVERDUE по каждой заявке)
  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_expire_money_sent_now.py

  # закрыть просроченные (TTL как в ЛК: от ПЕРВОЙ Money-sent)
  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_expire_money_sent_now.py

  # закрыть ВСЕ Money-sent сейчас, без проверки TTL
  docker compose exec -T -e APPLY=1 -e FORCE=1 app python manage.py shell \\
    < titanpay/basics/shell_expire_money_sent_now.py

  # полный expire() как cron (также OutOrder и т.д.)
  docker compose exec -T -e APPLY=1 -e FULL_EXPIRE=1 app python manage.py shell \\
    < titanpay/basics/shell_expire_money_sent_now.py
"""
from __future__ import annotations

import os
from datetime import timedelta

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from basics.models import PaymentSystem
from trade.models import InOrder, InOrderStatusChange
from trade.utils2 import expire

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
FULL = (os.environ.get("FULL_EXPIRE") or "").strip().lower() in {"1", "true", "yes"}
FORCE = (os.environ.get("FORCE") or "").strip().lower() in {"1", "true", "yes"}

now = timezone.now()
print(f"now={now.isoformat()} APPLY={APPLY} FULL_EXPIRE={FULL} FORCE={FORCE}")

stuck = InOrder.objects.filter(status__name="Money sent by user").select_related(
    "solution__payment_system",
    "status",
    "payment_details__group__trader__user",
)
print(f"Money sent by user total: {stuck.count()}")

due_ids = []
print("\n--- detail (every Money-sent order; TTL from FIRST Money-sent = UI) ---")
for o in stuck.order_by("updated_date"):
    ps = o.solution.payment_system if o.solution_id else None
    ttl = (ps.expired_time_in if ps else None) or timedelta(minutes=15)
    sc_first = (
        InOrderStatusChange.objects.filter(order=o, status__name="Money sent by user")
        .order_by("created_at")
        .first()
    )
    sc_last = (
        InOrderStatusChange.objects.filter(order=o, status__name="Money sent by user")
        .order_by("-created_at")
        .first()
    )
    n_sc = InOrderStatusChange.objects.filter(
        order=o, status__name="Money sent by user"
    ).count()
    sent_at = sc_first.created_at if sc_first else o.updated_date
    last_at = sc_last.created_at if sc_last else None
    deadline = sent_at + ttl
    overdue = now >= deadline
    left = deadline - now
    trader = "?"
    try:
        trader = o.payment_details.group.trader.user.username
    except Exception:
        pass
    print(
        f"  id={o.id} trader={trader} PS={ps.name if ps else '-'} "
        f"amount={o.amount} money_sent_rows={n_sc} "
        f"first_sent={sent_at} last_sent={last_at} ttl={ttl} "
        f"deadline={deadline} left={left} OVERDUE={overdue}"
    )
    if overdue or FORCE:
        due_ids.append(o.id)

for ps in PaymentSystem.objects.all():
    ttl = ps.expired_time_in or timedelta(minutes=15)
    cutoff = now - ttl
    money_sent_at = (
        InOrderStatusChange.objects.filter(
            order_id=OuterRef("pk"),
            status__name="Money sent by user",
        )
        .order_by("created_at")
        .values("created_at")[:1]
    )
    qs = (
        InOrder.objects.filter(
            status__name="Money sent by user",
            solution__payment_system=ps,
        )
        .annotate(_money_sent_at=Subquery(money_sent_at))
        .filter(_money_sent_at__lte=cutoff)
    )
    n = qs.count()
    if n:
        print(f"  PS={ps.name} ttl={ttl} due={n}")

# без InOrderStatusChange — fallback по updated_date
no_change = (
    InOrder.objects.filter(status__name="Money sent by user")
    .exclude(
        id__in=InOrderStatusChange.objects.filter(
            status__name="Money sent by user"
        ).values_list("order_id", flat=True)
    )
)
print(f"Money sent WITHOUT status_change row: {no_change.count()}")
for o in no_change.select_related("solution__payment_system")[:20]:
    ttl = o.solution.payment_system.expired_time_in if o.solution_id else timedelta(minutes=15)
    print(f"  id={o.id} updated={o.updated_date} ttl={ttl} overdue={o.updated_date <= now - ttl}")

print("sample due/force ids:", [str(i) for i in due_ids[:10]])

if not APPLY:
    print("DRY-RUN — APPLY=1 закрыть due; FORCE=1 + APPLY=1 закрыть все Money-sent")
elif FULL:
    print("running expire() …")
    expire()
    left = InOrder.objects.filter(status__name="Money sent by user").count()
    print(f"Money sent left after expire(): {left}")
else:
    closed = 0
    target_ids = list(due_ids)
    if FORCE:
        target_ids = list(
            InOrder.objects.filter(status__name="Money sent by user").values_list(
                "id", flat=True
            )
        )
    for oid in target_ids:
        try:
            with transaction.atomic():
                locked = InOrder.objects.select_for_update().get(pk=oid)
                if locked.status.name == "Money sent by user":
                    locked.deal_time_expired()
                    closed += 1
                    print(f"  expired {oid}")
        except Exception as exc:
            print(f"  FAIL {oid}: {exc}")
    # fallback: no status_change, use updated_date (unless FORCE already covered)
    if not FORCE:
        for o in no_change.select_related("solution__payment_system"):
            ttl = (
                o.solution.payment_system.expired_time_in
                if o.solution_id
                else timedelta(minutes=15)
            )
            if o.updated_date > now - ttl:
                continue
            try:
                with transaction.atomic():
                    locked = InOrder.objects.select_for_update().get(pk=o.pk)
                    if locked.status.name == "Money sent by user":
                        locked.deal_time_expired()
                        closed += 1
                        print(f"  expired(fallback) {o.id}")
            except Exception as exc:
                print(f"  FAIL fallback {o.id}: {exc}")
    print(f"closed={closed}")
    print(
        f"Money sent left: {InOrder.objects.filter(status__name='Money sent by user').count()}"
    )

print("DONE")
