"""Проверка: дневной спад Mostbet — спам отдельных client_id?

Сравнивает окно 12–14 vs 09–11: концентрация клиентов, серии create без Success,
повторяющиеся суммы, «очищенная» конверсия без спам-кандидатов.

  docker compose exec -T -e MERCHANT=mostbet app python manage.py shell \\
    < titanpay/basics/shell_mostbet_spam_clients.py

  DAYS=2 HOUR_FROM=12 HOUR_TO=14 SPAM_MIN=3 TOP=15
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn

MSK = ZoneInfo("Europe/Moscow")
MERCHANT = (os.environ.get("MERCHANT") or "mostbet").strip()
PS = (os.environ.get("PS") or "").strip()
DAYS = max(1, int(os.environ.get("DAYS") or "2"))
HOUR_FROM = int(os.environ.get("HOUR_FROM") or "12")
HOUR_TO = int(os.environ.get("HOUR_TO") or "14")
SPAM_MIN = max(2, int(os.environ.get("SPAM_MIN") or "3"))  # creates/client with 0 ok
TOP = max(5, int(os.environ.get("TOP") or "15"))
BURST_SEC = max(5, int(os.environ.get("BURST_SEC") or "60"))  # gap ≤N sec = burst pair


def _now():
    return timezone.now().astimezone(MSK)


def pct(n, d) -> str:
    if d <= 0:
        return "  -  "
    return f"{100.0 * n / d:5.1f}%"


def client_key(p) -> str:
    if p.client_id is None:
        return "(no_client)"
    cid = (getattr(p.client, "client_id", None) or "").strip()
    return cid or f"(id={p.client_id})"


def load_window(start: datetime, end: datetime):
    qs = (
        PayIn.objects.filter(
            merchant__user__username=MERCHANT,
            created_at__gte=start,
            created_at__lt=end,
        )
        .select_related("status", "client", "payment_system")
        .order_by("created_at")
    )
    if PS:
        qs = qs.filter(payment_system__name__iexact=PS)
    return list(qs)


def analyze(label: str, start: datetime, end: datetime) -> dict:
    rows = load_window(start, end)
    created = len(rows)
    declined = sum(1 for p in rows if p.status and p.status.name == "Declined")
    success = sum(1 for p in rows if p.status and p.status.name == "Success")
    issued = created - declined

    by_client: dict[str, dict] = defaultdict(
        lambda: {
            "n": 0,
            "ok": 0,
            "decl": 0,
            "amounts": Counter(),
            "times": [],
            "statuses": Counter(),
        }
    )
    amounts = Counter()
    for p in rows:
        st = p.status.name if p.status else "-"
        ck = client_key(p)
        amt = p.amount if isinstance(p.amount, Decimal) else Decimal(str(p.amount or 0))
        amounts[amt] += 1
        c = by_client[ck]
        c["n"] += 1
        c["statuses"][st] += 1
        c["amounts"][amt] += 1
        c["times"].append(p.created_at.astimezone(MSK))
        if st == "Success":
            c["ok"] += 1
        elif st == "Declined":
            c["decl"] += 1

    unique = len(by_client)
    multi = sum(1 for c in by_client.values() if c["n"] >= 2)
    spam_clients = {
        k: v for k, v in by_client.items() if v["n"] >= SPAM_MIN and v["ok"] == 0
    }
    spam_creates = sum(v["n"] for v in spam_clients.values())
    spam_ok = sum(v["ok"] for v in spam_clients.values())  # always 0 by def

    # burst: consecutive creates from same client within BURST_SEC
    burst_pairs = 0
    burst_clients = set()
    for ck, c in by_client.items():
        times = sorted(c["times"])
        for a, b in zip(times, times[1:]):
            if (b - a).total_seconds() <= BURST_SEC:
                burst_pairs += 1
                burst_clients.add(ck)

    # conversion without spam candidates
    clean_n = created - spam_creates
    clean_ok = success - spam_ok
    clean_decl = declined  # spam rarely Declined here (issued=all)
    # recompute clean success from rows excluding spam client keys
    spam_keys = set(spam_clients)
    clean_rows = [p for p in rows if client_key(p) not in spam_keys]
    clean_n = len(clean_rows)
    clean_ok = sum(1 for p in clean_rows if p.status and p.status.name == "Success")
    clean_decl = sum(1 for p in clean_rows if p.status and p.status.name == "Declined")
    clean_iss = clean_n - clean_decl

    # also: exclude heavy multi-fail (≥SPAM_MIN creates, ok/n < 10%)
    heavy = {
        k: v
        for k, v in by_client.items()
        if v["n"] >= SPAM_MIN and (v["ok"] / v["n"] if v["n"] else 0) < 0.10
    }
    heavy_keys = set(heavy)
    heavy_rows = [p for p in rows if client_key(p) not in heavy_keys]
    heavy_n = len(heavy_rows)
    heavy_ok = sum(1 for p in heavy_rows if p.status and p.status.name == "Success")
    heavy_decl = sum(1 for p in heavy_rows if p.status and p.status.name == "Declined")
    heavy_iss = heavy_n - heavy_decl
    heavy_creates = sum(v["n"] for v in heavy.values())

    print(f"\n=== {label}  {start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%H:%M %Z')} ===")
    print(
        f"  create={created}  unique_clients={unique}  multi(≥2)={multi}  "
        f"creates/client={created / unique if unique else 0:.2f}"
    )
    print(
        f"  success={success}  declined={declined}  "
        f"cr→ok={pct(success, created)}  iss→ok={pct(success, issued)}"
    )
    print(
        f"  spam (≥{SPAM_MIN} create, 0 Success): "
        f"clients={len(spam_clients)}  creates={spam_creates}  "
        f"share={pct(spam_creates, created)}"
    )
    print(
        f"  WITHOUT spam: create={clean_n}  ok={clean_ok}  "
        f"cr→ok={pct(clean_ok, clean_n)}  iss→ok={pct(clean_ok, clean_iss)}"
    )
    print(
        f"  heavy (≥{SPAM_MIN}, ok-rate<10%): "
        f"clients={len(heavy)}  creates={heavy_creates}  share={pct(heavy_creates, created)}"
    )
    print(
        f"  WITHOUT heavy: create={heavy_n}  ok={heavy_ok}  "
        f"cr→ok={pct(heavy_ok, heavy_n)}  iss→ok={pct(heavy_ok, heavy_iss)}"
    )
    print(
        f"  bursts (same client, gap≤{BURST_SEC}s): "
        f"pairs={burst_pairs}  clients={len(burst_clients)}"
    )

    # top clients by create volume
    top = sorted(by_client.items(), key=lambda x: (-x[1]["n"], x[0]))[:TOP]
    print(f"  top clients by creates (TOP={TOP}):")
    print(
        f"    {'client_id':32}  {'n':>4}  {'ok':>3}  {'ok%':>6}  "
        f"{'amounts (top)':28}  {'gaps_sec'}"
    )
    for ck, c in top:
        gaps = []
        times = sorted(c["times"])
        for a, b in zip(times, times[1:]):
            gaps.append(int((b - a).total_seconds()))
        gap_s = ",".join(str(g) for g in gaps[:6]) if gaps else "-"
        if len(gaps) > 6:
            gap_s += ",…"
        amts = ", ".join(
            f"{a:g}×{n}" for a, n in c["amounts"].most_common(3)
        )
        print(
            f"    {ck[:32]:32}  {c['n']:4}  {c['ok']:3}  {pct(c['ok'], c['n']):>6}  "
            f"{amts[:28]:28}  {gap_s}"
        )

    if spam_clients:
        print(f"  spam candidates (≥{SPAM_MIN}, 0 ok):")
        for ck, c in sorted(spam_clients.items(), key=lambda x: -x[1]["n"])[:TOP]:
            amts = ", ".join(f"{a:g}×{n}" for a, n in c["amounts"].most_common(4))
            print(f"    {ck[:40]:40}  n={c['n']:3}  amounts=[{amts}]")

    # amount concentration
    print("  top amounts:")
    for amt, n in amounts.most_common(8):
        ok_amt = sum(
            1
            for p in rows
            if p.amount == amt and p.status and p.status.name == "Success"
        )
        print(
            f"    {amt:>12}  n={n:4}  share={pct(n, created)}  ok={ok_amt:3}  "
            f"ok%={pct(ok_amt, n)}"
        )

    return {
        "created": created,
        "success": success,
        "unique": unique,
        "spam_clients": len(spam_clients),
        "spam_creates": spam_creates,
        "clean_ok_pct": (100.0 * clean_ok / clean_n) if clean_n else 0.0,
        "raw_ok_pct": (100.0 * success / created) if created else 0.0,
        "heavy_creates": heavy_creates,
        "without_heavy_ok_pct": (100.0 * heavy_ok / heavy_n) if heavy_n else 0.0,
    }


def run() -> None:
    now = _now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    print("=" * 72)
    print(f"MOSTBET SPAM / CLIENT CHECK  merchant={MERCHANT}  now={now.isoformat()}")
    print(
        f"  focus={HOUR_FROM:02d}-{HOUR_TO:02d}  baseline=09-11  "
        f"SPAM_MIN={SPAM_MIN}  BURST_SEC={BURST_SEC}  DAYS={DAYS}  PS={PS or 'ALL'}"
    )
    print("=" * 72)

    summary = []
    for i in range(DAYS - 1, -1, -1):
        day = today - timedelta(days=i)
        for kind, h0, h1 in (
            ("FOCUS", HOUR_FROM, HOUR_TO),
            ("BASELINE", 9, 11),
        ):
            start = day + timedelta(hours=h0)
            end = day + timedelta(hours=h1)
            if start >= now:
                continue
            end = min(end, now)
            if end <= start:
                continue
            label = f"{kind} {day.strftime('%Y-%m-%d')} {h0:02d}-{h1:02d}"
            stats = analyze(label, start, end)
            summary.append((label, stats))

    print("\n=== SUMMARY (spam impact on cr→ok) ===")
    print(
        f"  {'window':28}  {'create':>6}  {'uniq':>5}  {'spam_n':>6}  "
        f"{'spam%':>6}  {'raw%':>6}  {'-spam%':>7}  {'-heavy%':>8}"
    )
    for label, s in summary:
        print(
            f"  {label:28}  {s['created']:6}  {s['unique']:5}  {s['spam_creates']:6}  "
            f"{pct(s['spam_creates'], s['created']):>6}  "
            f"{s['raw_ok_pct']:5.1f}%  {s['clean_ok_pct']:6.1f}%  "
            f"{s['without_heavy_ok_pct']:7.1f}%"
        )
    print("\nDONE")


run()
