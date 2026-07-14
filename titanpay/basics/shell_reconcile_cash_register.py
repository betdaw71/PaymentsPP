"""
Трёхсторонняя сверка кассы: TitanPay + ExpayOne + Protocol.

  python3 basics/shell_reconcile_cash_register.py

  run(
      platform_path="/path/orders_in.xlsx",
      expayone_path="/path/expayone.csv",
      protocol_path="/path/protocol.xlsx",
  )

Ключ сопоставления:
  PayIn ID (платформа) = ID заявки (ExpayOne) = Внешний ID (Protocol)
  Fallback: сумма в фиате + |Δt| ≤ time_window_min
"""
from __future__ import annotations

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

Decimal0 = Decimal("0")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%d.%m.%Y %H:%M:%S")

SUCCESS = frozenset({
    "completed", "завершён", "завершен", "success", "succeeded", "успешно", "оплачен",
})
FAIL = frozenset({
    "cannot process", "cancelled", "expired", "истек", "отмен", "declined", "failed",
})


def _d(val, places: int = 6) -> Decimal:
    if val is None or val == "":
        return Decimal0
    try:
        return Decimal(str(val).replace(",", ".").strip()).quantize(Decimal(10) ** -places)
    except (InvalidOperation, ValueError):
        return Decimal0


