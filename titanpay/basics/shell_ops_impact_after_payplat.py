"""
Аналитика после отключения PayPlat / просадки Mostbet.

Сравнивает «до» и «после» по дням: create / issued / Success / iss→ok,
доли PSP, spam-срез, топ причин Declined (нет реквизита).

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_ops_impact_after_payplat.py

Опционально:
  DAYS=14                 # сколько дней назад смотреть
  CUTOFF=2026-11-07       # дата отключения PayPlat (MSK); иначе авто
  MERCHANTS=all           # all = все мерчи с трафиком; или csv
  MIN_CREATE=30           # мелких мерчей — одной строкой
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn

MSK = ZoneInfo("Europe/Moscow")
DAYS = int(os.environ.get("DAYS") or "14")
CUTOFF_RAW = (os.environ.get("CUTOFF") or "").strip()
MERCHANTS_RAW = (os.environ.get("MERCHANTS") or "all").strip()
MIN_CREATE = int(os.environ.get("MIN_CREATE") or "30")
Q2 = Decimal("0.01")
SPAM_MIN = int(os.environ.get("SPAM_MIN") or "3")


def money(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def pct(num, den) -> Decimal | None:
    if not den:
        return None
    return (Decimal(num) * Decimal("100") / Decimal(den)).quantize(Q2)


def pct_s(num, den) -> str:
    p = pct(num, den)
    return f"{p}%" if p is not None else "n/a"


def provider_of(pay) -> str:
    order = getattr(pay, "order", None)
    if order is None or not getattr(order, "payment_details_id", None):
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username or "(no_trader)"
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def client_key(pay) -> str:
    if getattr(pay, "client_id", None) is None:
        return "(no_client)"
    client = getattr(pay, "client", None)
    cid = (getattr(client, "client_id", None) or "").strip() if client else ""
    return cid or f"(id={pay.client_id})"


def day_key(dt) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%d")


now = timezone.now().astimezone(MSK)
since = now - timedelta(days=DAYS)

qs = (
    PayIn.objects.filter(created_at__gte=since)
    .select_related(
        "status",
        "merchant__user",
        "client",
        "order__payment_details__group__trader__user",
    )
    .order_by("created_at")
)
want_all = MERCHANTS_RAW.lower() in {"", "all", "*"}
MERCHANTS_FILTER = []
if not want_all:
    MERCHANTS_FILTER = [p.strip() for p in MERCHANTS_RAW.split(",") if p.strip()]
    qs = qs.filter(merchant__user__username__in=MERCHANTS_FILTER)

pays = list(qs.iterator(chunk_size=1000))
# Discover merchants present in window (sorted by create volume desc).
_vol: dict[str, int] = defaultdict(int)
for p in pays:
    if p.merchant_id and p.merchant.user_id:
        _vol[p.merchant.user.username] += 1
MERCHANTS = [n for n, _ in sorted(_vol.items(), key=lambda x: -x[1])]
if MERCHANTS_FILTER:
    MERCHANTS = [n for n in MERCHANTS if n in set(MERCHANTS_FILTER)]

# --- auto-detect PayPlat cutoff: last day when payplat share of issued >= 20% ---
by_day_psp_iss: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
for p in pays:
    st = p.status.name if p.status_id else ""
    if st == "Declined":
        continue
    psp = provider_of(p)
    by_day_psp_iss[day_key(p.created_at)][psp] += 1

cutoff = None
if CUTOFF_RAW:
    cutoff = datetime.strptime(CUTOFF_RAW, "%Y-%m-%d").replace(tzinfo=MSK)
else:
    # find last day with payplat1 issued share >= 15% and issued>=30
    days_sorted = sorted(by_day_psp_iss.keys())
    last_payplat_day = None
    for d in days_sorted:
        cell = by_day_psp_iss[d]
        total = sum(cell.values())
        pp = cell.get("payplat1", 0)
        if total >= 30 and pct(pp, total) is not None and pct(pp, total) >= Decimal("15"):
            last_payplat_day = d
    if last_payplat_day:
        # cutoff = next day after last meaningful payplat day
        cutoff = datetime.strptime(last_payplat_day, "%Y-%m-%d").replace(tzinfo=MSK) + timedelta(days=1)
    else:
        cutoff = now - timedelta(days=3)

print("=" * 78)
print(f"OPS IMPACT  window={since.date()} → {now.date()} MSK  DAYS={DAYS}")
print(f"merchants={'ALL → ' if want_all else ''}{','.join(MERCHANTS) or '(none)'}")
print(f"CUTOFF (after PayPlat collapse) = {cutoff.date()} MSK")
if not CUTOFF_RAW:
    print("  (auto; override: CUTOFF=YYYY-MM-DD)")
print(f"MIN_CREATE detail threshold = {MIN_CREATE}")
print("=" * 78)

# Platform-wide BEFORE/AFTER (all merchants in list)
print(f"\n{'=' * 78}\nPLATFORM TOTAL (selected merchants)\n{'=' * 78}")


def bucket(pay) -> str:
    return "AFTER" if pay.created_at.astimezone(MSK) >= cutoff else "BEFORE"


def analyze(label: str, subset: list) -> dict:
    created = len(subset)
    declined = sum(1 for p in subset if p.status_id and p.status.name == "Declined")
    success = sum(1 for p in subset if p.status_id and p.status.name == "Success")
    issued = created - declined
    usd_ok = money(sum((p.order.usd_amount if p.order_id and p.order else 0) for p in subset if p.status_id and p.status.name == "Success"))
    by_psp = defaultdict(lambda: {"c": 0, "d": 0, "ok": 0})
    by_client = defaultdict(lambda: {"n": 0, "ok": 0})
    for p in subset:
        st = p.status.name if p.status_id else ""
        psp = provider_of(p)
        by_psp[psp]["c"] += 1
        if st == "Declined":
            by_psp[psp]["d"] += 1
        elif st == "Success":
            by_psp[psp]["ok"] += 1
        ck = client_key(p)
        by_client[ck]["n"] += 1
        if st == "Success":
            by_client[ck]["ok"] += 1
    spam = {k: v for k, v in by_client.items() if v["n"] >= SPAM_MIN and v["ok"] == 0}
    spam_creates = sum(v["n"] for v in spam.values())
    clean = [p for p in subset if client_key(p) not in spam]
    clean_ok = sum(1 for p in clean if p.status_id and p.status.name == "Success")
    clean_decl = sum(1 for p in clean if p.status_id and p.status.name == "Declined")
    clean_iss = len(clean) - clean_decl

    print(f"\n--- {label} ---")
    print(
        f"  create={created}  issued={issued}  success={success}  "
        f"declined={declined}  USD_success≈{usd_ok}"
    )
    print(
        f"  create→ok={pct_s(success, created)}  iss→ok={pct_s(success, issued)}  "
        f"issue_rate={pct_s(issued, created)}"
    )
    print(
        f"  spam clients≥{SPAM_MIN}/0ok: n={len(spam)} creates={spam_creates} "
        f"share={pct_s(spam_creates, created)}  "
        f"iss→ok без спама={pct_s(clean_ok, clean_iss)}"
    )
    ranked = sorted(
        by_psp.items(),
        key=lambda x: -(x[1]["c"] - x[1]["d"]),
    )
    print("  PSP (issued share / iss→ok):")
    for psp, c in ranked[:12]:
        iss = c["c"] - c["d"]
        if iss <= 0 and c["c"] < 5:
            continue
        print(
            f"    {psp:16} create={c['c']:5} iss={iss:5} ok={c['ok']:5} "
            f"iss_share={pct_s(iss, issued):>7}  iss→ok={pct_s(c['ok'], iss)}"
        )
    return {
        "created": created,
        "issued": issued,
        "success": success,
        "declined": declined,
        "iss_ok": pct(success, issued),
        "issue_rate": pct(issued, created),
        "usd_ok": usd_ok,
        "spam_share": pct(spam_creates, created),
        "clean_iss_ok": pct(clean_ok, clean_iss),
        "by_psp": by_psp,
    }


# Platform-wide first
_plat_before = [p for p in pays if bucket(p) == "BEFORE"]
_plat_after = [p for p in pays if bucket(p) == "AFTER"]
analyze(f"PLATFORM BEFORE {cutoff.date()}", _plat_before)
analyze(f"PLATFORM AFTER  {cutoff.date()}", _plat_after)

# Per merchant BEFORE/AFTER
advice_bits: list[str] = []
summary_rows: list[tuple] = []
for merchant in MERCHANTS:
    m_pays = [p for p in pays if p.merchant_id and p.merchant.user.username == merchant]
    if not m_pays:
        print(f"\n=== {merchant}: no data ===")
        continue
    before = [p for p in m_pays if bucket(p) == "BEFORE"]
    after = [p for p in m_pays if bucket(p) == "AFTER"]
    if len(m_pays) < MIN_CREATE:
        # compact one-liner for tiny merchants
        b_ok = sum(1 for p in before if p.status_id and p.status.name == "Success")
        b_iss = len(before) - sum(1 for p in before if p.status_id and p.status.name == "Declined")
        a_ok = sum(1 for p in after if p.status_id and p.status.name == "Success")
        a_iss = len(after) - sum(1 for p in after if p.status_id and p.status.name == "Declined")
        print(
            f"\n=== {merchant} (small n={len(m_pays)}): "
            f"before iss→ok={pct_s(b_ok, b_iss)} after iss→ok={pct_s(a_ok, a_iss)} ==="
        )
        summary_rows.append(
            (merchant, len(before), len(after), pct(b_ok, b_iss), pct(a_ok, a_iss))
        )
        continue
    print(f"\n{'=' * 78}\nMERCHANT {merchant}\n{'=' * 78}")
    b = analyze(f"{merchant} BEFORE {cutoff.date()}", before)
    a = analyze(f"{merchant} AFTER  {cutoff.date()}", after)
    summary_rows.append(
        (merchant, b["created"], a["created"], b["iss_ok"], a["iss_ok"])
    )

    # day series
    by_day = defaultdict(lambda: {"c": 0, "d": 0, "ok": 0})
    for p in m_pays:
        d = day_key(p.created_at)
        st = p.status.name if p.status_id else ""
        by_day[d]["c"] += 1
        if st == "Declined":
            by_day[d]["d"] += 1
        elif st == "Success":
            by_day[d]["ok"] += 1
    print(f"\n  Day series {merchant} (create / issued / ok / iss→ok):")
    for d in sorted(by_day.keys()):
        cell = by_day[d]
        iss = cell["c"] - cell["d"]
        mark = " <<CUTOFF" if d == cutoff.date().isoformat() else ""
        print(
            f"    {d}  c={cell['c']:5} iss={iss:5} ok={cell['ok']:5} "
            f"iss→ok={pct_s(cell['ok'], iss)}{mark}"
        )

    if b["iss_ok"] is not None and a["iss_ok"] is not None:
        drop = b["iss_ok"] - a["iss_ok"]
        print(f"\n  Δ iss→ok: {b['iss_ok']}% → {a['iss_ok']}%  (Δ {drop:+} pp)")
        if drop >= Decimal("5"):
            advice_bits.append(
                f"{merchant}: iss→ok упал на {drop}pp после cutoff — каскад без PayPlat хуже держит конверсию."
            )
    if a["issue_rate"] is not None and b["issue_rate"] is not None:
        idrop = b["issue_rate"] - a["issue_rate"]
        if idrop >= Decimal("5"):
            advice_bits.append(
                f"{merchant}: issue_rate упал на {idrop}pp — чаще Cannot process / нет реквизита."
            )
    if a["spam_share"] is not None and a["spam_share"] >= Decimal("20"):
        advice_bits.append(
            f"{merchant}: spam share {a['spam_share']}% после cutoff — режь спам-клиентов / пороги, смотри clean iss→ok."
        )
    # who took payplat share
    b_iss = {k: v["c"] - v["d"] for k, v in b["by_psp"].items()}
    a_iss = {k: v["c"] - v["d"] for k, v in a["by_psp"].items()}
    b_total = sum(max(0, x) for x in b_iss.values()) or 1
    a_total = sum(max(0, x) for x in a_iss.values()) or 1
    print("\n  Share shift (issued %):")
    names = sorted(set(b_iss) | set(a_iss), key=lambda n: -(a_iss.get(n, 0)))
    for n in names[:10]:
        if n == "(no_req)":
            continue
        print(
            f"    {n:16} before={pct_s(b_iss.get(n, 0), b_total):>7}  "
            f"after={pct_s(a_iss.get(n, 0), a_total):>7}"
        )


print("\n" + "=" * 78)
print("SUMMARY iss→ok by merchant (BEFORE → AFTER)")
print("=" * 78)
print(f"  {'merchant':16} {'c_bef':>7} {'c_aft':>7} {'iss→ok bef':>12} {'iss→ok aft':>12} {'Δpp':>8}")
for name, cb, ca, pb, pa in summary_rows:
    dpp = ""
    if pb is not None and pa is not None:
        dpp = f"{(pa - pb):+.2f}"
    print(
        f"  {name:16} {cb:7} {ca:7} "
        f"{(str(pb) + '%') if pb is not None else 'n/a':>12} "
        f"{(str(pa) + '%') if pa is not None else 'n/a':>12} {dpp:>8}"
    )

print("\n" + "=" * 78)
print("СОВЕТЫ (по данным выше + типовой ops)")
print("=" * 78)
if not advice_bits:
    advice_bits.append("Резкого провала iss→ok по порогам не видно — смотри day series и issue_rate.")
for i, line in enumerate(advice_bits, 1):
    print(f"  {i}. {line}")

print(
    """
  Практический план:
  1) Каскад: подними в SHARE/PRIORITY тех, у кого AFTER iss→ok выше (часто patriot/gipay/visionx),
     PayPlat оставь на 99 / убери из SHARE пока не заживёт.
  2) Mostbet: если clean iss→ok ок, а raw плохой — это спам/нагрузка, не «мёртвые» PSP.
     Если clean тоже упал — меняй доли PSP и лимиты сумм.
  3) Issue_rate↓: смотри diagnose_routing + empty cascade (балансы PSP / credit_limit / status групп).
  4) Живые трейдеры (resdfe): manual_mode + amount_diff/interval; они должны быть ПЕРЕД PSP.
  5) Не включай Mostbet обратно, пока day iss→ok AFTER не стабильно ≥ порога алертов
     (сейчас ADMIN_ALERT_CONV_ISSUED_PCT_MIN) на объёме ≥20 create / 15 мин.
  6) Сравни USD_success BEFORE vs AFTER — если оборот упал сильнее конверсии,
     проблема в выдаче/доле трафика, не только в «качестве» платежей.

  Дополнительно:
    docker compose exec -T -e DAYS=3 app python manage.py shell \\
      < titanpay/basics/shell_diagnose_psp_conversion.py
    docker compose exec -T app python manage.py diagnose_routing mostbet --ps C2CKZT --amount 5000 --ftd false
"""
)
print("DONE")
