"""Aggrepay H2H latency: сколько мс уходит на Astrum/PSP внутри create.

Мерчант с CURLOPT ~2000ms получает:
  cURL error 28: Operation timed out after 2001 milliseconds with 0 bytes received
пока мы синхронно ждём Astrum (трансгран) и каскад на трейдеров.

Запуск:
  docker compose exec -T -e HOURS=6 -e MERCHANT=aggrepay app \\
    python manage.py shell < titanpay/basics/shell_aggrepay_h2h_latency.py

  docker compose exec -T app python manage.py diagnose_routing aggrepay \\
    --ps C2CKZT --amount 20000 --ftd false
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta
from statistics import median

from django.utils import timezone

from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import is_psp_trader

MERCHANT = (os.environ.get("MERCHANT") or "aggrepay").strip()
HOURS = float(os.environ.get("HOURS") or "6")
LIMIT = int(os.environ.get("LIMIT") or "40")


def _ms_list(rows) -> list[int]:
    out: list[int] = []
    for row in rows:
        body = row.body if isinstance(row.body, dict) else {}
        raw = body.get("elapsed_ms")
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


since = timezone.now() - timedelta(hours=HOURS)
print("=" * 72)
print(f"Aggrepay H2H latency  merchant={MERCHANT}  window={HOURS}h  since={since.isoformat()}")
print("=" * 72)

qs = (
    PayIn.objects.filter(
        merchant__user__username__iexact=MERCHANT,
        created_at__gte=since,
    )
    .select_related("status", "payment_system", "order__status", "order__payment_details__group__trader__user")
    .order_by("-created_at")
)
print(f"pay_ins: {qs.count()}")

by_status = Counter(qs.values_list("status__name", flat=True))
print("pay_in status:")
for name, n in by_status.most_common():
    print(f"  {name or '—'}: {n}")

# PSP attach timings from trace
routing = PayInTraceLog.objects.filter(
    merchant__user__username__iexact=MERCHANT,
    created_at__gte=since,
    direction="routing",
    note__icontains="psp provider",
).order_by("-created_at")
ms = _ms_list(routing)
print(f"\nPSP attach traces: {routing.count()}  with elapsed_ms: {len(ms)}")
if ms:
    print(
        f"  elapsed_ms  min={min(ms)}  p50={_pct(ms, 50)}  p90={_pct(ms, 90)}  "
        f"p99={_pct(ms, 99)}  max={max(ms)}  median={int(median(ms))}"
    )
    over_2s = sum(1 for v in ms if v >= 2000)
    over_5s = sum(1 for v in ms if v >= 5000)
    print(f"  >=2000ms (мерчант curl 28 @2s): {over_2s}/{len(ms)}")
    print(f"  >=5000ms: {over_5s}/{len(ms)}")

by_provider = Counter()
slow: list[tuple] = []
for row in routing[:500]:
    body = row.body if isinstance(row.body, dict) else {}
    prov = body.get("provider") or "?"
    by_provider[str(prov)] += 1
    try:
        elapsed = int(body.get("elapsed_ms"))
    except (TypeError, ValueError):
        continue
    if elapsed >= 2000:
        slow.append((row.created_at, row.merchant_order_id, prov, elapsed, body.get("success")))

print("\nPSP providers in traces:")
for name, n in by_provider.most_common():
    print(f"  {name}: {n}")

print(f"\nSlow attaches (>=2s), last {min(LIMIT, len(slow))}:")
for created, moid, prov, elapsed, ok in slow[:LIMIT]:
    print(f"  {created}  {elapsed:5d}ms  ok={ok}  psp={prov}  moid={moid}")

# Who got the deal
print(f"\nRecent issuers (last {LIMIT}):")
for pay_in in qs[:LIMIT]:
    order = pay_in.order
    trader = None
    if order and order.payment_details_id and order.payment_details and order.payment_details.group_id:
        trader = order.payment_details.group.trader
    uname = getattr(getattr(trader, "user", None), "username", None) or "—"
    kind = "psp" if is_psp_trader(trader) else "trader"
    print(
        f"  {pay_in.created_at}  {pay_in.amount}  st={getattr(pay_in.status, 'name', None)}  "
        f"{kind}:{uname}  moid={pay_in.merchant_order_id}"
    )

print(
    """
=== Вывод для мерчанта ===
1) Тело запроса OK (currency/KZT, C2CKZT, amount, ftd, callback, merchant_order_id*g, client_id).
2) curl error 28 @2001ms — их клиентский timeout ~2s. Наш /in/h2h синхронно:
   роутинг → Astrum (трансгран) → при отказе/таймауте каскад на живых трейдеров.
   Ответ часто 3–15s. При timeout=2s они получают 0 bytes.
3) Им: CURLOPT_TIMEOUT / connect+total не ниже 15–30 секунд.
4) Нам: ASTRUM_PAYIN_CREATE_TIMEOUT=5 (fail-fast Astrum → трейдеры).
"""
)
print("Готово.")
