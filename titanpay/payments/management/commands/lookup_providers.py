"""Быстрый lookup: PayIn UUID → id и имя провайдера (PSP).

Примеры:
  python manage.py lookup_providers c360f0ea-52c0-48e2-9032-514eb8590be6 ...
  python manage.py lookup_providers --stdin < ids.txt
  # можно вставить сырой текст из Telegram (a…g вокруг UUID) — нормализуется
"""
from __future__ import annotations

import re
import sys
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import (
    ExpayonePayInSession,
    FairpayPayInSession,
    PayIn,
    PlaymentsPayInSession,
    ProtocolPayInSession,
)
from trade.models import InOrder

# Telegram-копипаст часто даёт a<uuid>g; также вытаскиваем UUID из произвольного текста
_UUID_RE = re.compile(
    r"(?:^|[^0-9a-fA-F])a?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})g?(?:[^0-9a-fA-F]|$)"
)
_BARE_TG_RE = re.compile(
    r"^a([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})g$",
    re.I,
)


def extract_ids(text: str) -> list[str]:
    """Извлечь уникальные UUID из текста (сохраняя порядок)."""
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _BARE_TG_RE.match(s)
        if m:
            uid = m.group(1).lower()
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
            continue
        for m in _UUID_RE.finditer(s):
            uid = m.group(1).lower()
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
        # голый UUID без окружения
        if re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            s,
        ):
            uid = s.lower()
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
    return out


def _psp_for_pay_in(pay_in: PayIn) -> tuple[str, str]:
    """Вернуть (provider_name, provider_id) или ('', '')."""
    s = FairpayPayInSession.objects.filter(pay_in=pay_in).first()
    if s is not None and s.provider_order_id is not None:
        return "fairpay", str(s.provider_order_id)

    s = ExpayonePayInSession.objects.filter(pay_in=pay_in).first()
    if s is not None and s.provider_order_id:
        return "expayone", str(s.provider_order_id)

    s = ProtocolPayInSession.objects.filter(pay_in=pay_in).first()
    if s is not None and s.provider_payment_id:
        return "protocol", str(s.provider_payment_id)

    s = PlaymentsPayInSession.objects.filter(pay_in=pay_in).first()
    if s is not None and s.provider_deposit_id:
        return "playments", str(s.provider_deposit_id)

    return "", ""


def _trader_fallback(order: InOrder | None) -> tuple[str, str]:
    if not order or not order.payment_details_id:
        return "", ""
    try:
        trader = order.payment_details.group.trader
        return f"trader:{trader.user.username}", str(trader.id)
    except Exception:
        return "", ""


