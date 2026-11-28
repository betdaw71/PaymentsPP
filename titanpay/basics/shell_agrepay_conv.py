"""Конверсия мерчанта: невыдача реквизита vs выдали и не оплатили.

  docker compose exec -T -e MERCHANT=agrepay -e DAYS=3 app \\
    python manage.py shell < titanpay/basics/shell_agrepay_conv.py

  MERCHANT=agrepay     # кусок username, без учёта регистра
  DAYS=3               # окно назад от сейчас
  SINCE=2026-11-17     # вместо DAYS, календарь МСК, until не включается
  UNTIL=2026-11-19
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone

from merchant.models import Merchant
from payments.models import PayIn, PayInTraceLog

MSK = ZoneInfo("Europe/Moscow")
QUERY = (os.environ.get("MERCHANT") or "agrepay").strip()
DAYS = int(os.environ.get("DAYS") or "3")
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
UNTIL_RAW = (os.environ.get("UNTIL") or "").strip()

PROGRESS = {"In Progress", "Pending"}
BUCKETS = (
    (Decimal("0"), Decimal("5000"), "0–5k"),
    (Decimal("5000"), Decimal("10000"), "5–10k"),
    (Decimal("10000"), Decimal("20000"), "10–20k"),
    (Decimal("20000"), Decimal("50000"), "20–50k"),
    (Decimal("50000"), None, "50k+"),
)


def _parse_date(raw: str) -> datetime:
    raw = raw.replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=MSK)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {raw!r}")


def window():
    if SINCE_RAW:
        start = _parse_date(SINCE_RAW)
        end = _parse_date(UNTIL_RAW) if UNTIL_RAW else timezone.now().astimezone(MSK)
        return start, end
    end = timezone.now()
    return end - timedelta(days=DAYS), end


def pct(num, den) -> str:
    if not den:
        return "—"
    return f"{100.0 * num / den:.1f}%"


def bucket(amount) -> str:
    amt = Decimal(str(amount or 0))
    for lo, hi, label in BUCKETS:
        if amt >= lo and (hi is None or amt < hi):
            return label
    return "?"


def find_merchants():
    hits = list(
        Merchant.objects.filter(user__username__icontains=QUERY).select_related("user")
    )
    if hits:
        return hits
    if QUERY.lower() != "agre":
        hits = list(
            Merchant.objects.filter(user__username__icontains="agre").select_related("user")
        )
    return hits


def list_candidates(start, end):
    print("Мерчант не найден. Кто создавал заявки в этом окне:")
    rows = (
        PayIn.objects.filter(created_at__gte=start, created_at__lt=end)
        .values("merchant__user__username")
        .annotate(n=Count("id"))
        .order_by("-n")[:25]
    )
    for row in rows:
        print(f"  {row['merchant__user__username'] or '?':20} {row['n']}")
    print("Повтори с MERCHANT=<username>")


class Tot:
    def __init__(self):
        self.n = 0
        self.declined = 0
        self.success = 0
        self.progress = 0
        self.failed = 0
        self.no_req = 0

    def add(self, status, has_req):
        self.n += 1
        if status == "Declined":
            self.declined += 1
            return
        if not has_req:
            self.no_req += 1
        if status == "Success":
            self.success += 1
        elif status in PROGRESS:
            self.progress += 1
        else:
            self.failed += 1

    @property
    def issued(self):
        return self.n - self.declined


def line_tot(name, tot: Tot) -> str:
    return (
        f"{name:22} n={tot.n:5}  dec={tot.declined:5}  iss={tot.issued:5}  "
        f"ok={tot.success:4}  open={tot.progress:4}  fail={tot.failed:4}  "
        f"cr→ok {pct(tot.success, tot.n):7}  iss→ok {pct(tot.success, tot.issued):7}  "
        f"no_req={tot.no_req}"
    )


def analyze(merchant: Merchant, start, end):
    name = merchant.user.username
    print("=" * 88)
    print(f"{name}   {start.astimezone(MSK):%Y-%m-%d %H:%M} — {end.astimezone(MSK):%Y-%m-%d %H:%M} МСК")
    print("=" * 88)

    qs = PayIn.objects.filter(merchant=merchant, created_at__gte=start, created_at__lt=end)
    rows = qs.values_list(
        "id",
        "status__name",
        "payment_system_id",
        "payment_system__name",
        "order__status__name",
        "order__payment_details_id",
        "order__payment_details__group__trader__user__username",
        "order__payment_details__bank_name",
        "amount",
        "created_at",
        "client__client_id",
    )

    total = Tot()
    by_ps = defaultdict(Tot)
    by_trader = defaultdict(Tot)
    by_bank = defaultdict(Tot)
    by_amount = defaultdict(Tot)
    by_day = defaultdict(Tot)
    by_order_status = Counter()
    by_pay_status = Counter()
    clients = defaultdict(lambda: [0, 0])
    ps_ids = set()
    success_ids = []

    for (
        pid,
        status,
        ps_id,
        ps_name,
        order_status,
        details_id,
        trader,
        bank,
        amount,
        created,
        client_id,
    ) in rows.iterator(chunk_size=1000):
        status = status or "?"
        has_req = details_id is not None
        total.add(status, has_req)
        by_pay_status[status] += 1
        by_order_status[order_status or "—"] += 1
        ps_label = ps_name or "?"
        by_ps[ps_label].add(status, has_req)
        if ps_id:
            ps_ids.add(ps_id)
        if status != "Declined":
            by_trader[trader or "—"].add(status, has_req)
            by_bank[(bank or "—")[:32]].add(status, has_req)
        by_amount[bucket(amount)].add(status, has_req)
        day = created.astimezone(MSK).strftime("%Y-%m-%d")
        by_day[day].add(status, has_req)
        cid = client_id or "?"
        clients[cid][0] += 1
        if status == "Success":
            clients[cid][1] += 1
            success_ids.append(pid)

    if total.n == 0:
        print("Заявок нет.")
        return ps_ids

    print()
    print(line_tot("ИТОГО", total))
    print()
    print("PayIn статус:")
    for status, n in by_pay_status.most_common():
        print(f"  {status:20} {n:5}  {pct(n, total.n)}")
    print("InOrder статус:")
    for status, n in by_order_status.most_common():
        print(f"  {status:20} {n:5}  {pct(n, total.n)}")

    print()
    print("По платёжной системе:")
    for label, tot in sorted(by_ps.items(), key=lambda kv: -kv[1].n):
        print("  " + line_tot(label, tot))

    print()
    print("По дням (МСК):")
    for day in sorted(by_day):
        print("  " + line_tot(day, by_day[day]))

    print()
    print("По сумме (только выданные считаются в iss→ok):")
    for _, _, label in BUCKETS:
        tot = by_amount.get(label)
        if tot and tot.n:
            print("  " + line_tot(label, tot))

    print()
    print("По трейдеру (только не Declined — реквизит назначали):")
    shown = 0
    for label, tot in sorted(by_trader.items(), key=lambda kv: -kv[1].n):
        if shown >= 15:
            break
        print("  " + line_tot(label, tot))
        shown += 1

    print()
    print("По банку реквизита (не Declined):")
    shown = 0
    for label, tot in sorted(by_bank.items(), key=lambda kv: -kv[1].n):
        if shown >= 12:
            break
        print("  " + line_tot(label, tot))
        shown += 1

    spam_orders = 0
    heavy = sorted(clients.items(), key=lambda kv: -kv[1][0])[:8]
    print()
    print("Клиенты: топ по числу create (ok = Success):")
    for cid, (n, ok) in heavy:
        mark = "  СПАМ" if n >= 5 and ok == 0 else ""
        print(f"  {str(cid)[:40]:40} n={n:4} ok={ok:3}{mark}")
    for cid, (n, ok) in clients.items():
        if n >= 5 and ok == 0:
            spam_orders += n
    print(f"Клиенты ≥5 create и 0 Success: заявок {spam_orders} ({pct(spam_orders, total.n)} от create)")

    _callbacks(merchant, start, end, success_ids)
    _declines(merchant, start, end)
    _verdict(total, spam_orders)
    return ps_ids


def _callbacks(merchant, start, end, success_ids):
    print()
    print("Ответы мерчанту на create (merchant_response):")
    resp = (
        PayInTraceLog.objects.filter(
            merchant=merchant,
            created_at__gte=start,
            created_at__lt=end,
            direction="merchant_response",
        )
        .values("note", "status_code")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    any_resp = False
    for row in resp[:12]:
        any_resp = True
        print(f"  {row['status_code']!s:>4}  {row['note'] or '—':22} {row['n']}")
    if not any_resp:
        print("  нет trace")

    print("Callback нашим Success → мерчанту:")
    if not success_ids:
        print("  Success нет")
        return
    cbs = (
        PayInTraceLog.objects.filter(
            pay_in_id__in=success_ids,
            direction="merchant_callback",
        )
        .values("status_code")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    ok_payins = set(
        PayInTraceLog.objects.filter(
            pay_in_id__in=success_ids,
            direction="merchant_callback",
            status_code__gte=200,
            status_code__lt=300,
        )
        .values_list("pay_in_id", flat=True)
        .distinct()
    )
    for row in cbs:
        print(f"  http {row['status_code']}: {row['n']}")
    missing = len(success_ids) - len(ok_payins)
    print(f"  Success без принятого callback (не 2xx): {missing} из {len(success_ids)}")


def _body_hint(body) -> str:
    if not isinstance(body, dict):
        return str(body)[:120]
    for key in ("error", "detail", "details", "result", "psp_provider", "in_order_status", "trader"):
        if key in body and body[key]:
            val = body[key]
            if isinstance(val, (dict, list)):
                val = str(val)
            return f"{key}={str(val)[:140]}"
    chosen = body.get("chosen")
    if isinstance(chosen, dict) and chosen.get("trader"):
        return f"chosen={chosen.get('trader')}"
    skipped = body.get("skipped") or []
    if skipped:
        bits = []
        for row in skipped[:3]:
            if isinstance(row, dict):
                bits.append(f"{row.get('trader')}:{row.get('skip')}")
        if bits:
            return "skip " + ", ".join(bits)
    return str(body)[:140]


def _declines(merchant, start, end):
    print()
    print("Почему Declined (trace, топ note):")
    notes = (
        PayInTraceLog.objects.filter(
            merchant=merchant,
            created_at__gte=start,
            created_at__lt=end,
            pay_in__status__name="Declined",
        )
        .values("direction", "note")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    shown = 0
    for row in notes:
        if shown >= 12:
            break
        print(f"  {row['n']:5}  {row['direction']:22} {row['note'] or '—'}")
        shown += 1
    if shown == 0:
        print("  нет")
        return

    print("Последние отказы (что ушло мерчанту / роутинг):")
    recent = list(
        PayIn.objects.filter(
            merchant=merchant,
            created_at__gte=start,
            created_at__lt=end,
            status__name="Declined",
        )
        .order_by("-created_at")
        .values_list("id", "created_at", "payment_system__name", "amount", "merchant_order_id")[:8]
    )
    ids = [row[0] for row in recent]
    logs = PayInTraceLog.objects.filter(pay_in_id__in=ids).order_by("created_at")
    by_pi = defaultdict(list)
    for log in logs:
        if log.note in {"declined", "psp provider api failed", "routing decision"} or (
            log.direction == "merchant_response"
        ):
            by_pi[log.pay_in_id].append(log)
    for pid, created, ps, amount, moid in recent:
        picked = by_pi.get(pid) or []
        hint = _body_hint(picked[-1].body) if picked else "нет trace"
        note = picked[-1].note if picked else ""
        when = created.astimezone(MSK).strftime("%m-%d %H:%M")
        print(f"  {when} {ps or '?':10} {amount} moid={moid} [{note}] {hint}")


def _verdict(total: Tot, spam_orders: int):
    print()
    print("ВЫВОД")
    dec = 100.0 * total.declined / total.n
    iss_ok = (100.0 * total.success / total.issued) if total.issued else None
    cr_ok = 100.0 * total.success / total.n
    print(f"  create→ok {cr_ok:.1f}%   выдача→ok {pct(total.success, total.issued)}   отказы {dec:.1f}%")
    if dec >= 40:
        print("  Основное — невыдача: мерчанту уходит Declined, реквизита нет. Это наша сторона (ликвидность или ошибка PSP/роутинга), не «карты не конвертят».")
    elif iss_ok is not None and iss_ok < 25 and total.issued >= 20:
        print("  Реквизит выдаём. Низкая оплата уже после выдачи: конверсия реквизитов, не обрыв на передаче.")
    elif iss_ok is not None and iss_ok >= 40 and cr_ok < 20:
        print("  Выданные платят нормально. Общую конверсию роняют отказы без реквизита.")
    else:
        print("  Смешанная картина: смотри dec и iss→ok по платёжке и трейдеру выше.")
    if total.no_req:
        print(f"  Заявок не-Declined без реквизита: {total.no_req}. Статус живой, карты в заявке нет.")
    if spam_orders and total.n and spam_orders / total.n >= 0.25:
        print(f"  Спам-клиенты (≥5 create, 0 Success) — {pct(spam_orders, total.n)} потока.")


def peers(merchant, ps_ids, start, end):
    if not ps_ids:
        return
    print()
    print("Другие мерчанты на тех же платёжках (для сравнения 50%):")
    rows = (
        PayIn.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            payment_system_id__in=ps_ids,
        )
        .exclude(merchant=merchant)
        .values("merchant__user__username", "payment_system__name", "status__name")
        .annotate(n=Count("id"))
    )
    acc = defaultdict(Tot)
    for row in rows:
        key = (row["merchant__user__username"] or "?", row["payment_system__name"] or "?")
        status = row["status__name"] or "?"
        n = row["n"]
        tot = acc[key]
        tot.n += n
        if status == "Declined":
            tot.declined += n
        elif status == "Success":
            tot.success += n
        elif status in PROGRESS:
            tot.progress += n
        else:
            tot.failed += n
    ranked = sorted(acc.items(), key=lambda kv: -kv[1].n)
    shown = 0
    for (uname, ps), tot in ranked:
        if tot.n < 30:
            continue
        print("  " + line_tot(f"{uname}/{ps}", tot))
        shown += 1
        if shown >= 12:
            break
    if shown == 0:
        print("  нет соседей с ≥30 заявок")


def main():
    start, end = window()
    merchants = find_merchants()
    if not merchants:
        print(f"Нет мерчанта по «{QUERY}». Окно {start.astimezone(MSK)} — {end.astimezone(MSK)} МСК")
        users = list(User.objects.filter(username__icontains=QUERY).values_list("username", flat=True)[:20])
        if users:
            print("Есть users, но не Merchant:", ", ".join(users))
        list_candidates(start, end)
        return
    if len(merchants) > 1:
        print("Несколько мерчантов:", ", ".join(m.user.username for m in merchants))
    for merchant in merchants:
        ps_ids = analyze(merchant, start, end)
        peers(merchant, ps_ids, start, end)
        print()


main()
