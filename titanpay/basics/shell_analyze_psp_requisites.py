"""
Конверсия по реквизитам PSP: сколько раз выдали реквизит → сколько PayIn Success.

Запуск:
  python manage.py analyze_psp_requisites --days 7
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone

from payments.models import (
    ExpayonePayInSession,
    FairpayPayInSession,
    PayIn,
    ProtocolPayInSession,
)
from payments.expayone_client import expayone_map_requisite
from payments.protocol_client import protocol_map_requisite
from payments.psp_payin import requisite_payload_has_fields


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.strip())
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _window_bounds(
    target: date | None,
    *,
    week: bool,
    month: bool,
    days: float,
    hours: float | None,
    since: str,
    until: str,
) -> tuple[datetime, datetime]:
    now = timezone.now()
    if until.strip():
        end = _parse_dt(until)
    else:
        end = now
    if since.strip():
        start = _parse_dt(since)
    elif target is not None:
        start = timezone.make_aware(datetime.combine(target, datetime.min.time()))
        end = start + timedelta(days=1)
    elif week:
        start = end - timedelta(days=7)
    elif month:
        start = end - timedelta(days=30)
    elif hours is not None:
        start = end - timedelta(hours=float(hours))
    else:
        start = end - timedelta(days=float(days))
    return start, end


def _fairpay_map(create_body: dict) -> dict:
    if not isinstance(create_body, dict):
        return {}
    req = create_body.get("requisite")
    return req if isinstance(req, dict) else {}


def _requisite_key(req: dict) -> str:
    if not req:
        return "(empty)"
    card = (req.get("card_number") or "").strip()
    if card:
        digits = "".join(c for c in card if c.isdigit())
        if len(digits) >= 4:
            return f"card:*{digits[-4:]}"
        return f"card:{card[:8]}…"
    phone = (req.get("phone") or "").strip()
    if phone:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) >= 4:
            return f"phone:*{digits[-4:]}"
        return f"phone:{phone}"
    dep = (req.get("deposit_number") or "").strip()
    if dep:
        return f"dep:*{dep[-6:]}" if len(dep) >= 6 else f"dep:{dep}"
    if req.get("deeplink"):
        return "deeplink"
    if req.get("payment_form_url"):
        return "payment_form"
    owner = (req.get("owner") or "").strip()
    if owner:
        return f"owner:{owner[:24]}"
    return "other"


@dataclass
class ReqStats:
    issued: int = 0
    success: int = 0
    declined: int = 0
    in_progress: int = 0
    other: int = 0

    def add(self, status_name: str | None) -> None:
        self.issued += 1
        name = (status_name or "").strip()
        if name == "Success":
            self.success += 1
        elif name == "Declined":
            self.declined += 1
        elif name in ("In Progress", "Pending"):
            self.in_progress += 1
        else:
            self.other += 1

    @property
    def conversion_pct(self) -> float:
        if self.issued <= 0:
            return 0.0
        return 100.0 * self.success / self.issued


@dataclass
class Report:
    start: datetime
    end: datetime
    total_issued: int = 0
    total_success: int = 0
    by_provider: dict[str, ReqStats] = field(default_factory=dict)
    by_requisite: dict[str, dict[str, ReqStats]] = field(default_factory=lambda: defaultdict(dict))

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": {"start": self.start.isoformat(), "end": self.end.isoformat()},
            "total_issued": self.total_issued,
            "total_success": self.total_success,
            "conversion_pct": round(
                100.0 * self.total_success / self.total_issued, 2
            )
            if self.total_issued
            else 0,
            "by_provider": {
                p: {
                    "issued": s.issued,
                    "success": s.success,
                    "conversion_pct": round(s.conversion_pct, 2),
                }
                for p, s in self.by_provider.items()
            },
        }


def _session_providers():
    return [
        ("protocol", ProtocolPayInSession, protocol_map_requisite),
        ("expayone", ExpayonePayInSession, _expayone_map_body),
        ("fairpay", FairpayPayInSession, _fairpay_map),
    ]


def _expayone_map_body(create_body: dict) -> dict:
    if not isinstance(create_body, dict):
        return {}
    data = create_body.get("data")
    if isinstance(data, dict):
        return expayone_map_requisite(data)
    return expayone_map_requisite(create_body)


def _build_report(
    start: datetime,
    end: datetime,
    *,
    merchant: str | None,
    ps: str | None,
    provider_filter: str,
    limit: int,
) -> Report:
    report = Report(start=start, end=end)
    providers = _session_providers()
    if provider_filter != "all":
        providers = [p for p in providers if p[0] == provider_filter]

    payin_qs = (
        PayIn.objects.filter(created_at__gte=start, created_at__lte=end)
        .select_related("status", "payment_system", "merchant__user")
        .order_by("created_at")[:limit]
    )
    if merchant:
        payin_qs = payin_qs.filter(merchant__user__username=merchant)
    if ps:
        payin_qs = payin_qs.filter(payment_system__name__iexact=ps)

    payin_ids = list(payin_qs.values_list("pk", flat=True))
    if not payin_ids:
        return report

    payins = {p.pk: p for p in payin_qs}

    for prov_name, model, mapper in providers:
        sessions = model.objects.filter(pay_in_id__in=payin_ids).only(
            "pay_in_id", "create_response"
        )
        for session in sessions:
            pay_in = payins.get(session.pay_in_id)
            if pay_in is None:
                continue
            cr = session.create_response or {}
            if isinstance(cr, dict) and cr.get("error"):
                continue
            req = mapper(cr if isinstance(cr, dict) else {})
            if not requisite_payload_has_fields(req):
                if not (req.get("deeplink") or req.get("payment_form_url") or req.get("qr_image_url")):
                    continue
            key = _requisite_key(req)
            status_name = pay_in.status.name if pay_in.status else None

            prov_stats = report.by_provider.setdefault(prov_name, ReqStats())
            prov_stats.add(status_name)
            req_bucket = report.by_requisite[prov_name].setdefault(key, ReqStats())
            req_bucket.add(status_name)

            report.total_issued += 1
            if status_name == "Success":
                report.total_success += 1

    return report


def _print_report(
    report: Report,
    *,
    top: int,
    min_issued: int,
    shadow_min_issued: int,
    shadow_max_conv: float,
) -> None:
    print("\n=== PSP requisites — conversion ===")
    print(f"period:   {report.start:%Y-%m-%d %H:%M} … {report.end:%Y-%m-%d %H:%M} UTC")
    print(f"issued:   {report.total_issued}  (реквизит отдан мерчанту)")
    print(f"success:  {report.total_success}")
    if report.total_issued:
        pct = 100.0 * report.total_success / report.total_issued
        print(f"conv:     {pct:.1f}%")
    else:
        print("conv:     — (нет выданных реквизитов в окне)")

    print("\n--- By provider ---")
    for prov, stats in sorted(report.by_provider.items()):
        print(
            f"  {prov:10} issued={stats.issued:5} success={stats.success:5} "
            f"conv={stats.conversion_pct:5.1f}%  declined={stats.declined}"
        )

    print(f"\n--- Top requisites (min issued={min_issued}) ---")
    rows: list[tuple[str, str, ReqStats]] = []
    for prov, bucket in report.by_requisite.items():
        for key, stats in bucket.items():
            if stats.issued >= min_issued:
                rows.append((prov, key, stats))
    rows.sort(key=lambda x: (-x[2].issued, x[2].conversion_pct))
    for prov, key, stats in rows[:top]:
        shadow = (
            stats.issued >= shadow_min_issued and stats.conversion_pct < shadow_max_conv
        )
        mark = " ⚠ shadow" if shadow else ""
        print(
            f"  {prov:8} {key:22} issued={stats.issued:4} success={stats.success:4} "
            f"conv={stats.conversion_pct:5.1f}%{mark}"
        )
    if not rows:
        print("  (нет реквизитов с достаточным числом выдач)")


def run(
    target: date | None = None,
    *,
    week: bool = False,
    month: bool = False,
    days: float = 7,
    hours: float | None = None,
    since: str = "",
    until: str = "",
    merchant: str | None = None,
    ps: str | None = None,
    provider: str = "all",
    top: int = 25,
    min_issued: int = 2,
    shadow_min_issued: int = 5,
    shadow_max_conv: float = 5.0,
    limit: int = 50000,
    json_path: str = "",
    extra_periods: bool = True,
) -> None:
    start, end = _window_bounds(
        target, week=week, month=month, days=days, hours=hours, since=since, until=until
    )
    if merchant:
        print(f"merchant: {merchant}")
    if ps:
        print(f"payment_system: {ps}")
    if provider != "all":
        print(f"provider: {provider}")

    report = _build_report(
        start,
        end,
        merchant=merchant,
        ps=ps,
        provider_filter=provider,
        limit=limit,
    )
    _print_report(
        report,
        top=top,
        min_issued=min_issued,
        shadow_min_issued=shadow_min_issued,
        shadow_max_conv=shadow_max_conv,
    )

    if extra_periods and not target and not since.strip():
        for label, h in (("24h", 24), ("72h", 72)):
            if hours is not None:
                continue
            sub_end = timezone.now()
            sub_start = sub_end - timedelta(hours=h)
            sub = _build_report(
                sub_start,
                sub_end,
                merchant=merchant,
                ps=ps,
                provider_filter=provider,
                limit=limit,
            )
            if sub.total_issued:
                pct = 100.0 * sub.total_success / sub.total_issued
                print(f"\n--- Extra: last {label} --- issued={sub.total_issued} success={sub.total_success} conv={pct:.1f}%")

    if json_path:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)
        print(f"\nJSON: {json_path}")
