"""Прод-запуск: включить Astrum (asterisk) ~30% share, выключить Plutus.

Шаги на сервере:
  1) .env:
     PSP_ROUTING_SHARE_MAP={"patriot1":25,"gipay1":20,"prochub1":15,"visionx1":10,"astrum_kzt":30}
     PSP_ROUTING_PRIORITY_MAP=…,"astrum_kzt":6,…,"plutus1":98,…
     PSP_XE_MARKUP_BY_TRADER=…,"astrum_kzt":"1.03"…
     ASTRUM_API_KEY / ASTRUM_PRIVATE_KEY / ASTRUM_METHOD_TYPE_ID

  2) docker compose up -d app

  3) Применить БД:
     docker compose exec -T -e APPLY=1 app python manage.py shell \\
       < titanpay/basics/shell_ensure_astrum_payin_prod.py
     docker compose exec -T -e DISABLE=1 app python manage.py shell \\
       < titanpay/basics/shell_plutus_ensure_prod.py

  4) Ставки 6%:
     docker compose exec -T -e APPLY=1 app python manage.py shell \\
       < titanpay/basics/shell_apply_psp_kzt_terms.py

  5) Замер:
     docker compose exec -T -e HOURS=6 app python manage.py shell \\
       < titanpay/basics/shell_astrum_metrics.py

Этот файл — чеклист + dry-run статуса (без APPLY).
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings

from basics.models import PaymentDetailsGroup, Trader
from payments.astrum_client import astrum_trader_username
from payments.plutus_client import plutus_trader_username
from payments.psp_payin import parse_routing_share_map

TARGET_SHARE = Decimal("30")
SHARE_LINE = '{"patriot1":25,"gipay1":20,"prochub1":15,"visionx1":10,"astrum_kzt":30}'


def _group_summary(username: str) -> list[str]:
    trader = Trader.objects.filter(user__username__iexact=username).first()
    if trader is None:
        return [f"! trader {username} missing"]
    rows = []
    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related(
        "payment_system", "payment_system__currency"
    ):
        cur = g.payment_system.currency.symbol if g.payment_system and g.payment_system.currency_id else "?"
        rows.append(
            f"  {g.payment_system.name:12} {cur:4} in_active={g.in_active} status={g.status}"
        )
    return rows or ["  (no groups)"]


def run() -> None:
    astrum = astrum_trader_username()
    plutus = plutus_trader_username()
    share = parse_routing_share_map()
    print("=== Launch checklist: Astrum ON / Plutus OFF ===")
    print(f"нужно в .env: PSP_ROUTING_SHARE_MAP={SHARE_LINE}")
    print(f"PSP_ROUTING_SHARE_MAP now: {{{', '.join(f'{k}:{v}' for k, v in share.items())}}}" if share else "PSP_ROUTING_SHARE_MAP now: {}")
    print(f"PSP_ROUTING_PRIORITY_MAP={getattr(settings, 'PSP_ROUTING_PRIORITY_MAP', '')}")

    a_w = share.get(astrum.lower())
    p_w = share.get(plutus.lower())
    if a_w is None:
        print(f"! {astrum} нет в SHARE — поставь {TARGET_SHARE}%")
    else:
        total = sum(share.values()) or Decimal("1")
        pct = (a_w / total) * Decimal("100")
        mark = "OK" if abs(pct - TARGET_SHARE) <= Decimal("1") else "WARN"
        print(f"{mark}: {astrum} share≈{pct:.1f}% (target {TARGET_SHARE}%)")
    if p_w is None:
        print(f"OK: {plutus} нет в SHARE")
    else:
        print(f"! {plutus} всё ещё в SHARE={p_w} — убери из .env")

    print(f"\n{astrum} groups:")
    for line in _group_summary(astrum):
        print(line)
    print(f"\n{plutus} groups:")
    for line in _group_summary(plutus):
        print(line)

    api_ok = bool((getattr(settings, "ASTRUM_API_KEY", None) or "").strip())
    key_ok = bool((getattr(settings, "ASTRUM_PRIVATE_KEY", None) or "").strip())
    mt = (getattr(settings, "ASTRUM_METHOD_TYPE_ID", None) or "").strip()
    print(f"\nASTRUM_API_KEY={int(api_ok)} PRIVATE_KEY={int(key_ok)} METHOD_TYPE_ID={mt or '-'}")
    print("DONE (dry-run). APPLY через shell_ensure_astrum / shell_plutus DISABLE=1")


run()
