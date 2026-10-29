"""Melbet KZ cards Kaspi: конверсия + повторные клиенты + IP из payload (если Melbet шлёт).

Игровой IP в депозит-API не сохраняется: запрос приходит с серверов Melbet,
client_ip отбрасывается. Этот скрипт:
  1) считает конверсию C2CKZT / kaspi за окно и предыдущее такое же;
  2) ищет «спам» по customer_account_id (много заявок, мало Success);
  3) достаёт ip/user_ip/client_ip из тел melbet deposit, если поле было в JSON.

  docker compose exec -T -e DAYS=14 -e MERCHANT=melbet app python manage.py shell \\
    < titanpay/basics/shell_melbet_kz_kaspi_abuse.py
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.integrations.melbet.mapping import sender_bank_for_melbet_method
from payments.models import PayIn, PayInTraceLog

MSK = ZoneInfo("Europe/Moscow")
MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip()
DAYS = float(os.environ.get("DAYS") or "14")
MIN_PAYINS = int(os.environ.get("MIN_PAYINS") or "8")
BURST_MINUTES = int(os.environ.get("BURST_MINUTES") or "10")
BURST_N = int(os.environ.get("BURST_N") or "5")
TOP = int(os.environ.get("TOP") or "25")

IP_KEYS = (
    "ip",
    "user_ip",
    "userIp",
    "client_ip",
    "clientIp",
    "ip_address",
    "ipAddress",
    "customer_ip",
    "payer_ip",
)


def now_msk():
    return timezone.now().astimezone(MSK)


def window(days, *, end=None):
    end = end or now_msk()
    return end - timedelta(days=days), end


def qs_base(start, end):
    return (
        PayIn.objects.filter(
            merchant__user__username=MERCHANT,
            created_at__gte=start,
            created_at__lt=end,
        )
        .select_related(
            "status",
            "payment_system",
            "order",
            "order__status",
            "client",
            "melbet_session",
        )
        .order_by("created_at")
    )


def is_kz_kaspi(pay_in) -> bool:
    ps = (pay_in.payment_system.name or "").upper() if pay_in.payment_system else ""
    if ps not in {"C2CKZT", "PHONEKZT"}:
        return False
    session = getattr(pay_in, "melbet_session", None)
    method = (session.melbet_method if session is not None else "") or ""
    bank = sender_bank_for_melbet_method(method)
    if bank == "kaspi":
        return True
    if bank is None and method.lower() in {"", "card2card_kzt"}:
        # card2card_kzt без kaspi в имени — Halyk. Не берём.
        return False
    if "kaspi" in method.lower():
        return True
    return False


def deep_ips(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in IP_KEYS and isinstance(v, str) and v.strip():
                found.add(v.strip())
            deep_ips(v, found)
    elif isinstance(obj, list):
        for item in obj:
            deep_ips(item, found)
    elif isinstance(obj, str) and re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", obj.strip()):
        pass


class Cell:
    __slots__ = ("n", "success", "declined", "progress", "other")

    def __init__(self):
        self.n = self.success = self.declined = self.progress = self.other = 0

    def add(self, status: str):
        self.n += 1
        if status == "Success":
            self.success += 1
        elif status == "Declined":
            self.declined += 1
        elif status in ("In Progress", "Pending"):
            self.progress += 1
        else:
            self.other += 1

    @property
    def issued(self):
        return self.n - self.declined

    def conv(self):
        if self.issued <= 0:
            return None
        return 100.0 * self.success / self.issued


def pct(v):
    return f"{v:5.1f}%" if v is not None else "    -"


def print_cell(title, c: Cell):
    print(
        f"{title:<28} n={c.n:5}  decl={c.declined:4}  issued={c.issued:5}  "
        f"ok={c.success:5}  prog={c.progress:4}  iss→ok={pct(c.conv())}"
    )


def collect(start, end):
    total = Cell()
    by_day = defaultdict(Cell)
    by_method = defaultdict(Cell)
    by_os = defaultdict(Cell)
    clients: dict[str, dict] = {}
    rows = []
    for pay_in in qs_base(start, end).iterator(chunk_size=400):
        if not is_kz_kaspi(pay_in):
            continue
        status = pay_in.status.name if pay_in.status else "-"
        os_name = pay_in.order.status.name if pay_in.order and pay_in.order.status else "-"
        method = (getattr(getattr(pay_in, "melbet_session", None), "melbet_method", None) or "") or "(empty)"
        created = pay_in.created_at
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        day = created.astimezone(MSK).strftime("%Y-%m-%d")
        cid = (pay_in.client.client_id if pay_in.client_id and pay_in.client else "") or "(no_client)"
        total.add(status)
        by_day[day].add(status)
        by_method[method].add(status)
        by_os[os_name].add(status)
        rec = clients.setdefault(
            cid,
            {"n": 0, "ok": 0, "decl": 0, "times": []},
        )
        rec["n"] += 1
        rec["times"].append(created)
        if status == "Success":
            rec["ok"] += 1
        if status == "Declined":
            rec["decl"] += 1
        rows.append((cid, created, status, str(pay_in.id), str(pay_in.amount)))
    return total, by_day, by_method, by_os, clients, rows


def bursts(clients):
    hits = []
    delta = timedelta(minutes=BURST_MINUTES)
    for cid, rec in clients.items():
        times = sorted(rec["times"])
        i = 0
        while i < len(times):
            j = i
            while j < len(times) and times[j] - times[i] <= delta:
                j += 1
            n = j - i
            if n >= BURST_N:
                hits.append((n, cid, times[i], times[j - 1], rec["ok"], rec["n"]))
                i = j
            else:
                i += 1
    hits.sort(reverse=True)
    return hits


def extract_payload_ips(start, end):
    ip_counter = Counter()
    sample = []
    keys_seen = Counter()
    qs = PayInTraceLog.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        note="melbet deposit",
        merchant__user__username=MERCHANT,
    )
    n = 0
    for entry in qs.iterator(chunk_size=300):
        n += 1
        body = entry.body if isinstance(entry.body, dict) else {}
        found = set()

        def walk(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    keys_seen[k] += 1
                    if k in IP_KEYS and v:
                        found.add(str(v).strip())
                    walk(v, f"{path}.{k}" if path else k)

        walk(body)
        for ip in found:
            ip_counter[ip] += 1
            if len(sample) < 15:
                sample.append((ip, entry.merchant_order_id, entry.created_at))
    return n, ip_counter, sample, keys_seen


start, end = window(DAYS)
prev_start, prev_end = window(DAYS, end=start)

print("=" * 100)
print("Melbet KZ Kaspi — конверсия и повторные клиенты / IP из payload")
print(f"merchant={MERCHANT}  window={DAYS:g}d  {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} {MSK.key}")
print("фильтр: PS C2CKZT/PHONEKZT и method *kaspi*")
print()

total, by_day, by_method, by_os, clients, rows = collect(start, end)
ptotal, *_ = collect(prev_start, prev_end)

print("-- текущее окно --")
print_cell("KZ Kaspi", total)
print("-- предыдущее такое же окно --")
print_cell("KZ Kaspi prev", ptotal)
print()
print("-- по дням --")
for day in sorted(by_day):
    print_cell(day, by_day[day])
print()
print("-- method --")
for meth, c in sorted(by_method.items(), key=lambda x: -x[1].n):
    print_cell(meth[:28], c)
print()
print("-- InOrder status --")
for name, c in sorted(by_os.items(), key=lambda x: -x[1].n):
    print_cell(name[:28], c)

print()
print("-- клиенты --")
print(f"unique client_id: {len(clients)}")
repeat = [cid for cid, r in clients.items() if r["n"] >= MIN_PAYINS]
zero_ok = [cid for cid, r in clients.items() if r["n"] >= MIN_PAYINS and r["ok"] == 0]
print(f"client_id с ≥{MIN_PAYINS} заявок: {len(repeat)}")
print(f"из них 0 Success: {len(zero_ok)}")
print()
print(f"-- TOP {TOP} client_id по числу заявок --")
print(f"{'client_id':<40} {'n':>5} {'ok':>5} {'decl':>5} {'conv':>7}")
for cid, rec in sorted(clients.items(), key=lambda x: -x[1]["n"])[:TOP]:
    conv = f"{100.0 * rec['ok'] / rec['n']:.0f}%" if rec["n"] else "-"
    print(f"{cid[:40]:<40} {rec['n']:5} {rec['ok']:5} {rec['decl']:5} {conv:>7}")

print()
print(f"-- пачки: ≥{BURST_N} заявок за {BURST_MINUTES} мин с одного client_id --")
hits = bursts(clients)[:TOP]
if not hits:
    print("нет")
else:
    for n, cid, t0, t1, ok, total_n in hits:
        print(
            f"  n={n:3}  {cid[:36]:<36}  {t0.astimezone(MSK):%m-%d %H:%M}→{t1.astimezone(MSK):%H:%M}"
            f"  ok={ok}/{total_n}"
        )

print()
print("-- IP в телах melbet deposit (если Melbet передаёт) --")
n_logs, ip_counter, sample, keys_seen = extract_payload_ips(start, end)
print(f"trace 'melbet deposit': {n_logs}")
interesting = [k for k in IP_KEYS if keys_seen.get(k)]
print(f"ключи IP в payload: {interesting or 'нет'}")
if ip_counter:
    print("топ IP из payload:")
    for ip, c in ip_counter.most_common(TOP):
        print(f"  {c:5}  {ip}")
    print("примеры:")
    for ip, oid, ts in sample:
        print(f"  {ip}  order={oid}  {ts}")
else:
    print(
        "Игровых IP в депозит-запросе нет. С нашей стороны виден только IP серверов Melbet "
        "(whitelist API). Device.ip_address для этих клиентов не заполняется."
    )

print()
print("Итог для ответа Melbet:")
print("  • player IP в БД нет — депозит идёт server-to-server, поле IP в payload не приходило.")
print("  • спам смотрим по customer_account_id (client_id), не по IP.")
print("  • если пришлёте user IP в fields/ip — начнём копить и отдавать список.")
print("=" * 100)
