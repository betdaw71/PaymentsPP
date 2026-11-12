"""Полный недельный анализ Melbet redirect: объём, пики, реквизиты, PSP, платёжная страница."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.integrations.melbet.amount_probe import is_melbet_deposit_allocated
from payments.models import PayIn, PayInTraceLog
from payments.psp_payin import (
    _PSP_SESSION_PROVIDER_FIELDS,
    _extract_upstream_error,
    classify_payin_decline,
    psp_create_failure_reason_internal,
    psp_external_reference,
)
from payments.payment_page_assets import payment_page_public_base


def _parse_dt(raw: str) -> datetime:
    raw = raw.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {raw!r}")


def _pct(part: int, whole: int) -> str:
    if not whole:
        return "0.0%"
    return f"{part * 100 / whole:.1f}%"


def _norm_err(text: str, *, max_len: int = 160) -> str:
    return " ".join((text or "").split())[:max_len] or "—"


def _session_upstream_detail(pay_in: PayIn) -> tuple[str, str]:
    """provider label, error snippet."""
    import importlib

    for model_path, provider, _field in _PSP_SESSION_PROVIDER_FIELDS:
        module_name, class_name = model_path.rsplit(".", 1)
        model = getattr(importlib.import_module(module_name), class_name)
        session = model.objects.filter(pay_in=pay_in).first()
        if session is None:
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
            return provider, _norm_err(detail)
        if cr.get("deal_uuid") or cr.get("id") or cr.get("provider_payment_id"):
            return provider, "deal_created"
        if cr:
            return provider, _norm_err(str(cr.get("error") or cr)[:160])
    return "", ""


def _trace_routed_trader(pay_in: PayIn) -> str:
    for note in ("after InOrder.create", "routing"):
        entry = (
            PayInTraceLog.objects.filter(pay_in=pay_in, note=note)
            .order_by("created_at")
            .first()
        )
        if entry and isinstance(entry.body, dict):
            trader = entry.body.get("trader")
            if trader:
                return str(trader)
    return ""


def _trace_psp_providers(pay_in: PayIn) -> list[str]:
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


def _had_amount_probe(pay_in: PayIn) -> bool:
    return PayInTraceLog.objects.filter(pay_in=pay_in).filter(
        note__icontains="amount probe"
    ).exists()


def _classify_outcome(pay_in: PayIn) -> str:
    ps = pay_in.status.name if pay_in.status else "?"
    order = pay_in.order
    os_name = order.status.name if order and order.status else "?"

    if ps == "Success":
        return "success"
    if ps == "Declined":
        if os_name == "Cannot process":
            return "declined_no_requisites"
        if os_name == "Cancelled":
            return "declined_cancelled"
        return "declined_other"
    if ps == "Expired" or os_name == "Expired":
        return "expired"
    if ps == "Failed":
        return "failed"
    if os_name == "Money sent by user":
        return "user_sent_money"
    if os_name == "Arbitrage":
        return "arbitrage"
    if os_name == "Completed":
        return "completed_inorder"
    if is_melbet_deposit_allocated(pay_in):
        return "requisites_issued_waiting"
    if ps == "In Progress" and os_name == "Cannot process":
        return "declined_no_requisites"
    return "other"


@dataclass
class PayInRow:
    pay_in_id: str
    created_at: str
    merchant_order_id: str
    amount: str
    melbet_method: str
    outcome: str
    payin_status: str
    inorder_status: str
    trader: str
    psp_provider: str
    psp_error: str
    decline_code: str
    amount_probe: bool
    requisites_issued: bool


@dataclass
class Report:
    window_start: str
    window_end: str
    merchant: str
    payment_system: str
    total_deposits: int = 0
    api_http_201: int = 0
    api_http_400_validation: int = 0
    api_http_400_declined: int = 0
    outcome_counts: dict[str, int] = field(default_factory=dict)
    requisites_issued: int = 0
    declined_no_requisites: int = 0
    hourly_counts: dict[str, int] = field(default_factory=dict)
    peak_minute: str = ""
    peak_minute_count: int = 0
    avg_per_hour: float = 0.0
    provider_failures: dict[str, int] = field(default_factory=dict)
    provider_errors: dict[str, int] = field(default_factory=dict)
    trader_counts: dict[str, int] = field(default_factory=dict)
    decline_codes: dict[str, int] = field(default_factory=dict)
    melbet_methods: dict[str, int] = field(default_factory=dict)
    amount_probe_count: int = 0
    amount_buckets: dict[str, int] = field(default_factory=dict)
    funnel: dict[str, int] = field(default_factory=dict)
    payment_page: dict[str, Any] = field(default_factory=dict)
    samples: dict[str, list[dict]] = field(default_factory=dict)


def _amount_bucket(amount: Decimal) -> str:
    a = float(amount)
    if a < 5000:
        return "<5k"
    if a < 10000:
        return "5k-10k"
    if a < 15000:
        return "10k-15k"
    if a < 20000:
        return "15k-20k"
    if a < 50000:
        return "20k-50k"
    return "50k+"


class Command(BaseCommand):
    help = (
        "Полный анализ Melbet redirect за период: объём, пики, реквизиты, PSP, конверсия платёжной страницы. "
        "Пример: analyze_melbet_week --merchant melbet --days 7"
    )

    def add_arguments(self, parser):
        parser.add_argument("--merchant", default="melbet", help="username (melbet / melbet_test)")
        parser.add_argument("--ps", default="C2CKZT", help="фильтр payment_system")
        parser.add_argument("--days", type=float, default=7, help="окно назад от сейчас")
        parser.add_argument("--since", default="", help="YYYY-MM-DD HH:MM")
        parser.add_argument("--until", default="", help="YYYY-MM-DD HH:MM")
        parser.add_argument("--json", default="", help="сохранить JSON-отчёт в файл")
        parser.add_argument("--samples", type=int, default=5, help="примеров на категорию")

    def handle(self, *args, **options):
        since, until = self._window(options)
        merchant = options["merchant"].strip()
        ps_name = (options.get("ps") or "").strip()

        payins = list(self._query_payins(since, until, merchant, ps_name))
        report = self._build_report(payins, since, until, merchant, ps_name, options)
        self._print_report(report, options)
        if options["json"]:
            self._write_json(options["json"], report)

    def _window(self, options) -> tuple[datetime, datetime]:
        if options["since"].strip():
            start = _parse_dt(options["since"])
            end = _parse_dt(options["until"]) if options["until"].strip() else timezone.now()
            return start, end
        end = timezone.now()
        start = end - timedelta(days=float(options["days"]))
        return start, end

    def _query_payins(self, since: datetime, until: datetime, merchant: str, ps_name: str):
        qs = (
            PayIn.objects.filter(
                created_at__gte=since,
                created_at__lt=until,
                melbet_session__isnull=False,
                merchant__user__username=merchant,
            )
            .select_related(
                "status",
                "currency",
                "payment_system",
                "merchant__user",
                "order__status",
                "order__payment_details__group__trader__user",
                "melbet_session",
            )
            .order_by("created_at")
        )
        if ps_name:
            qs = qs.filter(payment_system__name__iexact=ps_name)
        return qs

    def _api_trace_stats(self, since: datetime, until: datetime, merchant: str) -> dict[str, int]:
        base = PayInTraceLog.objects.filter(
            created_at__gte=since,
            created_at__lt=until,
            merchant__user__username=merchant,
            note="melbet deposit",
            direction="merchant_request",
        )
        requests = base.count()
        responses = PayInTraceLog.objects.filter(
            created_at__gte=since,
            created_at__lt=until,
            merchant__user__username=merchant,
            note__in=("melbet deposit ok", "melbet deposit error"),
            direction="merchant_response",
        )
        ok = responses.filter(status_code=201, note="melbet deposit ok").count()
        err = responses.filter(note="melbet deposit error")
        validation = err.filter(status_code=400).count()
        return {
            "requests": requests,
            "http_201": ok,
            "http_400": err.count(),
            "http_400_validation": validation,
        }

    def _build_report(
        self,
        payins: list[PayIn],
        since: datetime,
        until: datetime,
        merchant: str,
        ps_name: str,
        options,
    ) -> Report:
        report = Report(
            window_start=since.isoformat(),
            window_end=until.isoformat(),
            merchant=merchant,
            payment_system=ps_name,
            total_deposits=len(payins),
        )
        api_stats = self._api_trace_stats(since, until, merchant)
        report.api_http_201 = api_stats["http_201"]
        report.api_http_400_validation = api_stats["http_400_validation"]
        report.api_http_400_declined = max(0, api_stats["http_400"] - api_stats["http_400_validation"])

        minute_counter: Counter[str] = Counter()
        rows: list[PayInRow] = []
        samples: dict[str, list[dict]] = defaultdict(list)
        sample_limit = int(options["samples"])

        for p in payins:
            outcome = _classify_outcome(p)
            report.outcome_counts[outcome] = report.outcome_counts.get(outcome, 0) + 1

            allocated = is_melbet_deposit_allocated(p)
            if allocated:
                report.requisites_issued += 1
            if outcome == "declined_no_requisites":
                report.declined_no_requisites += 1

            trader = _trace_routed_trader(p)
            if trader:
                report.trader_counts[trader] = report.trader_counts.get(trader, 0) + 1

            psp_provider, psp_error = _session_upstream_detail(p)
            if not psp_provider:
                ext = psp_external_reference(p)
                if ext:
                    psp_provider = ext.get("psp_provider", "")
            if not psp_provider:
                tried = _trace_psp_providers(p)
                if tried:
                    psp_provider = tried[-1]

            if outcome == "declined_no_requisites":
                label = psp_provider or trader or "routing"
                report.provider_failures[label] = report.provider_failures.get(label, 0) + 1
                err_key = psp_error or psp_create_failure_reason_internal(p)
                report.provider_errors[_norm_err(err_key, max_len=120)] = (
                    report.provider_errors.get(_norm_err(err_key, max_len=120), 0) + 1
                )
                code = classify_payin_decline(p)
                report.decline_codes[code] = report.decline_codes.get(code, 0) + 1

            method = ""
            if hasattr(p, "melbet_session") and p.melbet_session:
                method = p.melbet_session.melbet_method or ""
            if method:
                report.melbet_methods[method] = report.melbet_methods.get(method, 0) + 1

            probe = _had_amount_probe(p)
            if probe:
                report.amount_probe_count += 1

            report.amount_buckets[_amount_bucket(p.amount)] = (
                report.amount_buckets.get(_amount_bucket(p.amount), 0) + 1
            )

            hour_key = p.created_at.strftime("%Y-%m-%d %H:00")
            report.hourly_counts[hour_key] = report.hourly_counts.get(hour_key, 0) + 1
            minute_counter[p.created_at.strftime("%Y-%m-%d %H:%M")] += 1

            row = PayInRow(
                pay_in_id=str(p.id),
                created_at=p.created_at.isoformat(),
                merchant_order_id=p.merchant_order_id or "",
                amount=str(p.amount),
                melbet_method=method,
                outcome=outcome,
                payin_status=p.status.name if p.status else "?",
                inorder_status=p.order.status.name if p.order and p.order.status else "?",
                trader=trader,
                psp_provider=psp_provider,
                psp_error=psp_error,
                decline_code=classify_payin_decline(p) if outcome == "declined_no_requisites" else "",
                amount_probe=probe,
                requisites_issued=allocated,
            )
            rows.append(row)
            if len(samples[outcome]) < sample_limit:
                samples[outcome].append(asdict(row))

        if minute_counter:
            peak_minute, peak_count = minute_counter.most_common(1)[0]
            report.peak_minute = peak_minute
            report.peak_minute_count = peak_count

        hours_span = max(1, (until - since).total_seconds() / 3600)
        report.avg_per_hour = len(payins) / hours_span

        self._build_funnel(report, payins)
        self._build_payment_page_section(report, payins, since, until)
        report.samples = dict(samples)
        return report

    def _build_funnel(self, report: Report, payins: list[PayIn]) -> None:
        total = len(payins)
        issued = report.requisites_issued
        sent = report.outcome_counts.get("user_sent_money", 0) + report.outcome_counts.get("arbitrage", 0)
        success = report.outcome_counts.get("success", 0)
        expired = report.outcome_counts.get("expired", 0)
        waiting = report.outcome_counts.get("requisites_issued_waiting", 0)
        declined = report.declined_no_requisites

        report.funnel = {
            "deposit_created": total,
            "requisites_issued": issued,
            "declined_no_requisites": declined,
            "waiting_on_page": waiting,
            "user_clicked_paid": sent,
            "success": success,
            "expired": expired,
        }

    def _build_payment_page_section(
        self, report: Report, payins: list[PayIn], since: datetime, until: datetime
    ) -> None:
        issued_payins = [p for p in payins if is_melbet_deposit_allocated(p)]
        issued_n = len(issued_payins)
        sent_n = sum(
            1
            for p in issued_payins
            if p.order
            and p.order.status
            and p.order.status.name in ("Money sent by user", "Arbitrage", "Completed")
        )
        success_n = sum(1 for p in issued_payins if p.status and p.status.name == "Success")
        expired_n = sum(
            1
            for p in issued_payins
            if (p.status and p.status.name == "Expired")
            or (p.order and p.order.status and p.order.status.name == "Expired")
        )
        still_waiting = sum(1 for p in issued_payins if _classify_outcome(p) == "requisites_issued_waiting")

        stale_threshold = timezone.now() - timedelta(hours=2)
        stale_waiting = sum(
            1
            for p in issued_payins
            if _classify_outcome(p) == "requisites_issued_waiting" and p.created_at < stale_threshold
        )

        no_requisites_on_page = sum(
            1
            for p in payins
            if p.status
            and p.status.name == "In Progress"
            and p.order
            and p.order.status
            and p.order.status.name == "New"
            and not is_melbet_deposit_allocated(p)
        )

        report.payment_page = {
            "payment_page_base": payment_page_public_base(),
            "public_api_url": getattr(settings, "PUBLIC_API_URL", ""),
            "amount_probe_enabled": getattr(settings, "MELBET_AMOUNT_PROBE_ENABLED", None),
            "issued_with_requisites": issued_n,
            "still_waiting_on_page": still_waiting,
            "stale_waiting_over_2h": stale_waiting,
            "user_clicked_paid": sent_n,
            "conversion_paid_vs_issued": _pct(sent_n, issued_n),
            "success_vs_issued": _pct(success_n, issued_n),
            "success_vs_paid_click": _pct(success_n, sent_n),
            "expired_vs_issued": _pct(expired_n, issued_n),
            "in_progress_without_requisites": no_requisites_on_page,
            "interpretation": [],
        }

        interp: list[str] = report.payment_page["interpretation"]
        if issued_n == 0 and report.total_deposits > 0:
            interp.append(
                "Критично: ни одной выдачи реквизитов — проблема роутинга/PSP, платёжная страница не получает данных."
            )
        if report.declined_no_requisites > report.total_deposits * 0.5:
            interp.append(
                f"Высокий отказ на create ({_pct(report.declined_no_requisites, report.total_deposits)}): "
                "мерчант получает 400 до редиректа — смотрите provider_errors и decline_codes."
            )
        if issued_n > 0 and sent_n / issued_n < 0.15:
            interp.append(
                f"Низкая конверсия «нажал Оплатил» ({_pct(sent_n, issued_n)} от выданных реквизитов): "
                "возможны UX-проблемы платёжной страницы, таймаут, непонятные реквизиты или Kaspi/Halyk deeplink."
            )
        if issued_n > 0 and success_n / issued_n < 0.05 and sent_n > 0:
            interp.append(
                f"Пользователи нажимают «Оплатил» ({sent_n}), но Success мало ({success_n}): "
                "задержка PSP webhook, ручная проверка или несовпадение суммы."
            )
        if stale_waiting > issued_n * 0.3 and issued_n > 10:
            interp.append(
                f"Много зависших In Progress ({stale_waiting} старше 2ч): пользователи открывают redirect_url, "
                "но не завершают оплату (или не доходят до страницы)."
            )
        if report.amount_probe_count > report.total_deposits * 0.2:
            interp.append(
                f"Amount probe активен на {report.amount_probe_count} заявках — проверьте, не ломает ли probe "
                "успешные PSP-сессии (см. shell_diagnose_melbet_outage.py)."
            )
        if no_requisites_on_page > 0:
            interp.append(
                f"{no_requisites_on_page} pay-in In Progress без реквизитов — баг: redirect выдан, obtain вернёт пусто."
            )
        if not interp:
            interp.append("Явных системных аномалий по воронке не найдено — смотрите почасовые пики и PSP errors.")

    def _print_report(self, report: Report, options) -> None:
        w = self.style.HTTP_INFO
        e = self.style.ERROR
        s = self.style.SUCCESS

        self.stdout.write(w("\n" + "=" * 76))
        self.stdout.write(w("MELBET WEEKLY ANALYSIS"))
        self.stdout.write(f"merchant:        {report.merchant}")
        self.stdout.write(f"payment_system:  {report.payment_system or '(all)'}")
        self.stdout.write(f"window:          {report.window_start} .. {report.window_end}")
        self.stdout.write(f"duration:        {(datetime.fromisoformat(report.window_end) - datetime.fromisoformat(report.window_start)).days:.1f} days")

        self.stdout.write(w("\n--- 1. ОБЪЁМ ЗАЯВОК ---"))
        self.stdout.write(f"  PayIn создано (melbet_session):  {report.total_deposits}")
        self.stdout.write(f"  API trace melbet deposit 201:    {report.api_http_201}")
        self.stdout.write(f"  API trace 400 (validation):      {report.api_http_400_validation}")
        self.stdout.write(f"  API trace 400 (declined):        {report.api_http_400_declined}")
        self.stdout.write(f"  Среднее в час:                   {report.avg_per_hour:.2f}")
        self.stdout.write(f"  Пик (1 минута):                  {report.peak_minute} → {report.peak_minute_count} заявок")

        self.stdout.write(w("\n--- 2. ПОЧАСОВОЕ РАСПРЕДЕЛЕНИЕ (топ-15) ---"))
        for hour, cnt in sorted(report.hourly_counts.items(), key=lambda x: -x[1])[:15]:
            bar = "#" * min(cnt, 40)
            self.stdout.write(f"  {hour}  {cnt:4}  {bar}")

        self.stdout.write(w("\n--- 3. ВОРОНКА ---"))
        f = report.funnel
        t = f.get("deposit_created", 0) or 1
        self.stdout.write(f"  Заявки Melbet (deposit):     {f.get('deposit_created', 0)}")
        self.stdout.write(
            s(f"  Реквизиты выданы:            {f.get('requisites_issued', 0)} ({_pct(f.get('requisites_issued', 0), t)})")
        )
        self.stdout.write(
            e(f"  Отказ без реквизитов:         {f.get('declined_no_requisites', 0)} ({_pct(f.get('declined_no_requisites', 0), t)})")
        )
        self.stdout.write(f"  Ждут на платёжной странице:  {f.get('waiting_on_page', 0)}")
        self.stdout.write(f"  Нажали «Оплатил» (sent):     {f.get('user_clicked_paid', 0)}")
        self.stdout.write(f"  Success:                     {f.get('success', 0)}")
        self.stdout.write(f"  Expired:                     {f.get('expired', 0)}")

        self.stdout.write(w("\n--- 4. ИСХОДЫ (детально) ---"))
        for outcome, cnt in sorted(report.outcome_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {outcome:28} {cnt:5}  ({_pct(cnt, report.total_deposits)})")

        self.stdout.write(w("\n--- 5. ОТКАЗЫ: ПРОВАЙДЕР / ТРЕЙДЕР ---"))
        if report.provider_failures:
            for label, cnt in sorted(report.provider_failures.items(), key=lambda x: -x[1])[:15]:
                self.stdout.write(f"  {label:24} {cnt}")
        else:
            self.stdout.write("  (нет declined_no_requisites в окне)")

        self.stdout.write(w("\n--- 6. ТОП ОШИБОК PSP / РОУТИНГА ---"))
        for err, cnt in sorted(report.provider_errors.items(), key=lambda x: -x[1])[:12]:
            self.stdout.write(f"  [{cnt:4}] {err}")

        self.stdout.write(w("\n--- 7. DECLINE CODES (внутренние) ---"))
        for code, cnt in sorted(report.decline_codes.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {code:28} {cnt}")

        self.stdout.write(w("\n--- 8. ТРЕЙДЕРЫ (все заявки) ---"))
        for trader, cnt in sorted(report.trader_counts.items(), key=lambda x: -x[1])[:15]:
            self.stdout.write(f"  {trader:24} {cnt}")

        self.stdout.write(w("\n--- 9. MELBET METHOD ---"))
        for method, cnt in sorted(report.melbet_methods.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {method or '(default)':24} {cnt}")

        self.stdout.write(w("\n--- 10. СУММЫ ---"))
        for bucket, cnt in sorted(report.amount_buckets.items()):
            self.stdout.write(f"  {bucket:12} {cnt}")

        self.stdout.write(w("\n--- 11. AMOUNT PROBE ---"))
        self.stdout.write(f"  заявок с amount probe в trace: {report.amount_probe_count}")

        pp = report.payment_page
        self.stdout.write(w("\n--- 12. ПЛАТЁЖНАЯ СТРАНИЦА (redirect) ---"))
        self.stdout.write(f"  payment_page_base:     {pp.get('payment_page_base')}")
        self.stdout.write(f"  PUBLIC_API_URL:        {pp.get('public_api_url')}")
        self.stdout.write(f"  amount_probe_enabled:  {pp.get('amount_probe_enabled')}")
        self.stdout.write(f"  выдано реквизитов:     {pp.get('issued_with_requisites')}")
        self.stdout.write(f"  ждут на странице:      {pp.get('still_waiting_on_page')} (stale >2h: {pp.get('stale_waiting_over_2h')})")
        self.stdout.write(f"  нажали Оплатил:        {pp.get('user_clicked_paid')}  (conv vs issued: {pp.get('conversion_paid_vs_issued')})")
        self.stdout.write(f"  Success:               conv vs issued {pp.get('success_vs_issued')}, vs paid {pp.get('success_vs_paid_click')}")
        self.stdout.write(f"  Expired:               {pp.get('expired_vs_issued')}")
        self.stdout.write(f"  In Progress без рекв.: {pp.get('in_progress_without_requisites')}")

        self.stdout.write(w("\n--- 13. ВЫВОДЫ ---"))
        for line in pp.get("interpretation", []):
            self.stdout.write(f"  • {line}")

        self.stdout.write(w("\n--- 14. ПРИМЕРЫ (по категориям) ---"))
        for outcome, items in sorted(report.samples.items()):
            self.stdout.write(f"\n  [{outcome}]")
            for item in items[: int(options["samples"])]:
                self.stdout.write(
                    f"    {item['pay_in_id']}  order={item['merchant_order_id']}  "
                    f"amt={item['amount']}  trader={item['trader'] or '-'}  "
                    f"psp={item['psp_provider'] or '-'}  err={item['psp_error'] or '-'}"
                )

        self.stdout.write(w("\n--- ДОП. КОМАНДЫ ---"))
        self.stdout.write("  diagnose_payin <uuid>")
        self.stdout.write("  payin_trace <uuid>")
        self.stdout.write(f"  analyze_cannot_process --merchant {report.merchant} --ps {report.payment_system} --hours 168")
        self.stdout.write(f"  analyze_merchant_rejects --merchant {report.merchant} --hours 168")
        if options.get("json"):
            self.stdout.write(s(f"\nJSON saved: {options['json']}"))

    def _write_json(self, path: str, report: Report) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(report), fh, ensure_ascii=False, indent=2)
