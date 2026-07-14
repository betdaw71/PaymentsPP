"""Показать / поправить лимиты MerchantSolution (pay-in)."""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from basics.models import PaymentSystem
from merchant.models import Merchant, MerchantSolution


class Command(BaseCommand):
    help = "Лимиты pay-in мерчанта по payment_system (диагностика Amount out of limits!)"

    def add_arguments(self, parser):
        parser.add_argument("merchant_username", type=str)
        parser.add_argument("--ps", type=str, default="", help="Фильтр по имени PS, напр. C2CKZT")
        parser.add_argument("--fix-c2ckzt", action="store_true", help="Выставить C2CKZT: min=1000 max=10000 ftd=false")
        parser.add_argument("--min", type=str, default="1000")
        parser.add_argument("--max", type=str, default="10000")

    def handle(self, *args, **options):
        try:
            merchant = Merchant.objects.get(user__username=options["merchant_username"])
        except Merchant.DoesNotExist:
            raise CommandError(f"Merchant {options['merchant_username']!r} not found")

        qs = MerchantSolution.objects.filter(merchant=merchant, status=1).select_related(
            "payment_system", "payment_system__currency", "traffic"
        )
        ps_filter = (options.get("ps") or "").strip()
        if ps_filter:
            qs = qs.filter(payment_system__name__iexact=ps_filter)

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No active MerchantSolution rows"))
            return

        for sol in qs.order_by("payment_system__name", "ftd"):
            ps = sol.payment_system
            self.stdout.write(
                f"{ps.name} ({ps.currency.symbol}) ftd={sol.ftd} "
                f"pay-in [{sol.min_limit_in} .. {sol.max_limit_in}] "
                f"pay-out [{sol.min_limit_out} .. {sol.max_limit_out}] "
                f"traffic={sol.traffic.name} id={sol.id}"
            )

        if options["fix_c2ckzt"]:
            ps_name = ps_filter or "C2CKZT"
            ps = PaymentSystem.objects.filter(name__iexact=ps_name).first()
            if ps is None:
                raise CommandError(f"PaymentSystem {ps_name!r} not found")
            mn = Decimal(options["min"])
            mx = Decimal(options["max"])
            updated = MerchantSolution.objects.filter(
                merchant=merchant, payment_system=ps, ftd=False, status=1
            ).update(min_limit_in=mn, max_limit_in=mx)
            if not updated:
                self.stdout.write(
                    self.style.WARNING(
                        f"No active MerchantSolution for {ps.name} ftd=False — create one in admin/shell"
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated {updated} solution(s): min={mn} max={mx}"))
