"""Анализ PSP-реквизитов: python manage.py analyze_psp_requisites --days 7"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from basics.shell_analyze_psp_requisites import run


class Command(BaseCommand):
    help = "Конверсия по реквизитам PSP: провайдер vs ответ мерчанту"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=float, default=7)
        parser.add_argument("--hours", type=float, default=None)
        parser.add_argument("--since", type=str, default="")
        parser.add_argument("--until", type=str, default="")
        parser.add_argument("--merchant", type=str, default="")
        parser.add_argument("--ps", type=str, default="")
        parser.add_argument(
            "--provider",
            type=str,
            default="all",
            choices=("all", "protocol", "expayone", "fairpay"),
        )
        parser.add_argument("--top", type=int, default=25)
        parser.add_argument("--min-issued", type=int, default=2)
        parser.add_argument("--shadow-min-issued", type=int, default=5)
        parser.add_argument("--shadow-max-conv", type=float, default=5.0)
        parser.add_argument("--limit", type=int, default=50000)
        parser.add_argument("--json", type=str, default="")
        parser.add_argument("--day", type=str, default="", help="YYYY-MM-DD")
        parser.add_argument("--week", action="store_true")
        parser.add_argument("--month", action="store_true")
        parser.add_argument("--no-extra-periods", action="store_true")

    def handle(self, *args, **options):
        merchant = (options.get("merchant") or "").strip() or None
        ps = (options.get("ps") or "").strip() or None
        json_path = (options.get("json") or "").strip()

        target = None
        if options.get("day"):
            try:
                target = datetime.strptime(options["day"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Дата в формате YYYY-MM-DD") from exc

        run(
            target,
            week=bool(options.get("week")),
            month=bool(options.get("month")),
            days=float(options.get("days") or 7),
            hours=options.get("hours"),
            since=(options.get("since") or "").strip(),
            until=(options.get("until") or "").strip(),
            merchant=merchant,
            ps=ps,
            provider=options.get("provider") or "all",
            top=int(options.get("top") or 25),
            min_issued=int(options.get("min_issued") or 2),
            shadow_min_issued=int(options.get("shadow_min_issued") or 5),
            shadow_max_conv=float(options.get("shadow_max_conv") or 5.0),
            limit=int(options.get("limit") or 50000),
            json_path=json_path,
            extra_periods=not options.get("no_extra_periods") and not options.get("day"),
        )
