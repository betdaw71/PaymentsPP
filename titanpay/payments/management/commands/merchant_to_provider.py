"""
merchant_order_id → provider_id (FairPay / ExpayOne / Protocol / Playments).

Примеры:
  python manage.py merchant_to_provider 23501162683 23500174835
  python manage.py merchant_to_provider --file /tmp/ids.txt
  python manage.py merchant_to_provider --csv
  python manage.py merchant_to_provider --builtin   # список из запроса (ниже)
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from payments.models import (
    ExpayonePayInSession,
    FairpayPayInSession,
    PayIn,
    PayOut,
    PlaymentsPayInSession,
    PlaymentsPayOutSession,
    ProtocolPayInSession,
)

# Merchant order IDs из срочного запроса
BUILTIN_MERCHANT_ORDER_IDS = [
    "23501162683",
    "23500174835",
    "23500125163",
    "23497395823",
    "23496192495",
    "23495727527",
    "23495715697",
    "23495071459",
    "23455789371",
    "23452450137",
    "23452256637",
    "23452116307",
    "23438369987",
    "23437913175",
    "23436080565",
    "23436067911",
    "23434188727",
    "23430457667",
    "23425357701",
    "23425338389",
    "23422395657",
    "23420413807",
    "23419938051",
    "23419810121",
    "23417389245",
    "23416457895",
    "23416385745",
    "23415840161",
    "23410890861",
    "23408449009",
    "23407870041",
    "23407503039",
    "23406150025",
    "23404922339",
    "23397159915",
    "23396613645",
    "23396245871",
    "23395938275",
    "23395929441",
    "23395921711",
    "23395909453",
    "23395816583",
    "23395749667",
    "23395587903",
    "23395543079",
    "23395535749",
    "23395312345",
    "23395231945",
    "23395134129",
    "23394188051",
    "23392190241",
    "23390798809",
    "23389861395",
    "23389398127",
    "23388197537",
    "23386907895",
    "23385790241",
    "23378778821",
    "23372020427",
]


def _provider_maps(payin_pks: list) -> dict:
    """pay_in_id → (provider_name, provider_id). Приоритет: fairpay → expayone → protocol → playments."""
    out: dict = {}
    if not payin_pks:
        return out

    for s in FairpayPayInSession.objects.filter(pay_in_id__in=payin_pks).exclude(provider_order_id=None):
        out[s.pay_in_id] = ("fairpay", str(s.provider_order_id))

    for s in ExpayonePayInSession.objects.filter(pay_in_id__in=payin_pks).exclude(provider_order_id=""):
        out.setdefault(s.pay_in_id, ("expayone", str(s.provider_order_id)))

    for s in ProtocolPayInSession.objects.filter(pay_in_id__in=payin_pks).exclude(provider_payment_id=""):
        out.setdefault(s.pay_in_id, ("protocol", str(s.provider_payment_id)))

    for s in PlaymentsPayInSession.objects.filter(pay_in_id__in=payin_pks).exclude(provider_deposit_id=""):
        out.setdefault(s.pay_in_id, ("playments", str(s.provider_deposit_id)))

    return out


def _payout_provider_maps(payout_pks: list) -> dict:
    out: dict = {}
    if not payout_pks:
        return out
    for s in PlaymentsPayOutSession.objects.filter(pay_out_id__in=payout_pks).exclude(provider_withdrawal_id=""):
        out[s.pay_out_id] = ("playments", str(s.provider_withdrawal_id))
    return out


def resolve_ids(merchant_order_ids: list[str]) -> list[dict]:
    """Сопоставить merchant_order_id → provider_id (PayIn, затем PayOut)."""
    ids = [str(x).strip() for x in merchant_order_ids if str(x).strip()]
    if not ids:
        return []

    payins = {
        p.merchant_order_id: p
        for p in PayIn.objects.filter(merchant_order_id__in=ids).select_related("status", "merchant__user")
    }
    payouts = {
        p.merchant_order_id: p
        for p in PayOut.objects.filter(merchant_order_id__in=ids).select_related("status", "merchant__user")
    }
    provider_by_payin = _provider_maps([p.id for p in payins.values()])
    provider_by_payout = _payout_provider_maps([p.id for p in payouts.values()])

    rows: list[dict] = []
    for mid in ids:
        pay_in = payins.get(mid)
        if pay_in is not None:
            provider, provider_id = provider_by_payin.get(pay_in.id, ("", ""))
            rows.append(
                {
                    "merchant_order_id": mid,
                    "type": "payin",
                    "internal_id": str(pay_in.id),
                    "merchant": pay_in.merchant.user.username if pay_in.merchant else "",
                    "status": pay_in.status.name if pay_in.status else "",
                    "provider": provider,
                    "provider_id": provider_id,
                    "found": True,
                }
            )
            continue

        pay_out = payouts.get(mid)
        if pay_out is not None:
            provider, provider_id = provider_by_payout.get(pay_out.id, ("", ""))
            rows.append(
                {
                    "merchant_order_id": mid,
                    "type": "payout",
                    "internal_id": str(pay_out.id),
                    "merchant": pay_out.merchant.user.username if pay_out.merchant else "",
                    "status": pay_out.status.name if pay_out.status else "",
                    "provider": provider,
                    "provider_id": provider_id,
                    "found": True,
                }
            )
            continue

        rows.append(
            {
                "merchant_order_id": mid,
                "type": "",
                "internal_id": "",
                "merchant": "",
                "status": "",
                "provider": "",
                "provider_id": "",
                "found": False,
            }
        )
    return rows


class Command(BaseCommand):
    help = "По merchant_order_id вывести provider_id (FairPay / ExpayOne / Protocol / Playments)"

    def add_arguments(self, parser):
        parser.add_argument(
            "ids",
            nargs="*",
            help="merchant_order_id (пробел/несколько аргументов)",
        )
        parser.add_argument(
            "--file",
            "-f",
            type=str,
            help="Файл: один merchant_order_id на строку",
        )
        parser.add_argument(
            "--builtin",
            action="store_true",
            help="Использовать встроенный список из срочного запроса",
        )
        parser.add_argument(
            "--csv",
            action="store_true",
            help="Вывод в CSV (иначе TSV)",
        )
        parser.add_argument(
            "--provider-only",
            action="store_true",
            help="Только provider_id (по одному на строку; пусто если не найден)",
        )

    def handle(self, *args, **options):
        ids: list[str] = list(options.get("ids") or [])
        if options.get("file"):
            text = Path(options["file"]).read_text(encoding="utf-8")
            ids.extend(line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))
        if options.get("builtin") or not ids:
            if not ids:
                self.stderr.write("ID не переданы — берём --builtin список")
            ids.extend(BUILTIN_MERCHANT_ORDER_IDS)

        # уникальные с сохранением порядка
        seen: set[str] = set()
        ordered: list[str] = []
        for mid in ids:
            mid = str(mid).strip()
            if mid and mid not in seen:
                seen.add(mid)
                ordered.append(mid)

        rows = resolve_ids(ordered)
        found = sum(1 for r in rows if r["found"])
        with_provider = sum(1 for r in rows if r["provider_id"])
        missing = sum(1 for r in rows if not r["found"])

        if options.get("provider_only"):
            for r in rows:
                self.stdout.write(r["provider_id"] or "")
        elif options.get("csv"):
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=[
                    "merchant_order_id",
                    "provider",
                    "provider_id",
                    "type",
                    "internal_id",
                    "merchant",
                    "status",
                    "found",
                ],
            )
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        else:
            header = (
                "merchant_order_id\tprovider\tprovider_id\ttype\tinternal_id\tmerchant\tstatus"
            )
            self.stdout.write(header)
            for r in rows:
                self.stdout.write(
                    f"{r['merchant_order_id']}\t{r['provider']}\t{r['provider_id']}\t"
                    f"{r['type']}\t{r['internal_id']}\t{r['merchant']}\t{r['status']}"
                )

        self.stderr.write(
            f"\nИтого: {len(rows)} | найдено: {found} | с provider_id: {with_provider} | не найдено: {missing}"
        )
