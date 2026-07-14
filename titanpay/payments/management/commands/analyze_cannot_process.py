"""Массовый разбор Cannot process / Declined pay-in за период."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import (
    ExpayonePayInSession,
    FairpayPayInSession,
    PayIn,
    PayInTraceLog,
    ProtocolPayInSession,
)
from payments.psp_payin import _extract_upstream_error, psp_create_failure_reason_internal


@dataclass
class Row:
    pay_in_id: str
    created_at: str
    merchant: str
    merchant_order_id: str
    amount: str
    payment_system: str
    category: str
    provider: str
    routed_trader: str
    upstream_error: str
    detail: str


def _norm_err(text: str, *, max_len: int = 200) -> str:
    s = " ".join((text or "").split())
    return s[:max_len] if s else "—"


def _session_upstream(pay_in) -> tuple[str, str, str]:
    """provider, short error, raw detail."""
    for model, label in (
        (ProtocolPayInSession, "protocol"),
        (ExpayonePayInSession, "expayone"),
        (FairpayPayInSession, "fairpay"),
    ):
        try:
            session = model.objects.get(pay_in=pay_in)
        except model.DoesNotExist:
            continue
        cr = session.create_response or {}
        if not isinstance(cr, dict):
            continue
        detail = _extract_upstream_error(cr)
        if not detail and cr.get("error"):
            detail = str(cr.get("error"))
        upstream = cr.get("upstream")
        if not detail and isinstance(upstream, dict):
            detail = _extract_upstream_error(upstream)
        if not detail and cr.get("message"):
            detail = str(cr.get("message"))
        if detail:
            return label, _norm_err(detail), detail[:500]
        if cr:
            return label, "empty_or_unknown_response", str(cr)[:500]
    return "", "", ""


def _trace_routed_trader(pay_in) -> str:
    entry = (
        PayInTraceLog.objects.filter(pay_in=pay_in, note="after InOrder.create")
        .order_by("created_at")
        .first()
    )
    if entry and isinstance(entry.body, dict):
        return str(entry.body.get("trader") or "")
    return ""


def _trace_had_psp_api(pay_in) -> bool:
    return PayInTraceLog.objects.filter(
        pay_in=pay_in,
        note__in=("psp provider api", "psp provider fallback"),
    ).exists()


def _trace_psp_providers_tried(pay_in) -> list[str]:
    providers: list[str] = []
    for entry in PayInTraceLog.objects.filter(
        pay_in=pay_in,
        note__in=("psp provider api", "psp provider fallback"),
    ).order_by("created_at"):
        body = entry.body if isinstance(entry.body, dict) else {}
        p = body.get("provider")
        if p and (not providers or providers[-1] != p):
            providers.append(str(p))
    return providers


def classify_payin(pay_in) -> tuple[str, str, str, str]:
    """
    category, provider, routed_trader, upstream_error.
    category: routing_no_requisite | psp_api_fail | psp_no_session | unknown
    """
    order = pay_in.order
    routed = _trace_routed_trader(pay_in)
    if order is not None and order.status and order.status.name == "Cannot process":
        if not _trace_had_psp_api(pay_in):
            provider, err, _ = _session_upstream(pay_in)
            if provider:
                return "psp_api_fail", provider, routed, err
            if order.payment_details_id is None and not routed:
                return "routing_no_requisite", "", "", "роутинг не подобрал реквизит"
            if routed and not _trace_had_psp_api(pay_in):
                return "psp_no_trace", routed, routed, "нет записи psp provider api в trace"
        providers = _trace_psp_providers_tried(pay_in)
        provider, err, _ = _session_upstream(pay_in)
        if not provider and providers:
            provider = providers[-1]
        if not err or err == "—":
            err = psp_create_failure_reason_internal(pay_in)
        return "psp_api_fail", provider or (providers[-1] if providers else ""), routed, _norm_err(err)
    provider, err, _ = _session_upstream(pay_in)
    if provider:
        return "psp_api_fail", provider, routed, err
    return "unknown", "", routed, ""


def _amount_bucket(amount: Decimal) -> str:
    a = float(amount)
    if a < 10000:
        return "<10k"
    if a < 15000:
        return "10k-15k"
    if a < 20000:
        return "15k-20k"
    return "20k+"


def _max_consecutive_streak(timestamps_sorted) -> int:
    if not timestamps_sorted:
        return 0
    best = cur = 1
    for i in range(1, len(timestamps_sorted)):
        gap = (timestamps_sorted[i] - timestamps_sorted[i - 1]).total_seconds()
        if gap <= 120:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


class Command(BaseCommand):
    help = (
        "Агрегированный отчёт по Cannot process / Declined pay-in. "
        "Пример: analyze_cannot_process --merchant pandapay --hours 12"
    )
    def add_arguments(self, parser):
        parser.add_argument("--merchant", type=str, default="", help="username мерчанта, напр. pandapay")
        parser.add_argument("--ps", type=str, default="", help="фильтр PaymentSystem, напр. C2CKZT")
        parser.add_argument("--hours", type=float, default=12, help="окно назад от сейчас")
        parser.add_argument("--since", type=str, default="", help="YYYY-MM-DD HH:MM (UTC) вместо --hours")
        parser.add_argument("--until", type=str, default="", help="YYYY-MM-DD HH:MM (UTC)")
        parser.add_argument("--limit", type=int, default=5000)
        parser.add_argument("--json", type=str, default="", help="путь для JSON-отчёта")
        parser.add_argument("--samples", type=int, default=3, help="примеров pay_in_id на категорию")
    def handle(self, *args, **options):
        since, until = self._parse_window(options)
        rows = self._collect_rows(since, until, options)
        if not rows:
            self.stdout.write(self.style.WARNING("Нет Declined pay-in с Cannot process в выбранном окне."))
            return
        self._print_report(rows, options)
        if options["json"]:
            self._write_json(options["json"], rows, since, until)
    def _parse_window(self, options):
        until = timezone.now()
        if options["until"].strip():
            until = timezone.datetime.fromisoformat(options["until"].strip())
            if timezone.is_naive(until):
                until = timezone.make_aware(until)
        if options["since"].strip():
            since = timezone.datetime.fromisoformat(options["since"].strip())
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
        else:
            since = until - timedelta(hours=float(options["hours"]))
        return since, until
    def _collect_rows(self, since, until, options) -> list[Row]:
        qs = (
            PayIn.objects.filter(
                created_at__gte=since,
                created_at__lte=until,
                status__name="Declined",
                order__status__name="Cannot process",
            )
            .select_related(
                "merchant__user",
                "currency",
                "payment_system",
                "order",
                "order__status",
            )
            .order_by("created_at")
        )
        merchant = (options.get("merchant") or "").strip()
        if merchant:
            qs = qs.filter(merchant__user__username=merchant)
        ps_name = (options.get("ps") or "").strip()
        if ps_name:
            qs = qs.filter(payment_system__name__iexact=ps_name)
        limit = int(options["limit"])
        rows: list[Row] = []
        for pay_in in qs[:limit]:
            category, provider, routed, upstream = classify_payin(pay_in)
            rows.append(
                Row(
                    pay_in_id=str(pay_in.id),
                    created_at=pay_in.created_at.isoformat(sep=" ", timespec="seconds"),
                    merchant=pay_in.merchant.user.username if pay_in.merchant else "",
                    merchant_order_id=pay_in.merchant_order_id,
                    amount=str(pay_in.amount),
                    payment_system=pay_in.payment_system.name if pay_in.payment_system else "",
                    category=category,
                    provider=provider or "—",
                    routed_trader=routed or "—",
                    upstream_error=upstream or "—",
                    detail=psp_create_failure_reason_internal(pay_in),
                )
            )
        return rows
    def _print_report(self, rows: list[Row], options):
        since_ts = rows[0].created_at
        until_ts = rows[-1].created_at
        self.stdout.write(self.style.HTTP_INFO("\n=== Cannot process — сводка ==="))
        self.stdout.write(f"заявок:        {len(rows)}")
        self.stdout.write(f"период:        {since_ts} … {until_ts}")
        by_cat = Counter(r.category for r in rows)
        self.stdout.write(self.style.HTTP_INFO("\n--- По типу отказа ---"))
        for cat, n in by_cat.most_common():
            pct = 100.0 * n / len(rows)
            self.stdout.write(f"  {cat:22} {n:5}  ({pct:.1f}%)")
        psp_rows = [r for r in rows if r.category == "psp_api_fail"]
        if psp_rows:
            self.stdout.write(self.style.HTTP_INFO("\n--- PSP API (провайдер) ---"))
            for prov, n in Counter(r.provider for r in psp_rows).most_common():
                self.stdout.write(f"  {prov:12} {n}")
            self.stdout.write(self.style.HTTP_INFO("\n--- Топ ошибок upstream ---"))
            err_counter = Counter(_norm_err(r.upstream_error, max_len=120) for r in psp_rows)
            for err, n in err_counter.most_common(15):
                self.stdout.write(f"  [{n:4}] {err}")
            self.stdout.write(self.style.HTTP_INFO("\n--- Роутинг → трейдер (перед API) ---"))
            for tr, n in Counter(r.routed_trader for r in psp_rows).most_common():
                self.stdout.write(f"  {tr:12} {n}")
        self.stdout.write(self.style.HTTP_INFO("\n--- Сумма (bucket) ---"))
        for bucket, n in Counter(_amount_bucket(Decimal(r.amount)) for r in rows).most_common():
            self.stdout.write(f"  {bucket:10} {n}")
        self.stdout.write(self.style.HTTP_INFO("\n--- По часу (UTC) ---"))
        by_hour = Counter(r.created_at[:13] for r in rows)
        for hour, n in sorted(by_hour.items()):
            bar = "█" * min(n, 60)
            self.stdout.write(f"  {hour}  {n:4}  {bar}")
        timestamps = []
        for r in rows:
            dt = timezone.datetime.fromisoformat(r.created_at)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            timestamps.append(dt)
        if timestamps:
            streak = _max_consecutive_streak(timestamps)
            self.stdout.write(self.style.HTTP_INFO("\n--- Серии подряд (≤2 мин между заявками) ---"))
            self.stdout.write(f"  макс. серия: {streak} заявок")
        samples = int(options["samples"])
        self.stdout.write(self.style.HTTP_INFO(f"\n--- Примеры (payin_trace <id>) ---"))
        grouped: dict[tuple[str, str, str], list[Row]] = defaultdict(list)
        for r in rows:
            key = (r.category, r.provider, _norm_err(r.upstream_error, max_len=80))
            if len(grouped[key]) < samples:
                grouped[key].append(r)
        for (cat, prov, err), items in sorted(grouped.items(), key=lambda x: -len(x[1])):
            self.stdout.write(f"\n  [{cat}] provider={prov}")
            self.stdout.write(f"    err: {err}")
            for r in items:
                self.stdout.write(
                    f"    {r.created_at}  {r.amount} {r.payment_system}  "
                    f"trader={r.routed_trader}  id={r.pay_in_id}"
                )
        self.stdout.write(self.style.HTTP_INFO("\n--- Рекомендации ---"))
        self._hints(rows, psp_rows)
    def _hints(self, rows: list[Row], psp_rows: list[Row]):
        errs = " ".join(r.upstream_error.lower() for r in psp_rows)
        if "10000" in errs or "не меньше 10000" in errs:
            self.stdout.write(
                "  • ExpayOne min 10k: включите fallback на Protocol или отключите expayone на малых суммах."
            )
        if "busy" in errs or "not available" in errs or "не найдены" in errs:
            self.stdout.write(
                "  • Protocol/ExpayOne «busy/url»: проверьте callback whitelist и лимиты у провайдера."
            )
        routing_n = sum(1 for r in rows if r.category == "routing_no_requisite")
        if routing_n:
            self.stdout.write(
                f"  • routing_no_requisite: {routing_n} — diagnose_routing для типичной суммы."
            )
        self.stdout.write("  • Детально: python manage.py payin_trace <pay_in_id>")
        self.stdout.write("  • JSON: --json /tmp/cannot_process.json")
    def _write_json(self, path: str, rows: list[Row], since, until):
        payload = {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "total": len(rows),
            "rows": [r.__dict__ for r in rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f"\nJSON: {path}"))
