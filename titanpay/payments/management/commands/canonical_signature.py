"""Показать канонический JSON и подпись для тела мерчанта / callback."""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from payments.signing import canonical_json, sign_canonical


class Command(BaseCommand):
    help = (
        "Канонический JSON для Signature: ключи отсортированы, без пробелов. "
        "Для callback не используйте тело create — только тело callback."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            dest="raw_json",
            help="JSON-тело (create или callback), одной строкой",
        )
        parser.add_argument(
            "--merchant",
            help="username мерчанта: посчитать реальную Signature активным ключом",
        )
        parser.add_argument(
            "--payin",
            help="PayIn.id или merchant_order_id: взять поля последнего callback из тела заявки",
        )

    def handle(self, *args, **options):
        payload = None
        if options.get("payin"):
            payload = self._payload_from_payin(options["payin"])
        elif options.get("raw_json"):
            try:
                payload = json.loads(options["raw_json"])
            except json.JSONDecodeError as exc:
                raise CommandError(f"invalid JSON: {exc}") from exc
        else:
            raise CommandError("Передайте --json '{...}' или --payin <id|moid>")

        dumped = canonical_json(payload)
        self.stdout.write("canonical JSON:")
        self.stdout.write(dumped)
        self.stdout.write("")
        self.stdout.write(
            "Проверка: Signature = SHA256(эта_строка + private_key_с_дефисами). "
            "PHP: json_encode(..., JSON_UNESCAPED_SLASHES) + ksort рекурсивно. "
            "Не json_encode заново целое 10800.0 → 10800. Для callback берите RAW body."
        )

        merchant_name = options.get("merchant")
        if merchant_name:
            from merchant.models import Merchant

            merchant = Merchant.objects.filter(user__username=merchant_name).first()
            if merchant is None:
                raise CommandError(f"merchant {merchant_name!r} not found")
            api_key = merchant.api_keys.filter(active=True).order_by("-created_at").first()
            if api_key is None:
                raise CommandError("no active APIKeys")
            sig, _ = sign_canonical(payload, api_key.private_key)
            self.stdout.write("")
            self.stdout.write(f"key_created_at: {api_key.created_at}")
            self.stdout.write(f"Signature:      {sig}")

    def _payload_from_payin(self, ref: str):
        from payments.models import PayIn
        from django.utils import timezone

        qs = PayIn.objects.select_related("currency", "payment_system", "order", "merchant")
        pay_in = qs.filter(id=ref).first() if len(ref) == 36 else None
        if pay_in is None:
            pay_in = qs.filter(merchant_order_id=ref).first()
        if pay_in is None:
            raise CommandError(f"PayIn {ref!r} not found")
        return {
            "id": str(pay_in.id),
            "order_id": pay_in.merchant_order_id,
            "amount": float(pay_in.amount),
            "currency": pay_in.currency.symbol if pay_in.currency else None,
            "payment_system": pay_in.payment_system.name if pay_in.payment_system else None,
            "status": pay_in.status.name if pay_in.status else None,
            "recalculated": bool(pay_in.order.recalculated) if pay_in.order else False,
            "timestamp": int(timezone.now().timestamp()),
        }
