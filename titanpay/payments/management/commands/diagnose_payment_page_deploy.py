"""Проверка деплоя платёжной страницы (чек, Kaspi guide, enrich)."""
from pathlib import Path

from django.core.management.base import BaseCommand

from payments.bank_guides import build_bank_guides
from payments.payment_page_assets import kaspi_guide_public_url
from payments.receipt_policy import receipt_required_for_payin


class Command(BaseCommand):
    help = "Проверить, что в контейнере есть код чека/Kaspi guide и файлы ассетов"

    def handle(self, *args, **options):
        enrich_path = Path(__file__).resolve().parents[2] / "payment_page_enrich.py"
        enrich_src = enrich_path.read_text(encoding="utf-8")
        checks = [
            ("receipt_required in enrich", "receipt_required" in enrich_src),
            ("bank_guides in enrich", "bank_guides" in enrich_src),
            ("receipt_policy module", True),
        ]
        asset = (
            Path(__file__).resolve().parents[2]
            / "static"
            / "payment_page"
            / "kaspi-international-transfers-guide.png"
        )
        checks.append(("kaspi png in repo", asset.is_file()))
        checks.append(("kaspi asset URL", bool(kaspi_guide_public_url())))

        guides = build_bank_guides(currency="KZT", locale="ru", bank_actions=[{"id": "kaspi", "label": "Kaspi"}])
        checks.append(("build_bank_guides KZT", len(guides) == 1))

        self.stdout.write(self.style.HTTP_INFO("\n=== Payment page deploy check ===\n"))
        ok = True
        for name, passed in checks:
            mark = self.style.SUCCESS("OK") if passed else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{mark}] {name}")
            ok = ok and passed

        self.stdout.write(f"\n  kaspi_guide_url: {kaspi_guide_public_url()}")
        self.stdout.write(f"  asset_bytes: {asset.stat().st_size if asset.is_file() else 0}")

        sample = checks and ok
        if sample:
            self.stdout.write(self.style.SUCCESS("\nDeploy looks good. Rebuild app if any FAIL above.\n"))
        else:
            self.stdout.write(self.style.ERROR("\nFix FAIL items, then: docker compose build --no-cache app\n"))