def _age(dt) -> str:
    if not dt:
        return ""
    delta = timezone.now() - dt
    if delta < timedelta(0):
        delta = timedelta(0)
    total_min = int(delta.total_seconds() // 60)
    h, m = divmod(total_min, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


_PAYIN_SELECT = (
    "status",
    "order",
    "order__status",
    "order__payment_details__group__trader__user",
)


def resolve_one(raw_id: str) -> dict:
    row = {
        "id": raw_id,
        "kind": "",
        "provider": "",
        "provider_id": "",
        "status": "",
        "order_status": "",
        "merchant_order": "",
        "amount": "",
        "age": "",
        "error": "",
    }

    pay_in = PayIn.objects.select_related(*_PAYIN_SELECT).filter(id=raw_id).first()

    if pay_in is None:
        # иногда в чат кидают InOrder.id
        order = (
            InOrder.objects.select_related(
                "status",
                "payment_details__group__trader__user",
            )
            .filter(id=raw_id)
            .first()
        )
        if order is None:
            row["error"] = "not found"
            return row
        pay_in = PayIn.objects.select_related(*_PAYIN_SELECT).filter(order=order).first()
        if pay_in is None:
            provider, provider_id = _trader_fallback(order)
            row["kind"] = "inorder"
            row["status"] = order.status.name if order.status else ""
            row["order_status"] = row["status"]
            row["amount"] = str(order.amount)
            row["age"] = _age(order.creation_date)
            row["provider"] = provider
            row["provider_id"] = provider_id
            row["error"] = "no pay_in"
            return row
        row["kind"] = "inorder→payin"
        row["id"] = str(pay_in.id)
    else:
        row["kind"] = "payin"

    provider, provider_id = _psp_for_pay_in(pay_in)
    if not provider:
        provider, provider_id = _trader_fallback(pay_in.order)

    row["provider"] = provider
    row["provider_id"] = provider_id
    row["status"] = pay_in.status.name if pay_in.status else ""
    if pay_in.order and pay_in.order.status:
        row["order_status"] = pay_in.order.status.name
    row["merchant_order"] = pay_in.merchant_order_id or ""
    row["amount"] = str(pay_in.amount)
    row["age"] = _age(pay_in.created_at)
    return row


class Command(BaseCommand):
    help = "Рядом с каждым PayIn UUID вывести id и название провайдера (PSP/trader)"

    def add_arguments(self, parser):
        parser.add_argument(
            "ids",
            nargs="*",
            help="PayIn / InOrder UUID (можно a<uuid>g из Telegram)",
        )
        parser.add_argument(
            "--stdin",
            action="store_true",
            help="Читать id / сырой текст из stdin",
        )
        parser.add_argument(
            "--tsv",
            action="store_true",
            help="Только TSV: id\\tprovider_id\\tprovider (удобно вставить в чат)",
        )
        parser.add_argument(
            "--compact",
            action="store_true",
            help="Одна строка: id | provider_id | provider",
        )

    def handle(self, *args, **options):
        chunks: list[str] = []
        if options["ids"]:
            chunks.append("\n".join(options["ids"]))

        read_stdin = options["stdin"] or not options["ids"]
        if read_stdin:
            if sys.stdin.isatty():
                self.stderr.write(
                    "Вставьте список id (можно сырой текст из Telegram), затем Ctrl-D:"
                )
            chunks.append(sys.stdin.read())

        text = "\n".join(chunks)
        ids = extract_ids(text)
        if not ids:
            self.stderr.write(self.style.ERROR("Не найдено ни одного UUID"))
            self.stderr.write(
                "Пример: python manage.py lookup_providers --compact --stdin < ids.txt"
            )
            return

        rows = [resolve_one(i) for i in ids]

        if options["tsv"]:
            self.stdout.write("id\tprovider_id\tprovider\tstatus\tage")
            for r in rows:
                self.stdout.write(
                    f"{r['id']}\t{r['provider_id']}\t{r['provider']}\t"
                    f"{r['status']}\t{r['age']}"
                    + (f"\t{r['error']}" if r["error"] else "")
                )
            return

        if options["compact"]:
            for r in rows:
                extra = f" [{r['error']}]" if r["error"] else ""
                self.stdout.write(
                    f"{r['id']} | {r['provider_id'] or '-'} | {r['provider'] or '-'}{extra}"
                )
            return

        # таблица для терминала
        headers = (
            "pay_in_id",
            "provider_id",
            "provider",
            "payin_status",
            "order_status",
            "amount",
            "age",
            "note",
        )
        table = [headers]
        for r in rows:
            table.append(
                (
                    r["id"],
                    r["provider_id"] or "-",
                    r["provider"] or "-",
                    r["status"] or "-",
                    r["order_status"] or "-",
                    r["amount"] or "-",
                    r["age"] or "-",
                    r["error"] or "",
                )
            )

        widths = [max(len(str(row[i])) for row in table) for i in range(len(headers))]
        for i, row in enumerate(table):
            line = "  ".join(str(cell).ljust(widths[j]) for j, cell in enumerate(row))
            if i == 0:
                self.stdout.write(self.style.HTTP_INFO(line))
                self.stdout.write(self.style.HTTP_INFO("  ".join("-" * w for w in widths)))
            elif row[-1]:
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)

        missing = sum(1 for r in rows if r["error"] == "not found")
        no_prov = sum(1 for r in rows if not r["provider"] and not r["error"])
        self.stdout.write("")
        self.stdout.write(
            f"всего: {len(rows)}  не найдено: {missing}  без провайдера: {no_prov}"
        )
