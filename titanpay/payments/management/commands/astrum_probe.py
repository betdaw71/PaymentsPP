"""Безопасные проверки Astrum API: info / balance / methods / optional dry create.

Примеры (на сервере с whitelist IP Astrum):

  docker compose exec -T app python manage.py astrum_probe --info --balance --methods

  # Dry-run: только шифрует payload, НЕ шлёт create
  docker compose exec -T app python manage.py astrum_probe --dry-create \\
    --amount 1000 --card 4400430123456789 --initials "Test User"

  # Реальный create на Astrum (осторожно — списывает баланс провайдера)
  docker compose exec -T app python manage.py astrum_probe --create \\
    --amount 1000 --card 4400430123456789 --initials "Test User" --foreign-id astrum-test-001

  docker compose exec -T app python manage.py astrum_probe --status --foreign-id astrum-test-001
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from payments.astrum_client import (
    astrum_create_payout,
    astrum_get_balance,
    astrum_get_info,
    astrum_get_methods,
    astrum_get_payout_info,
    encrypt_application,
)


class Command(BaseCommand):
    help = "Probe Astrum API (info/balance/methods) and optionally create a test payout"

    def add_arguments(self, parser):
        parser.add_argument("--info", action="store_true", help="GET /source/info/api")
        parser.add_argument("--balance", action="store_true", help="GET /source/balance/api/currency")
        parser.add_argument("--methods", action="store_true", help="GET /source/methods")
        parser.add_argument("--dry-create", action="store_true", help="Build+encrypt payload only")
        parser.add_argument("--create", action="store_true", help="POST real payout create (spends balance)")
        parser.add_argument("--status", action="store_true", help="GET payout info by foreign id")
        parser.add_argument("--amount", type=str, default="1000")
        parser.add_argument("--card", type=str, default="")
        parser.add_argument("--initials", type=str, default="Test User")
        parser.add_argument("--foreign-id", type=str, default="")
        parser.add_argument("--method-type-id", type=int, default=None)
        parser.add_argument("--method-name-id", type=int, default=None)
        parser.add_argument("--express", action="store_true")
        parser.add_argument("--currency", type=str, default="KZT")

    def handle(self, *args, **options):
        any_action = any(
            options[k]
            for k in ("info", "balance", "methods", "dry_create", "create", "status")
        )
        if not any_action:
            options["info"] = True
            options["balance"] = True
            options["methods"] = True

        if options["info"]:
            ok, data = astrum_get_info()
            self._print("info", ok, data)
        if options["balance"]:
            ok, data = astrum_get_balance()
            self._print("balance", ok, data)
        if options["methods"]:
            ok, data = astrum_get_methods()
            self._print("methods", ok, data)
            if ok and isinstance(data, dict):
                result = data.get("result") or {}
                types = result.get("methodTypes") or []
                names = result.get("methodNames") or []
                self.stdout.write(self.style.HTTP_INFO("\n--- methodTypes (set ASTRUM_METHOD_TYPE_ID) ---"))
                for row in types:
                    self.stdout.write(f"  id={row.get('id')}  name={row.get('name')}")
                self.stdout.write(self.style.HTTP_INFO("\n--- methodNames (optional ASTRUM_METHOD_NAME_ID) ---"))
                for row in names:
                    self.stdout.write(f"  id={row.get('id')}  name={row.get('name')}")

        if options["status"]:
            fid = (options["foreign_id"] or "").strip()
            if not fid:
                raise CommandError("--status requires --foreign-id")
            ok, data = astrum_get_payout_info(fid)
            self._print("status", ok, data)

        if options["dry_create"] or options["create"]:
            card = (options["card"] or "").strip().replace(" ", "")
            if not card:
                raise CommandError("--card is required for create/dry-create")
            foreign_id = (options["foreign_id"] or "").strip() or f"astrum-dry-{uuid.uuid4().hex[:12]}"

            method_type_id = options["method_type_id"]
            if method_type_id is None:
                raw = (getattr(settings, "ASTRUM_METHOD_TYPE_ID", None) or "").strip()
                if not raw:
                    raise CommandError("Set ASTRUM_METHOD_TYPE_ID or pass --method-type-id")
                method_type_id = int(raw)

            method_name_id = options["method_name_id"]
            if method_name_id is None:
                raw_n = (getattr(settings, "ASTRUM_METHOD_NAME_ID", None) or "").strip()
                method_name_id = int(raw_n) if raw_n else None

            payload = {
                "foreignId": foreign_id,
                "amount": float(Decimal(options["amount"])),
                "requisite": card,
                "methodTypeId": method_type_id,
                "methodNameId": method_name_id,
                "clientInitials": options["initials"],
                "express": bool(options["express"]),
                "currency": options["currency"],
            }
            token = encrypt_application(payload)
            if not token:
                raise CommandError("ASTRUM_PRIVATE_KEY missing/invalid — cannot Fernet-encrypt")
            self.stdout.write(self.style.HTTP_INFO(f"\npayload={json.dumps(payload, ensure_ascii=False)}"))
            self.stdout.write(f"encrypted_application length={len(token)}")

            if options["dry_create"] and not options["create"]:
                self.stdout.write(self.style.SUCCESS("dry-create only — request NOT sent"))
                return

            if options["create"]:
                self.stdout.write(self.style.WARNING("Sending REAL create to Astrum…"))
                ok, data = astrum_create_payout(
                    foreign_id=foreign_id,
                    amount=Decimal(options["amount"]),
                    requisite=card,
                    client_initials=options["initials"],
                    method_type_id=method_type_id,
                    method_name_id=method_name_id,
                    express=bool(options["express"]),
                    currency=options["currency"],
                )
                self._print("create", ok, data)
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"foreignId={foreign_id}"))

    def _print(self, label: str, ok: bool, data):
        style = self.style.SUCCESS if ok else self.style.ERROR
        self.stdout.write(style(f"\n=== {label} ok={ok} ==="))
        self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str)[:8000])
