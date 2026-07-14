"""CSV export PayIn / PayOut for merchant (1C sync format)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path

from django.db.models import Count
from django.utils import timezone

from merchant.models import Merchant
from payments.models import PayIn, PayOut

CSV_HEADER = [
    "ID",
    "Client",
    "Merchant Order ID",
    "Order Amount",
    "Comission Amount in Order Currency",
    "Currency",
    "Amount in USDT",
    "Comission Amount in USDT",
    "Order Type",
    "Status",
    "Created At",
    "Updated At",
    "Currency Rate",
]

_STATUS_1C = {
    "Success": "succeeded",
    "Failed": "failed",
    "Declined": "declined_by_gateway",
    "In Progress": "in_progress",
    "New": "new",
}


def _fmt_dt(dt) -> str:
    if dt is None:
        return ""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dec(value, places: int = 2) -> str:
    if value is None:
        return f"0.{'0' * places}"
    return f"{Decimal(value):.{places}f}"


def _client_label(client) -> str:
    if client is None:
        return ""
    return (client.name or client.client_id or "").strip()


def _rate(ps) -> Decimal:
    if ps is None:
        return Decimal("0")
    return Decimal(ps.get_rate())


def _commission_fiat(merchant_fee_usdt: Decimal, rate: Decimal) -> Decimal:
    if not merchant_fee_usdt or not rate:
        return Decimal("0")
    return merchant_fee_usdt * rate


def _status_for_1c(status_name: str | None) -> str:
    if not status_name:
        return ""
    return _STATUS_1C.get(status_name, status_name.lower().replace(" ", "_"))


def payin_row(pi: PayIn) -> list[str]:
    order = pi.order
    rate = _rate(pi.payment_system)
    usd = Decimal(order.usd_amount) if order and order.usd_amount else Decimal("0")
    fee_usdt = Decimal(order.merchant_fee) if order and order.merchant_fee else Decimal("0")
    fee_fiat = _commission_fiat(fee_usdt, rate)
    return [
        str(pi.id),
        _client_label(pi.client),
        pi.merchant_order_id or "",
        _dec(pi.amount),
        _dec(fee_fiat),
        pi.currency.symbol if pi.currency else "",
        _dec(usd),
        _dec(fee_usdt),
        "PayIn",
        _status_for_1c(pi.status.name if pi.status else None),
        _fmt_dt(pi.created_at),
        _fmt_dt(pi.updated_at),
        _dec(rate),
    ]


def payout_row(po: PayOut) -> list[str]:
    order = po.order
    rate = _rate(po.payment_system)
    usd = Decimal(order.usd_amount) if order and order.usd_amount else Decimal("0")
    fee_usdt = Decimal(order.merchant_fee) if order and order.merchant_fee else Decimal("0")
    fee_fiat = _commission_fiat(fee_usdt, rate)
    out_status = order.status.name if order and order.status else (po.status.name if po.status else "")
    if po.status and po.status.name == "Success":
        status_out = "succeeded"
    elif po.status and po.status.name in ("Failed", "Declined"):
        status_out = _status_for_1c(po.status.name)
    elif out_status == "Expired":
        status_out = "expired_without_callback"
    elif out_status == "Arbitrage":
        status_out = "failed_by_appeal"
    else:
        status_out = _status_for_1c(po.status.name if po.status else out_status)
    return [
        str(po.id),
        _client_label(po.client),
        po.merchant_order_id or "",
        _dec(po.amount),
        _dec(fee_fiat),
        po.currency.symbol if po.currency else "",
        _dec(usd),
        _dec(fee_usdt),
        "PayOut",
        status_out,
        _fmt_dt(po.created_at),
        _fmt_dt(po.updated_at),
        _dec(rate),
    ]


def _parse_period(
    *,
    date_from: str | None,
    date_to: str | None,
    days: int | None,
) -> tuple[datetime, datetime]:
    now = timezone.now()
    if days is not None:
        return now - timedelta(days=days), now
    if not date_from:
        raise ValueError("Укажите date_from или days=")
    start = timezone.make_aware(datetime.strptime(date_from, "%Y-%m-%d"), dt_timezone.utc)
    if date_to:
        end = timezone.make_aware(
            datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59),
            dt_timezone.utc,
        )
    else:
        end = now
    return start, end


def write_csv(path: Path, rows: list[list[str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return len(rows)


def export_merchant_deals_csv(
    merchant_username: str,
    date_from: str | None = None,
    date_to: str | None = None,
    *,
    days: int | None = None,
    out_dir: str = "/tmp",
    limit: int = 5000,
    verbose: bool = True,
) -> tuple[str, str, int, int]:
    """
    Export PayIn and PayOut CSV for one merchant.

    Returns: (payin_path, payout_path, payin_count, payout_count)
    """
    merchant = Merchant.objects.get(user__username=merchant_username)
    start, end = _parse_period(date_from=date_from, date_to=date_to, days=days)
    label = f"{merchant_username}_{start.date()}_{end.date()}"
    out = Path(out_dir)

    payins = (
        PayIn.objects.filter(merchant=merchant, created_at__gte=start, created_at__lte=end)
        .select_related("currency", "payment_system", "status", "client", "order")
        .order_by("created_at")[:limit]
    )
    payouts = (
        PayOut.objects.filter(merchant=merchant, created_at__gte=start, created_at__lte=end)
        .select_related("currency", "payment_system", "status", "client", "order", "order__status")
        .order_by("created_at")[:limit]
    )

    payin_path = out / f"PayIn_export_{label}.csv"
    payout_path = out / f"PayOut_export_{label}.csv"

    pin_n = write_csv(payin_path, [payin_row(pi) for pi in payins])
    pout_n = write_csv(payout_path, [payout_row(po) for po in payouts])

    if verbose:
        print(f"Merchant: {merchant_username}")
        print(f"Period:   {start.date()} .. {end.date()} (UTC)")
        print(f"  PayIn  -> {payin_path} ({pin_n} rows)")
        print(f"  PayOut -> {payout_path} ({pout_n} rows)")

    return str(payin_path), str(payout_path), pin_n, pout_n


def list_merchants_with_deals(*, days: int = 90, limit: int = 10) -> list[dict]:
    since = timezone.now() - timedelta(days=days)
    result = []
    for order_type, model in [("PayIn", PayIn), ("PayOut", PayOut)]:
        rows = (
            model.objects.filter(created_at__gte=since)
            .values("merchant__user__username")
            .annotate(count=Count("id"))
            .order_by("-count")[:limit]
        )
        for r in rows:
            result.append({"type": order_type, "username": r["merchant__user__username"], "count": r["count"]})
    return result
