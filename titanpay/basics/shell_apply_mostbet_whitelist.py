"""Mostbet: актуализировать IP whitelist на API-ключах.

Адреса от мерчанта (2026-11-27):
  49.12.245.121
  49.12.221.218
  212.224.113.206
  212.224.113.113
  185.26.97.90
  185.26.97.102
  162.248.160.16
  3.65.76.171

  # dry-run
  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_apply_mostbet_whitelist.py

  # записать
  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_apply_mostbet_whitelist.py
"""
from __future__ import annotations

import os

from merchant.models import Merchant
from payments.models import APIKeys

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
MERCHANT = (os.environ.get("MERCHANT") or "mostbet").strip()
WHITELIST_ON = (os.environ.get("WHITELIST_ON") or "1").strip().lower() in {
    "1",
    "true",
    "yes",
}

DEFAULT_IPS = [
    "49.12.245.121",
    "49.12.221.218",
    "212.224.113.206",
    "212.224.113.113",
    "185.26.97.90",
    "185.26.97.102",
    "162.248.160.16",
    "3.65.76.171",
]


def _parse_ips(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_IPS)
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        ip = part.strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        out.append(ip)
    return out


TARGET_IPS = _parse_ips(os.environ.get("IPS"))


def run() -> None:
    print(
        f"APPLY={int(APPLY)}  merchant={MERCHANT}  "
        f"whitelist_on→{WHITELIST_ON}  ips={len(TARGET_IPS)}"
    )
    for ip in TARGET_IPS:
        print(f"  + {ip}")

    merchant = (
        Merchant.objects.select_related("user")
        .filter(user__username__iexact=MERCHANT)
        .first()
    )
    if merchant is None:
        print("! merchant not found")
        return

    keys = list(
        APIKeys.objects.filter(merchant=merchant, active=True).order_by("-created_at")
    )
    if not keys:
        print("! no active API keys")
        return

    for key in keys:
        old = key.whitelist_ips if isinstance(key.whitelist_ips, list) else []
        print(
            f"  key id={key.id} whitelist_on={key.whitelist_on} "
            f"ips={len(old)} → {len(TARGET_IPS)}"
        )
        removed = sorted(set(old) - set(TARGET_IPS))
        added = sorted(set(TARGET_IPS) - set(old))
        if removed:
            print(f"    - remove: {removed}")
        if added:
            print(f"    + add: {added}")
        if not removed and not added and key.whitelist_on == WHITELIST_ON:
            print("    (already up to date)")
            continue
        if APPLY:
            key.update_whitelist(WHITELIST_ON, list(TARGET_IPS))
            print("    APPLIED")
        else:
            print("    (dry-run)")


run()
