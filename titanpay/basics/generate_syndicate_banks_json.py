"""
Сгенерировать payments/data/syndicate_banks.json из выгрузки Syndicate (xlsx).

  python3 titanpay/basics/generate_syndicate_banks_json.py /path/to/banks-*.xlsx

Колонки xlsx: ID, Название, Код банка, Код НСПК, Страна, ...
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

PS_HINTS: dict[str, list[str]] = {
    "Sber": ["сбер", "sberbank"],
    "SberPay": ["сбер", "sberbank"],
    "SberDep": ["сбер", "sberbank"],
    "Tinkoff": ["т-банк", "тиньк", "tinkoff"],
    "TBANK": ["т-банк", "tinkoff"],
    "Alfa": ["альфа", "alfa"],
    "OTP": ["отп", "otp"],
    "C2C": ["any-bank"],
    "SBP": ["sbp"],
}


def _cell_text(cell) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//m:t", NS))
    v = cell.find("m:v", NS)
    return v.text if v is not None else ""


def _col_letter(ref: str) -> str:
    m = re.match(r"([A-Z]+)", ref)
    return m.group(1) if m else ""


def parse_banks_xlsx(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))

    banks: list[dict] = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells: dict[str, str] = {}
        for c in row.findall("m:c", NS):
            cells[_col_letter(c.get("r", ""))] = _cell_text(c)
        code = (cells.get("C") or "").strip()
        name = (cells.get("B") or "").strip()
        if not code or code.lower() == "код банка":
            continue
        banks.append(
            {
                "id": (cells.get("A") or "").strip(),
                "name": name,
                "code": code,
                "nspk_code": (cells.get("D") or "").strip() or None,
                "country": (cells.get("E") or "").strip() or None,
                "mobile_operator": (cells.get("F") or "").strip(),
                "phone_format": (cells.get("G") or "").strip() or None,
                "currency": (cells.get("H") or "").strip() or None,
                "cross_border_conversion": (cells.get("I") or "").strip() or None,
                "sbp_queue": (cells.get("N") or "").strip() or None,
                "account_queue": (cells.get("O") or "").strip() or None,
            }
        )
    return banks


def build_payment_system_map(banks: list[dict]) -> dict[str, str]:
    out = {"C2C": "any-bank", "SBP": "sbp"}
    for ps, hints in PS_HINTS.items():
        if ps in out:
            continue
        for bank in banks:
            nl = bank["name"].lower()
            cl = bank["code"].lower()
            if any(h in nl or h == cl for h in hints):
                out[ps] = bank["code"]
                break
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <banks.xlsx>")
    src = Path(sys.argv[1]).expanduser().resolve()
    banks = parse_banks_xlsx(src)
    ps_map = build_payment_system_map(banks)
    # каждый код банка → сам себя (если в TitanPay заведут PS = code Syndicate)
    for bank in banks:
        code = bank["code"]
        if code and code not in ("any-bank", "sbp") and code not in ps_map.values():
            key = code
            if key not in ps_map:
                ps_map[key] = code

    out_path = Path(__file__).resolve().parents[1] / "payments" / "data" / "syndicate_banks.json"
    payload = {
        "source_file": src.name,
        "count": len(banks),
        "banks": banks,
        "payment_system_to_bank_code": ps_map,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({len(banks)} banks, {len(ps_map)} PS mappings)")


if __name__ == "__main__":
    main()
