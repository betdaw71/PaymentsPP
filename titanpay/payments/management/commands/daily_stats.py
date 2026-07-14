"""Статистика за день: python manage.py daily_stats 2026-02-22"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from basics.shell_daily_stats import run


class Command(BaseCommand):
    help = "Оборот и комиссии за день (Completed InOrder/OutOrder)"

    def add_arguments(self, parser):
        parser.add_argument(
            "date",
            nargs="?",
            type=str,
            help="Дата YYYY-MM-DD (по умолчанию — сегодня)",
        )
        parser.add_argument("--merchant", type=str, default="", help="Фильтр по username мерчанта")
        parser.add_argument("--yesterday", action="store_true", help="Вчера")

    def handle(self, *args, **options):
        target = None
        if options.get("date"):
            try:
                target = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Дата в формате YYYY-MM-DD, напр. 2026-02-22") from exc
        merchant = (options.get("merchant") or "").strip() or None
        run(target, yesterday=options["yesterday"], merchant=merchant)
