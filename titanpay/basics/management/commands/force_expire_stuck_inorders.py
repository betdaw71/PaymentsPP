"""
Принудительно протушить InOrder в статусе New, у которых уже прошёл expired_time_in,
и разморозить USDT трейдера (deal_time_expired).

Нужно, когда UI уже показывает таймер 0, а cron expire() не успел / упал на callback.

Запуск (dry-run по умолчанию):
  docker compose exec app python manage.py force_expire_stuck_inorders botonpay1
  docker compose exec app python manage.py force_expire_stuck_inorders botonpay1 --apply
  docker compose exec app python manage.py force_expire_stuck_inorders --all --apply
"""
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from basics.models import Trader
from trade.models import InOrder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Expire past-due New InOrders and unfreeze trader balance"

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            nargs="?",
            default=None,
            help="username трейдера; без --all обязателен",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Все трейдеры (осторожно)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Реально вызвать deal_time_expired (иначе только список)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        username = options["username"]
        all_traders = options["all"]

        if not all_traders and not username:
            raise CommandError("Укажите username или --all")

        qs = InOrder.objects.filter(status__name="New").select_related(
            "solution__payment_system",
            "payment_details__group__trader__user",
            "status",
        )
        if username:
            try:
                trader = Trader.objects.get(user__username=username)
            except Trader.DoesNotExist as exc:
                raise CommandError(f"Trader {username!r} not found") from exc
            qs = qs.filter(payment_details__group__trader=trader)

        now = timezone.now()
        stuck = []
        for order in qs.iterator(chunk_size=200):
            ps = order.solution.payment_system
            if order.creation_date <= now - ps.expired_time_in:
                stuck.append(order)

        self.stdout.write(f"Past-due New InOrders: {len(stuck)}")
        ok = fail = 0
        for order in stuck:
            trader_name = (
                order.payment_details.group.trader.user.username
                if order.payment_details_id
                else "?"
            )
            line = (
                f"  {order.id}  trader={trader_name}  usd={order.usd_amount}  "
                f"created={order.creation_date}  ttl={order.solution.payment_system.expired_time_in}"
            )
            if not apply:
                self.stdout.write(line)
                continue
            try:
                with transaction.atomic():
                    locked = InOrder.objects.select_for_update().get(pk=order.id)
                    if locked.status.name != "New":
                        self.stdout.write(f"SKIP (status changed) {order.id}")
                        continue
                    locked.deal_time_expired()
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"EXPIRED {line}"))
            except Exception as e:
                fail += 1
                logger.exception("force expire %s", order.id)
                self.stdout.write(self.style.ERROR(f"FAIL {order.id}: {e}"))

        if not apply:
            self.stdout.write(self.style.WARNING("Dry-run. Добавьте --apply чтобы разморозить."))
        else:
            self.stdout.write(f"Done: ok={ok} fail={fail}")
