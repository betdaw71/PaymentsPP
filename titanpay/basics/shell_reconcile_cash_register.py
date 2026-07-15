"""
Трёхсторонняя сверка кассы: TitanPay + ExpayOne + Protocol.

  python3 basics/shell_reconcile_cash_register.py platform.xlsx expayone.csv protocol.xlsx

  run(platform_path=..., expayone_path=..., protocol_path=...)

Сопоставление: PayIn ID = ID заявки (ExpayOne) = Внешний ID (Protocol).
Rate PnL (без комиссии): fiat/provider_rate − platform_usdt
  > 0 — выигрыш: наш курс выше → мерчанту меньше USDT, чем от провайдера
  < 0 — проигрыш на курсе

Исключаются заявки с синтетическим курсом ≈1 (C2CTRY TRY hack).
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


_RATE_RE = re.compile(r"([\d.,]+)")


def _parse_rate(raw: str) -> Decimal:
    m = _RATE_RE.search((raw or "").replace(",", "."))
    return _d(m.group(1), 4) if m else Decimal0


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
    profit_usdt: Decimal = Decimal0  # legacy / trader_fee in old exports
    merchant_fee_usdt: Decimal = Decimal0
    trader_fee_usdt: Decimal = Decimal0
    platform_commission_usdt: Decimal = Decimal0  # merchant_fee − trader_fee
    commission_usdt: Decimal = Decimal0  # provider-side fee if any
    payment_system: str = ""
    created_at: datetime | None = None
    raw: dict = field(default_factory=dict)

    @property
    def payin_id(self) -> str:
        return _norm_id(self.external_id)

    @property
    def our_rate(self) -> Decimal:
        """KZT (fiat) per 1 USDT on platform."""
        if self.amount_usdt > 0 and self.amount_fiat > 0:
            return _d(self.amount_fiat / self.amount_usdt, 4)
        return self.rate if self.rate > 0 else Decimal0

    @property
    def provider_settlement_usdt(self) -> Decimal:
        """USDT at provider rate for same fiat."""
        if self.rate > 0 and self.amount_fiat > 0:
            return _d(self.amount_fiat / self.rate)
        if self.amount_usdt > 0:
            return self.amount_usdt
        return Decimal0


def _platform_commission_from_row(r: dict, *, spread_pct: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Returns (merchant_fee, trader_fee, platform_commission, used_estimate).
    Platform earns merchant_fee − trader_fee (spread мерчант vs трейдер/провайдер).
    """
    plat_comm = _d(r.get("Комиссия платформы (USDT)"))
    mf = _d(r.get("Комиссия мерчанта (USDT)"))
    tf = _d(r.get("Комиссия трейдера (USDT)"))
    if plat_comm > 0:
        return mf, tf, plat_comm, Decimal0
    if mf > 0 or tf > 0:
        return mf, tf, _d(mf - tf), Decimal0
    usdt = _d(r.get("Сумма (USDT)"))
    if spread_pct > 0 and usdt > 0:
        est = _d(usdt * spread_pct / Decimal("100"))
        legacy_trader = _d(r.get("Прибыль"))  # old export: trader_fee, NOT platform
        return Decimal0, legacy_trader, est, spread_pct
    return Decimal0, _d(r.get("Прибыль")), Decimal0, Decimal0


def _parse_platform(rows: list[dict], *, spread_pct: Decimal) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        mf, tf, plat, _ = _platform_commission_from_row(r, spread_pct=spread_pct)
        out.append(Deal(
            source="platform",
            external_id=str(r.get("PayIn ID") or r.get("pay_in__id") or ""),
            inorder_id=str(r.get("ID (InOrder)") or r.get("ID") or ""),
            status=str(r.get("Статус") or ""),
            amount_fiat=_d(r.get("Сумма (Фиат)"), 2),
            amount_usdt=_d(r.get("Сумма (USDT)")),
            merchant_fee_usdt=mf,
            trader_fee_usdt=tf,
            platform_commission_usdt=plat,
            profit_usdt=tf,
            payment_system=str(r.get("Платёжная система") or ""),
            created_at=_parse_dt(str(r.get("Дата создания") or "")),
            raw=r,
        ))
    return out