def _parse_dt(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _norm_id(val: str) -> str:
    return (val or "").strip().lower().rstrip("r")


def _is_success(status: str) -> bool:
    s = (status or "").lower()
    return any(x in s for x in SUCCESS)


def _read_csv(path: Path) -> list[dict]:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Cannot read CSV: {path}")


def _read_xlsx(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f".//{_NS}si"):
                shared.append("".join(t.text or "" for t in si.findall(f".//{_NS}t")))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        matrix: list[list[str]] = []
        for row_el in sheet.findall(f".//{_NS}row"):
            vals: list[str] = []
            for c in row_el.findall(f"{_NS}c"):
                is_el = c.find(f"{_NS}is")
                v = c.find(f"{_NS}v")
                t = c.get("t")
                if is_el is not None:
                    vals.append("".join(x.text or "" for x in is_el.findall(f".//{_NS}t")))
                elif v is not None and v.text:
                    if t == "s":
                        vals.append(shared[int(v.text)])
                    elif t == "n" and len(vals) == 7:
                        serial = float(v.text)
                        dt = datetime(1899, 12, 30) + timedelta(days=serial)
                        vals.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        vals.append(v.text)
                else:
                    vals.append("")
            if any(vals):
                matrix.append(vals)
    if not matrix:
        return []
    headers = matrix[0]
    return [dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in matrix[1:]]


def _load(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    return _read_xlsx(path)


@dataclass
class Deal:
    source: str
    external_id: str = ""
    inorder_id: str = ""
    provider_order_id: str = ""
    status: str = ""
    amount_fiat: Decimal = Decimal0
    amount_usdt: Decimal = Decimal0
    rate: Decimal = Decimal0
    profit_usdt: Decimal = Decimal0
    commission_usdt: Decimal = Decimal0
    payment_system: str = ""
    created_at: datetime | None = None
    raw: dict = field(default_factory=dict)

    @property
    def match_id(self) -> str:
        return _norm_id(self.external_id or self.inorder_id)

    @property
    def implied_rate(self) -> Decimal:
        if self.rate > 0:
            return self.rate
        if self.amount_usdt > 0 and self.amount_fiat > 0:
            return _d(self.amount_fiat / self.amount_usdt, 4)
        return Decimal0


def _parse_platform(rows: list[dict]) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        ext = r.get("PayIn ID") or r.get("pay_in__id") or ""
        inorder = r.get("ID (InOrder)") or r.get("ID") or ""
        fiat = _d(r.get("Сумма (Фиат)"), 2)
        usdt = _d(r.get("Сумма (USDT)"))
        out.append(Deal(
            source="platform",
            external_id=str(ext),
            inorder_id=str(inorder),
            status=str(r.get("Статус") or ""),
            amount_fiat=fiat,
            amount_usdt=usdt,
            profit_usdt=_d(r.get("Прибыль")),
            payment_system=str(r.get("Платёжная система") or ""),
            created_at=_parse_dt(str(r.get("Дата создания") or "")),
            raw=r,
        ))
    return out


def _parse_expayone(rows: list[dict]) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        rate_raw = r.get("Курс USDT") or ""
        rate, _ = _parse_rate(rate_raw)
        out.append(Deal(
            source="expayone",
            external_id=str(r.get("ID заявки") or ""),
            provider_order_id=str(r.get("ID ордера") or ""),
            status=str(r.get("Статус") or ""),
            amount_fiat=_d(r.get("Сумма в валюте"), 2),
            amount_usdt=_d(r.get("Сумма USDT")),
            commission_usdt=_d(r.get("Комиссия USDT")),
            rate=rate,
            created_at=_parse_dt(str(r.get("Дата") or "")),
            raw=r,
        ))
    return out


def _parse_protocol(rows: list[dict]) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        out.append(Deal(
            source="protocol",
            external_id=str(r.get("Внешний ID") or ""),
            provider_order_id=str(r.get("UUID Заказа") or ""),
            status=str(r.get("Статус") or ""),
            amount_fiat=_d(r.get("Сумма"), 2),
            amount_usdt=_d(r.get("Прибыль мерчанта")),  # merchant-side USDT
            profit_usdt=_d(r.get("Прибыль мерчанта")),
            commission_usdt=_d(r.get("Сумма комиссии сервиса")),
            rate=_d(r.get("Курс"), 4),
            created_at=_parse_dt(str(r.get("Дата создания") or "")),
            raw=r,
        ))
    return out


_RATE_RE = re.compile(r"([\d.,]+)")


def _parse_rate(raw: str) -> tuple[Decimal, str]:
    m = _RATE_RE.search((raw or "").replace(",", "."))
    return (_d(m.group(1), 4) if m else Decimal0, "")


def _date_range(deals: list[Deal]) -> str:
    dts = [d.created_at for d in deals if d.created_at]
    if not dts:
        return "—"
    return f"{min(dts):%Y-%m-%d} — {max(dts):%Y-%m-%d}"


def _index(deals: list[Deal]) -> dict[str, Deal]:
    idx: dict[str, Deal] = {}
    for d in deals:
        mid = d.match_id
        if mid:
            idx[mid] = d
    return idx


def _match_amount_time(
    left: list[Deal],
    right: list[Deal],
    *,
    window_min: int,
) -> list[tuple[Deal, Deal, float]]:
    pairs: list[tuple[Deal, Deal, float]] = []
    used: set[int] = set()
    window = timedelta(minutes=window_min)
    for i, a in enumerate(left):
        if not a.created_at or a.amount_fiat <= 0:
            continue
        best_j = None
        best_dt = None
        for j, b in enumerate(right):
            if j in used or b.amount_fiat != a.amount_fiat or not b.created_at:
                continue
            dt = abs(a.created_at - b.created_at)
            if dt <= window and (best_dt is None or dt < best_dt):
                best_j, best_dt = j, dt
        if best_j is not None:
            used.add(best_j)
            pairs.append((a, right[best_j], best_dt.total_seconds()))
    return pairs


@dataclass
class TriMatch:
    platform: Deal | None
    expayone: Deal | None
    protocol: Deal | None
    match_type: str
    flags: list[str] = field(default_factory=list)


def run(
    platform_path: str,
    expayone_path: str,
    protocol_path: str,
    *,
    time_window_min: int = 30,
    rate_tolerance_pct: float = 1.0,
    only_success: bool = True,
    report_csv: str | None = None,
) -> dict:
    plat = _parse_platform(_load(Path(platform_path)))
    exp = _parse_expayone(_load(Path(expayone_path)))
    prot = _parse_protocol(_load(Path(protocol_path)))

    if only_success:
        plat_p = [d for d in plat if _is_success(d.status)]
        exp_p = [d for d in exp if _is_success(d.status)]
        prot_p = [d for d in prot if _is_success(d.status)]
    else:
        plat_p, exp_p, prot_p = plat, exp, prot

    print("=" * 72)
    print("СВЕРКА КАССЫ: TitanPay + ExpayOne + Protocol")
    print("=" * 72)
    print(f"  Platform:  {len(plat)} rows | { _date_range(plat)}")
    print(f"  ExpayOne:  {len(exp)} rows | {_date_range(exp)}")
    print(f"  Protocol:  {len(prot)} rows | {_date_range(prot)}")
    print()

    print("--- Статусы (все строки) ---")
    print("  Platform:", dict(Counter(d.status for d in plat).most_common(6)))
    print("  ExpayOne:", dict(Counter(d.status for d in exp).most_common(6)))
    print("  Protocol:", dict(Counter(d.status for d in prot).most_common(6)))
    print()

    has_payin_col = any(d.external_id for d in plat)
    if not has_payin_col:
        print("  [!] В выгрузке платформы нет колонки PayIn ID — сопоставление только сумма+время.")
        print("      Переэкспортируйте заявки после обновления (колонка PayIn ID добавлена).")
        print()

    idx_plat = _index(plat_p if has_payin_col else [])
    idx_exp = _index(exp_p)
    idx_prot = _index(prot_p)

    triple_ids = set(idx_plat) & set(idx_exp) & set(idx_prot)
    plat_exp = set(idx_plat) & set(idx_exp) - triple_ids if has_payin_col else set()
    plat_prot = set(idx_plat) & set(idx_prot) - triple_ids if has_payin_col else set()

    print("--- Сопоставление по PayIn ID ---")
    print(f"  Тройное (platform+expayone+protocol): {len(triple_ids)}")
    print(f"  Platform + ExpayOne: {len(plat_exp)}")
    print(f"  Platform + Protocol: {len(plat_prot)}")
    print()

    # Platform-only P&L
    plat_ok = [d for d in plat if _is_success(d.status)]
    total_profit = sum(d.profit_usdt for d in plat_ok)
    total_usdt = sum(d.amount_usdt for d in plat_ok)
    c2c_ok = [d for d in plat_ok if d.payment_system == "C2CKZT"]
    print("--- Операционная прибыль (платформа, Completed) ---")
    print(f"  Успешных заявок: {len(plat_ok)}")
    print(f"  C2CKZT успешных: {len(c2c_ok)}")
    print(f"  Сумма trader_fee (колонка Прибыль): {total_profit:.2f} USDT")
    print(f"  Оборот USDT: {total_usdt:.2f}")
    print()

    rate_tol = Decimal(str(rate_tolerance_pct))
    rate_issues: list[dict] = []
    report_rows: list[dict] = []

    def _analyze_pair(a: Deal, b: Deal, label: str, time_diff: float = 0) -> None:
        flags: list[str] = []
        if a.amount_fiat != b.amount_fiat:
            flags.append("amount_mismatch")
        ra, rb = a.implied_rate, b.implied_rate
        diff_pct = Decimal0
        if ra > 0 and rb > 0:
            diff_pct = abs(ra - rb) / rb * 100
            if diff_pct > rate_tol:
                flags.append(f"rate_diff_{diff_pct:.2f}%")
        if _is_success(a.status) != _is_success(b.status):
            flags.append("status_mismatch")
        if flags:
            rate_issues.append({"pair": label, "flags": flags, "rate_a": ra, "rate_b": rb})
        report_rows.append({
            "match": label,
            "platform_id": a.inorder_id,
            "payin_id": a.external_id or b.external_id,
            "amount_fiat": float(a.amount_fiat),
            "platform_usdt": float(a.amount_usdt),
            "platform_profit": float(a.profit_usdt),
            "provider_usdt": float(b.amount_usdt),
            "platform_rate": float(ra),
            "provider_rate": float(rb),
            "rate_diff_pct": float(diff_pct),
            "platform_status": a.status,
            "provider_status": b.status,
            "time_diff_sec": time_diff,
            "flags": ";".join(flags),
        })

    # ID-based pairs
    for eid in sorted(triple_ids):
        _analyze_pair(idx_plat[eid], idx_exp[eid], "triple_exp", 0)
        _analyze_pair(idx_plat[eid], idx_prot[eid], "triple_prot", 0)

    for eid in sorted(plat_prot):
        if eid not in triple_ids:
            _analyze_pair(idx_plat[eid], idx_prot[eid], "plat_prot_id", 0)

    # amount+time fallback for platform C2CKZT completed vs protocol/expayone
    plat_c2c = [d for d in plat_p if d.payment_system == "C2CKZT"] if only_success else [d for d in plat if d.payment_system == "C2CKZT"]
    if not has_payin_col or len(triple_ids) == 0:
        print("--- Fallback: сумма + время (C2CKZT) ---")
        for prov_name, prov_list in (("expayone", exp_p), ("protocol", prot_p)):
            pairs = _match_amount_time(plat_c2c, prov_list, window_min=time_window_min)
            print(f"  Platform ↔ {prov_name}: {len(pairs)} пар")
            for a, b, td in pairs[:10]:
                _analyze_pair(a, b, f"weak_{prov_name}", td)
                print(
                    f"    {float(a.amount_fiat):.0f} KZT | plat {a.status} / {prov_name} {b.status} | "
                    f"rate plat {a.implied_rate:.2f} vs prov {b.implied_rate:.2f} | Δt {td:.0f}s"
                )
        print()

    print("--- Расхождения курса ---")
    print(f"  Пар с флагами: {len(rate_issues)}")
    for item in rate_issues[:15]:
        print(f"    {item['pair']}: {item['flags']} | {item['rate_a']} vs {item['rate_b']}")
    print()

    cannot = sum(1 for d in plat if "cannot" in d.status.lower())
    print("--- Проблемы операционные ---")
    print(f"  Cannot process на платформе: {cannot} ({cannot/len(plat)*100:.1f}%)")
    print(f"  ExpayOne без успешных (все expired?): {len(exp_p)} success из {len(exp)}")
    print()

    out = report_csv or str(Path(platform_path).with_name("reconcile_3way_report.csv"))
    if report_rows:
        try:
            out_path = Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
                w.writeheader()
                w.writerows(report_rows)
            print(f"--- Отчёт CSV: {out} ---")
        except OSError:
            out = f"/tmp/reconcile_3way_report.csv"
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
                w.writeheader()
                w.writerows(report_rows)
            print(f"--- Отчёт CSV: {out} ---")

    print("Готово.")
    return {
        "platform_rows": len(plat),
        "expayone_rows": len(exp),
        "protocol_rows": len(prot),
        "triple_match": len(triple_ids),
        "platform_profit_usdt": total_profit,
        "rate_issues": len(rate_issues),
        "report_csv": out,
    }


print("shell_reconcile_cash_register loaded")
print("  run(platform_path='...', expayone_path='...', protocol_path='...')")

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        run(sys.argv[1], sys.argv[2], sys.argv[3])
