"""Management command: export PayIn / PayOut CSV for merchant (1C format)."""

from django.core.management.base import BaseCommand, CommandError

from merchant.models import Merchant
from payments.merchant_deals_export import export_merchant_deals_csv, list_merchants_with_deals


class Command(BaseCommand):
    help = "Export PayIn and PayOut CSV reports for a merchant (1C sync format)"

    def add_arguments(self, parser):
        parser.add_argument("--merchant", help="Merchant username (User.username)")
        parser.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD (UTC)")
        parser.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD (UTC, inclusive)")
        parser.add_argument("--days", type=int, help="Last N days (instead of --from/--to)")
        parser.add_argument("--out", dest="out_dir", default="/tmp", help="Output directory")
        parser.add_argument("--limit", type=int, default=5000, help="Max rows per file")
        parser.add_argument(
            "--list",
            action="store_true",
            help="List merchants with recent PayIn/PayOut (use with --days)",
        )

    def handle(self, *args, **options):
        if options["list"]:
            days = options["days"] or 90
            rows = list_merchants_with_deals(days=days, limit=20)
            if not rows:
                self.stdout.write("No deals found.")
                return
            self.stdout.write(f"Merchants with deals (last {days} days):\n")
            for r in rows:
                self.stdout.write(f"  {r['type']:6}  {r['username']:30}  {r['count']}")
            return

        merchant = options["merchant"]
        if not merchant:
            raise CommandError("Specify --merchant USERNAME or use --list")

        days = options["days"]
        date_from = options["date_from"]
        date_to = options["date_to"]

        if days is None and not date_from:
            raise CommandError("Specify --days N or --from YYYY-MM-DD [--to YYYY-MM-DD]")

        try:
            payin_path, payout_path, pin_n, pout_n = export_merchant_deals_csv(
                merchant,
                date_from,
                date_to,
                days=days,
                out_dir=options["out_dir"],
                limit=options["limit"],
                verbose=False,
            )
        except Merchant.DoesNotExist:
            raise CommandError(f"Merchant not found: {merchant}") from None
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"PayIn:  {payin_path} ({pin_n} rows)"))
        self.stdout.write(self.style.SUCCESS(f"PayOut: {payout_path} ({pout_n} rows)"))