def _parse_expayone(rows: list[dict]) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        rate = _parse_rate(r.get("Курс USDT") or "")
        fiat = _d(r.get("Сумма в валюте"), 2)
        usdt = _d(r.get("Сумма USDT"))
        if usdt <= 0 and rate > 0 and fiat > 0:
            usdt = _d(fiat / rate)
        out.append(Deal(
            source="expayone",
            external_id=str(r.get("ID заявки") or ""),
            provider_order_id=str(r.get("ID ордера") or ""),
            status=str(r.get("Статус") or ""),
            amount_fiat=fiat,
            amount_usdt=usdt,
            commission_usdt=_d(r.get("Комиссия USDT")),
            rate=rate,
            created_at=_parse_dt(str(r.get("Дата") or "")),
            raw=r,
        ))
    return out


def _parse_protocol(rows: list[dict]) -> list[Deal]:
    out: list[Deal] = []
    for r in rows:
        rate = _d(r.get("Курс"), 4)
        fiat = _d(r.get("Сумма"), 2)
        settlement = _d(fiat / rate) if rate > 0 and fiat > 0 else Decimal0
        out.append(Deal(
            source="protocol",
            external_id=str(r.get("Внешний ID") or ""),
            provider_order_id=str(r.get("UUID Заказа") or ""),
            status=str(r.get("Статус") or ""),
            amount_fiat=fiat,
            amount_usdt=settlement,
            profit_usdt=_d(r.get("Прибыль мерчанта")),
            commission_usdt=_d(r.get("Сумма комиссии сервиса")),
            rate=rate,
            created_at=_parse_dt(str(r.get("Дата создания") or "")),
            raw=r,
        ))
    return out


def _is_synthetic_rate(deal: Deal, *, max_synthetic_rate: Decimal) -> bool:
    """C2CTRY TRY hack: rate pinned to 1 to skip local balance."""
    r = deal.our_rate if deal.source == "platform" else deal.rate
    if r <= Decimal0:
        return False
    if r <= max_synthetic_rate:
        return True
    if deal.payment_system.upper() == "C2CTRY" and r <= max_synthetic_rate:
        return True
    return False


def _rate_pnl(platform: Deal, provider: Deal) -> Decimal:
    """
    PnL on rate only (USDT), excluding commission.

    Модель: покупаем у провайдера (fiat/R_provider), продаём мерчанту (fiat/R_ours).
    Если наш курс ВЫШЕ (больше fiat за 1 USDT) → мерчанту меньше USDT → мы выигрываем.

    rate_pnl = fiat/R_provider − platform_usdt  (= provider_settlement − our_debit)
    Positive → выигрыш на курсе.
    """
    prov_rate = provider.rate if provider.rate > 0 else provider.our_rate
    if prov_rate <= 0 or platform.amount_usdt <= 0:
        return Decimal0
    provider_usdt = _d(platform.amount_fiat / prov_rate)
    return _d(provider_usdt - platform.amount_usdt)


def _rate_spread_pct(our_rate: Decimal, provider_rate: Decimal) -> Decimal:
    if provider_rate <= 0:
        return Decimal0
    return _d((our_rate - provider_rate) / provider_rate * 100, 4)


def _index_by_payin(deals: list[Deal]) -> dict[str, Deal]:
    return {d.payin_id: d for d in deals if d.payin_id}


def _match_amount_time(
    left: list[Deal],
    right: list[Deal],
    *,
    window_min: int,
) -> list[tuple[Deal, Deal, float]]:
    pairs: list[tuple[Deal, Deal, float]] = []
    used: set[int] = set()
    window = timedelta(minutes=window_min)
    for a in left:
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


def _build_pairs(
    platform: list[Deal],
    provider: list[Deal],
    *,
    window_min: int,
) -> list[tuple[Deal, Deal, str, float]]:
    """Return (platform, provider, match_type, time_diff_sec)."""
    pairs: list[tuple[Deal, Deal, str, float]] = []
    used_plat: set[str] = set()
    used_prov: set[str] = set()

    idx_prov = _index_by_payin(provider)
    for p in platform:
        pid = p.payin_id
        if not pid or pid not in idx_prov:
            continue
        pr = idx_prov[pid]
        pairs.append((p, pr, "payin_id", 0.0))
        used_plat.add(p.inorder_id or pid)
        used_prov.add(pr.payin_id)

    rest_plat = [p for p in platform if (p.inorder_id or p.payin_id) not in used_plat]
    rest_prov = [p for p in provider if p.payin_id not in used_prov]
    for p, pr, td in _match_amount_time(rest_plat, rest_prov, window_min=window_min):
        pairs.append((p, pr, "amount+time", td))
    return pairs


