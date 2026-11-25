"""Apply Mostbet routing = Pandapay-like cascade on the running server.

Prints the exact .env lines to set. Does not rewrite .env automatically
(restart needed). Verify with diagnose_routing after deploy.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_apply_mostbet_pandapay_cascade.py
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from django.conf import settings

from payments.psp_payin import (
    merchant_psp_priority_map,
    merchant_wants_psp_first,
    sort_groups_for_routing,
)

_PANDAPAY_CASCADE = {
    "patriot1": 1,
    "gipay1": 2,
    "prochub1": 3,
    "layerone1": 4,
    "plutus1": 98,
    "astrum_kzt": 97,
    "payplat1": 99,
}


def _merchant(name: str):
    return SimpleNamespace(user=SimpleNamespace(username=name))


print("=== Current settings ===")
print(f"PSP_ROUTING_PSP_FIRST_MERCHANTS={settings.PSP_ROUTING_PSP_FIRST_MERCHANTS!r}")
print(f"PSP_ROUTING_PRIORITY_BY_MERCHANT={settings.PSP_ROUTING_PRIORITY_BY_MERCHANT!r}")
print()
print(f"mostbet psp_first={merchant_wants_psp_first(_merchant('mostbet'))}")
print(f"pandapay psp_first={merchant_wants_psp_first(_merchant('pandapay'))}")
print(f"mostbet map={merchant_psp_priority_map(_merchant('mostbet'))}")
print(f"pandapay map={merchant_psp_priority_map(_merchant('pandapay'))}")
print()

desired_map = {
    "pandapay": dict(_PANDAPAY_CASCADE),
    "mostbet": dict(_PANDAPAY_CASCADE),
    "aggrepay": {"astrum_kzt": 1},
}
desired_first = "aggrepay"

print("=== Put these in server .env (then restart app) ===")
print(
    "PSP_ROUTING_PRIORITY_BY_MERCHANT="
    + json.dumps(desired_map, separators=(",", ":"), ensure_ascii=False)
)
print(f"PSP_ROUTING_PSP_FIRST_MERCHANTS={desired_first}")
print()
print("After restart expect:")
print("  mostbet psp_first=False")
print("  mostbet map == pandapay map")
print("  order: live traders → patriot1 → gipay1 → prochub1 → layerone1 → …")
print()
print(
    "Verify:\n"
    "  docker compose exec -T app python manage.py diagnose_routing mostbet "
    "--ps C2CKZT --amount 3000 --ftd false"
)