@dataclass
class MatchedRow:
    provider_name: str
    match_type: str
    platform: Deal
    provider: Deal
    time_diff_sec: float
    our_rate: Decimal = Decimal0
    provider_rate: Decimal = Decimal0
    rate_spread_pct: Decimal = Decimal0
    rate_pnl_usdt: Decimal = Decimal0
    commission_usdt: Decimal = Decimal0
    excluded: bool = False
    exclude_reason: str = ""

    def to_csv_dict(self) -> dict:
        dt = self.platform.created_at
        return {
            "provider": self.provider_name,
            "match_type": self.match_type,
            "day": dt.strftime("%Y-%m-%d") if dt else "",
            "hour": dt.strftime("%H:00") if dt else "",
            "payin_id": self.platform.external_id or self.provider.external_id,
            "inorder_id": self.platform.inorder_id,
            "payment_system": self.platform.payment_system,
            "amount_fiat": float(self.platform.amount_fiat),
            "our_rate": float(self.our_rate),
            "provider_rate": float(self.provider_rate),
            "rate_spread_pct": float(self.rate_spread_pct),
            "platform_usdt": float(self.platform.amount_usdt),
            "provider_usdt_at_rate": float(_d(self.platform.amount_fiat / self.provider_rate) if self.provider_rate > 0 else 0),
            "rate_pnl_usdt": float(self.rate_pnl_usdt),
            "platform_commission_usdt": float(self.platform.platform_commission_usdt),
            "trader_fee_usdt": float(self.platform.trader_fee_usdt),
            "merchant_fee_usdt": float(self.platform.merchant_fee_usdt),
            "platform_profit_trader_fee": float(self.platform.trader_fee_usdt),
            "platform_status": self.platform.status,
            "provider_status": self.provider.status,
            "time_diff_sec": self.time_diff_sec,
            "excluded": self.excluded,
            "exclude_reason": self.exclude_reason,
        }


def _aggregate(rows: list[MatchedRow], key_fn) -> list[dict]:
    buckets: dict[str, list[MatchedRow]] = defaultdict(list)
    for r in rows:
        if r.excluded:
            continue
        buckets[key_fn(r)].append(r)

    out: list[dict] = []
    for key in sorted(buckets):
        items = buckets[key]
        rate_pnls = [r.rate_pnl_usdt for r in items]
        wins = sum(1 for x in rate_pnls if x > 0)
        losses = sum(1 for x in rate_pnls if x < 0)
        out.append({
            "period": key,
            "deals": len(items),
            "total_fiat": float(sum(r.platform.amount_fiat for r in items)),
            "avg_our_rate": float(_d(sum(r.our_rate for r in items) / len(items), 4)),
            "avg_provider_rate": float(_d(sum(r.provider_rate for r in items) / len(items), 4)),
            "avg_rate_spread_pct": float(_d(sum(r.rate_spread_pct for r in items) / len(items), 4)),
            "rate_pnl_usdt": float(sum(rate_pnls)),
            "rate_wins": wins,
            "rate_losses": losses,
            "commission_usdt": float(sum(r.platform.platform_commission_usdt for r in items)),
        })
    return out


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  CSV: {path}")
    except OSError:
        alt = f"/tmp/{p.name}"
        with open(alt, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  CSV: {alt}")


def run(
    platform_path: str,
    expayone_path: str,
    protocol_path: str,
    *,
    time_window_min: int = 30,
    rate_tolerance_pct: float = 1.0,
    only_success: bool = True,
    skip_synthetic_rate: bool = True,
    max_synthetic_rate: float = 1.01,
    commission_spread_pct: float = 0.5,
    report_csv: str | None = None,
) -> dict:
    spread = Decimal(str(commission_spread_pct))
    plat_all = _parse_platform(_load(Path(platform_path)), spread_pct=spread)
    exp_all = _parse_expayone(_load(Path(expayone_path)))
    prot_all = _parse_protocol(_load(Path(protocol_path)))

    plat = [d for d in plat_all if _is_success(d.status)] if only_success else plat_all
    exp = [d for d in exp_all if _is_success(d.status)] if only_success else exp_all
    prot = [d for d in prot_all if _is_success(d.status)] if only_success else prot_all

    max_syn = Decimal(str(max_synthetic_rate))
    excluded_count = 0
    if skip_synthetic_rate:
        excluded_count = sum(1 for d in plat if _is_synthetic_rate(d, max_synthetic_rate=max_syn))
        plat = [d for d in plat if not _is_synthetic_rate(d, max_synthetic_rate=max_syn)]

    print("=" * 72)
    print("СВЕРКА КАССЫ + АНАЛИЗ КУРСА")
    print("=" * 72)
    print(f"  Platform: {len(plat_all)} всего | {len(plat)} в анализе")
    print(f"  ExpayOne: {len(exp_all)} всего | {len(exp)} в анализе")
    print(f"  Protocol: {len(prot_all)} всего | {len(prot)} в анализе")
    if skip_synthetic_rate:
        print(f"  Исключено C2CTRY/курс≈1: {excluded_count} заявок (порог ≤ {max_synthetic_rate})")
    print()

    plat_ok_all = [d for d in plat_all if _is_success(d.status)]
    plat_ok_clean = plat
    plat_total_fiat = sum(d.amount_fiat for d in plat_ok_clean)
    plat_total_usdt = sum(d.amount_usdt for d in plat_ok_clean)
    plat_total_commission = sum(d.platform_commission_usdt for d in plat_ok_clean)
    plat_total_trader_fee = sum(d.trader_fee_usdt for d in plat_ok_clean)
    using_commission_estimate = not any(
        d.merchant_fee_usdt > 0 or _d(d.raw.get("Комиссия платформы (USDT)")) > 0
        for d in plat_ok_clean
    )
    ps_breakdown = Counter(d.payment_system for d in plat_ok_clean)

    print("=" * 72)
    print("ПЛАТФОРМА — ВСЕ УСПЕШНЫЕ ЗАЯВКИ (Completed)")
    print("=" * 72)
    print(f"  Успешных всего (до фильтров):     {len(plat_ok_all)}")
    print(f"  В анализе (без курса≈1):          {len(plat_ok_clean)}")
    print(f"  Оборот фиат:                      {float(plat_total_fiat):,.2f}")
    print(f"  Оборот USDT:                      {float(plat_total_usdt):,.2f}")
    print(f"  Комиссия платформы (merchant−trader): {float(plat_total_commission):,.2f} USDT")
    print(f"  Комиссия трейдера (не ваш доход):     {float(plat_total_trader_fee):,.2f} USDT")
    if using_commission_estimate:
        print(f"  [!] merchant_fee нет в экспорте — комиссия оценена как {commission_spread_pct}% от USDT-оборота")
        print("      Переэкспортируйте заявки после обновления (колонка Комиссия платформы)")
    print(f"  По платёжным системам:")
    for ps, cnt in ps_breakdown.most_common(8):
        ps_deals = [d for d in plat_ok_clean if d.payment_system == ps]
        ps_fiat = sum(d.amount_fiat for d in ps_deals)
        ps_comm = sum(d.platform_commission_usdt for d in ps_deals)
        ps_trader = sum(d.trader_fee_usdt for d in ps_deals)
        print(f"    {ps or '(пусто)':12} {cnt:4} сд. | {float(ps_fiat):>12,.0f} fiat | платформа {float(ps_comm):>8,.2f} | трейдер {float(ps_trader):>8,.2f} USDT")
    print()
    print("  [!] Rate PnL считается только по сопоставленным с провайдером заявкам.")
    print("      Комиссия выше — по ВСЕМ успешным на платформе.")
    print()

    matched: list[MatchedRow] = []
    for prov_name, prov_list in (("expayone", exp), ("protocol", prot)):
        pairs = _build_pairs(plat, prov_list, window_min=time_window_min)
        print(f"--- Platform ↔ {prov_name}: {len(pairs)} пар ---")
        for p, pr, mtype, td in pairs:
            our_r = p.our_rate
            prov_r = pr.rate if pr.rate > 0 else pr.our_rate
            row = MatchedRow(
                provider_name=prov_name,
                match_type=mtype,
                platform=p,
                provider=pr,
                time_diff_sec=td,
                our_rate=our_r,
                provider_rate=prov_r,
                rate_spread_pct=_rate_spread_pct(our_r, prov_r),
                rate_pnl_usdt=_rate_pnl(p, pr),
                commission_usdt=p.platform_commission_usdt,
            )
            if skip_synthetic_rate and (_is_synthetic_rate(p, max_synthetic_rate=max_syn) or prov_r <= max_syn):
                row.excluded = True
                row.exclude_reason = "synthetic_rate_1"
            matched.append(row)
            flag = " ⚠ EXCLUDED" if row.excluded else ""
            win_lose = "WIN" if row.rate_pnl_usdt > 0 else ("LOSS" if row.rate_pnl_usdt < 0 else "—")
            print(
                f"  [{mtype}] {p.payment_system} {float(p.amount_fiat):.0f} | "
                f"наш {our_r:.2f} vs {prov_name} {prov_r:.2f} ({float(row.rate_spread_pct):+.2f}%) | "
                f"rate {float(row.rate_pnl_usdt):+.4f} | платформа {float(row.commission_usdt):.4f} USDT [{win_lose}]{flag}"
            )
        print()

    active = [r for r in matched if not r.excluded]
    total_rate_pnl = sum(r.rate_pnl_usdt for r in active)
    total_commission = sum(r.commission_usdt for r in active)
    total_fiat = sum(r.platform.amount_fiat for r in active)
    wins = sum(1 for r in active if r.rate_pnl_usdt > 0)
    losses = sum(1 for r in active if r.rate_pnl_usdt < 0)
    sum_wins_usdt = sum(r.rate_pnl_usdt for r in active if r.rate_pnl_usdt > 0)
    sum_losses_usdt = sum(r.rate_pnl_usdt for r in active if r.rate_pnl_usdt < 0)

    by_provider: dict[str, list[MatchedRow]] = defaultdict(list)
    for r in active:
        by_provider[r.provider_name].append(r)

    print("=" * 72)
    print("ЗАРАБОТОК НА РАЗНИЦЕ КУРСОВ (суммарно по всем заявкам)")
    print("=" * 72)
    for prov_name in sorted(by_provider):
        items = by_provider[prov_name]
        prov_pnl = sum(r.rate_pnl_usdt for r in items)
        prov_fiat = sum(r.platform.amount_fiat for r in items)
        prov_wins = sum(1 for r in items if r.rate_pnl_usdt > 0)
        prov_losses = sum(1 for r in items if r.rate_pnl_usdt < 0)
        print(
            f"  {prov_name:10} | {len(items):4} сд. | "
            f"оборот {float(prov_fiat):,.0f} fiat | "
            f"rate PnL {float(prov_pnl):+.4f} USDT | "
            f"комиссия {float(sum(r.platform.platform_commission_usdt for r in items)):.2f} USDT | "
            f"W/L {prov_wins}/{prov_losses}"
        )
    print("-" * 72)
    print(f"  {'ИТОГО':10} | {len(active):4} сд. | "
          f"оборот {float(total_fiat):,.0f} fiat | "
          f"rate PnL {float(total_rate_pnl):+.4f} USDT | "
          f"комиссия {float(total_commission):.2f} USDT | W/L {wins}/{losses}")
    print(f"  Сумма выигрышей на курсе:  {float(sum_wins_usdt):+.4f} USDT  ({wins} сделок)")
    print(f"  Сумма проигрышей на курсе: {float(sum_losses_usdt):+.4f} USDT  ({losses} сделок)")
    print(f"  Чистый заработок на курсе:  {float(total_rate_pnl):+.4f} USDT")
    print()
    matched_plat_ids = {r.platform.inorder_id or r.platform.payin_id for r in active}
    coverage = len(matched_plat_ids)
    coverage_pct = (coverage / len(plat_ok_clean) * 100) if plat_ok_clean else 0
    print(f"  Сопоставлено с провайдерами: {coverage} из {len(plat_ok_clean)} platform-сделок ({coverage_pct:.1f}%)")
    print(f"  Rate PnL ниже — только по этим {len(active)} парам (не по всей платформе!)")
    print()
    print("  (комиссия платформы = merchant_fee − trader_fee, ~0.5% оборота; НЕ trader_fee)")
    print(f"  Комиссия платформы (сопоставленные): {float(total_commission):,.2f} USDT")
    print(f"  Комиссия платформы (ВСЯ платформа):  {float(plat_total_commission):,.2f} USDT")
    print(f"  Rate PnL (сопоставленные):     {float(total_rate_pnl):+.4f} USDT")
    print(f"  Полный доход (курс+комиссия, только {len(active)} пар): {float(total_rate_pnl + total_commission):+.4f} USDT")
    print()
    print("  rate_spread > 0 → наш курс ВЫШЕ провайдера → мерчанту меньше USDT → выигрываем")
    print("  rate_pnl > 0     → fiat/provider_rate > platform_usdt → выигрыш в USDT на сделке")
    print()

    by_day = _aggregate(active, lambda r: r.platform.created_at.strftime("%Y-%m-%d") if r.platform.created_at else "?")
    by_hour = _aggregate(active, lambda r: r.platform.created_at.strftime("%Y-%m-%d %H:00") if r.platform.created_at else "?")

    print("--- По дням ---")
    for row in by_day:
        sign = "+" if row["rate_pnl_usdt"] >= 0 else ""
        print(
            f"  {row['period']} | {row['deals']} сд. | "
            f"курс {row['avg_our_rate']:.2f} vs {row['avg_provider_rate']:.2f} ({row['avg_rate_spread_pct']:+.2f}%) | "
            f"rate PnL {sign}{row['rate_pnl_usdt']:.4f} USDT | "
            f"комиссия {row['commission_usdt']:.2f} USDT | W/L {row['rate_wins']}/{row['rate_losses']}"
        )
    print()

    print("--- По часам (топ проигрышей) ---")
    by_hour_sorted = sorted(by_hour, key=lambda x: x["rate_pnl_usdt"])
    for row in by_hour_sorted[:12]:
        sign = "+" if row["rate_pnl_usdt"] >= 0 else ""
        print(
            f"  {row['period']} | {row['deals']} сд. | "
            f"курс {row['avg_our_rate']:.2f} vs {row['avg_provider_rate']:.2f} | "
            f"rate PnL {sign}{row['rate_pnl_usdt']:.4f} USDT | "
            f"комиссия {row['commission_usdt']:.2f} USDT"
        )
    print()

    # --- Commission section (bottom) ---
    comm_by_day: dict[str, Decimal] = defaultdict(lambda: Decimal0)
    comm_by_day_cnt: dict[str, int] = defaultdict(int)
    for d in plat_ok_clean:
        if not d.created_at:
            continue
        key = d.created_at.strftime("%Y-%m-%d")
        comm_by_day[key] += d.platform_commission_usdt
        comm_by_day_cnt[key] += 1

    comm_by_ps: dict[str, Decimal] = defaultdict(lambda: Decimal0)
    comm_by_ps_cnt: dict[str, int] = defaultdict(int)
    for d in plat_ok_clean:
        ps = d.payment_system or "(пусто)"
        comm_by_ps[ps] += d.platform_commission_usdt
        comm_by_ps_cnt[ps] += 1

    print("=" * 72)
    print("КОМИССИОННЫЙ ЗАРАБОТОК ПЛАТФОРМЫ (merchant_fee − trader_fee)")
    print("=" * 72)
    print("  --- По сопоставленным с провайдерами ---")
    for prov_name in sorted(by_provider):
        items = by_provider[prov_name]
        prov_comm = sum(r.platform.platform_commission_usdt for r in items)
        print(f"  {prov_name:10} | {len(items):4} сд. | комиссия {float(prov_comm):,.2f} USDT")
    print(f"  {'ИТОГО':10} | {len(active):4} сд. | комиссия {float(total_commission):,.2f} USDT")
    print()
    print(f"  --- По ВСЕЙ платформе ({len(plat_ok_clean)} успешных заявок) ---")
    print(f"  Суммарная комиссия: {float(plat_total_commission):,.2f} USDT")
    print(f"  Оборот USDT:        {float(plat_total_usdt):,.2f} USDT")
    print(f"  Оборот fiat:        {float(plat_total_fiat):,.2f}")
    print()
    print("  По платёжным системам:")
    for ps in sorted(comm_by_ps, key=lambda k: comm_by_ps[k], reverse=True):
        print(
            f"    {ps:12} {comm_by_ps_cnt[ps]:4} сд. | "
            f"комиссия {float(comm_by_ps[ps]):>10,.2f} USDT"
        )
    print()
    print("  Комиссия по дням (вся платформа):")
    for day in sorted(comm_by_day):
        print(
            f"    {day} | {comm_by_day_cnt[day]:4} сд. | "
            f"комиссия {float(comm_by_day[day]):>8,.2f} USDT"
        )
    print()

    print("=" * 72)
    print("СВОДКА: ПОЛНЫЙ ЗАРАБОТОК")
    print("=" * 72)
    print(f"  Заработок на курсе (сопоставленные {len(active)} пар):  {float(total_rate_pnl):+,.4f} USDT")
    print(f"  Комиссия (сопоставленные):                             {float(total_commission):,.2f} USDT")
    print(f"  Комиссия (ВСЯ платформа, {len(plat_ok_clean)} сд.):           {float(plat_total_commission):,.2f} USDT")
    print("-" * 72)
    print(f"  ИТОГО курс + комиссия (сопоставленные):                {float(total_rate_pnl + total_commission):+,.4f} USDT")
    print(f"  ИТОГО комиссия по всей платформе:                       {float(plat_total_commission):,.2f} USDT")
    if coverage_pct < 100:
        print(f"  (курс известен только для {coverage_pct:.0f}% сделок — полный rate PnL занижен)")
    print()

    base = Path(report_csv or platform_path).expanduser()
    if base.suffix:
        stem = base.with_suffix("")
    else:
        stem = base
    detail_path = str(stem) + "_detail.csv" if not report_csv else report_csv
    day_path = str(stem) + "_by_day.csv"
    hour_path = str(stem) + "_by_hour.csv"

    summary_path = str(stem) + "_summary.csv"
    summary_rows = [{
        "provider": prov_name,
        "deals": len(items),
        "total_fiat": float(sum(r.platform.amount_fiat for r in items)),
        "rate_pnl_usdt": float(sum(r.rate_pnl_usdt for r in items)),
        "rate_wins_usdt": float(sum(r.rate_pnl_usdt for r in items if r.rate_pnl_usdt > 0)),
        "rate_losses_usdt": float(sum(r.rate_pnl_usdt for r in items if r.rate_pnl_usdt < 0)),
        "commission_usdt": float(sum(r.platform.platform_commission_usdt for r in items)),
    } for prov_name, items in sorted(by_provider.items())]
    summary_rows.append({
        "provider": "ИТОГО (сопоставленные)",
        "deals": len(active),
        "total_fiat": float(total_fiat),
        "rate_pnl_usdt": float(total_rate_pnl),
        "rate_wins_usdt": float(sum_wins_usdt),
        "rate_losses_usdt": float(sum_losses_usdt),
        "commission_usdt": float(total_commission),
    })
    summary_rows.append({
        "provider": "ИТОГО (вся платформа)",
        "deals": len(plat_ok_clean),
        "total_fiat": float(plat_total_fiat),
        "rate_pnl_usdt": None,
        "rate_wins_usdt": None,
        "rate_losses_usdt": None,
        "commission_usdt": float(plat_total_commission),
    })

    comm_day_rows = [{
        "day": day,
        "deals": comm_by_day_cnt[day],
        "commission_usdt": float(comm_by_day[day]),
    } for day in sorted(comm_by_day)]
    comm_day_path = str(stem) + "_commission_by_day.csv"

    _write_csv(detail_path, [r.to_csv_dict() for r in matched])
    _write_csv(day_path, by_day)
    _write_csv(hour_path, by_hour)
    _write_csv(summary_path, summary_rows)
    _write_csv(comm_day_path, comm_day_rows)

    print("Готово.")
    return {
        "matched": len(active),
        "rate_pnl_usdt": float(total_rate_pnl),
        "rate_wins_usdt": float(sum_wins_usdt),
        "rate_losses_usdt": float(sum_losses_usdt),
        "commission_usdt": float(total_commission),
        "total_income_usdt": float(total_rate_pnl + total_commission),
        "platform_success_count": len(plat_ok_clean),
        "platform_total_fiat": float(plat_total_fiat),
        "platform_total_usdt": float(plat_total_usdt),
        "platform_total_commission_usdt": float(plat_total_commission),
        "matched_coverage_pct": float(coverage_pct),
        "excluded_synthetic": excluded_count,
        "detail_csv": detail_path,
        "by_day_csv": day_path,
        "by_hour_csv": hour_path,
        "summary_csv": summary_path,
        "commission_by_day_csv": comm_day_path,
    }


print("shell_reconcile_cash_register loaded")
print("  run(platform_path='...', expayone_path='...', protocol_path='...')")

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        run(sys.argv[1], sys.argv[2], sys.argv[3])
