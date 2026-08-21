"""
Диагностика заморозки USDT у трейдера.

Заморозка trader.frozen_balance_usdt появляется из:
  1) InOrder.freeze  — pay-in в статусах New / Money sent by user / Arbitrage / Recalculation
  2) WithdrawalRequest.create (status=0) — «Freeze before the withdrawal»
  3) редкий/легаси путь PayOut: merchant → trader.frozen (linked_out_order)

Разморозка: InOrder.unfreeze / complete (Charge с frozen), reject/approve withdrawal.

Запуск:
  docker compose exec app python manage.py check_frozen_balance botonpay1
  docker compose exec app python manage.py check_frozen_balance botonpay1 --fix 50
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum
from django.utils import timezone

from basics.models import Trader
from trade.models import InOrder, OutOrder, Transaction, WithdrawalRequest


# Статусы InOrder, при которых средства должны оставаться на frozen
IN_HOLD_STATUSES = (
    "New",
    "Money sent by user",
    "Arbitrage",
    "Recalculation",
)

OUT_HOLD_STATUSES = (
    "New",
    "Money sent by trader",
    "Arbitrage",
    "Recalculation",
    "Manual check",
)


class Command(BaseCommand):
    help = "Показать, чем объясняется frozen_balance_usdt трейдера"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="username трейдера (например botonpay1)")
        parser.add_argument(
            "--fix",
            type=int,
            default=30,
            help="Сколько последних Freeze-транзакций на frozen показать",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            trader = Trader.objects.select_related(
                "user", "balance_usdt", "frozen_balance_usdt"
            ).get(user__username=username)
        except Trader.DoesNotExist as exc:
            raise CommandError(f"Trader с username={username!r} не найден") from exc

        available = trader.balance_usdt
        frozen = trader.frozen_balance_usdt
        frozen_amount = frozen.amount if frozen else Decimal("0")

        self.stdout.write("=" * 72)
        self.stdout.write(f"Trader: {username} (id={trader.id})")
        self.stdout.write(f"  available (balance_usdt): {available.amount}  [balance_id={available.id}]")
        self.stdout.write(f"  frozen    (frozen_usdt):  {frozen_amount}  [balance_id={frozen.id if frozen else None}]")
        self.stdout.write("=" * 72)

        # --- 1. Активные InOrder, которые должны держать freeze ---
        in_orders = (
            InOrder.objects.filter(
                payment_details__group__trader=trader,
                status__name__in=IN_HOLD_STATUSES,
            )
            .select_related("status", "payment_details")
            .order_by("-creation_date")
        )
        in_sum = in_orders.aggregate(s=Sum("usd_amount"))["s"] or Decimal("0")
        self.stdout.write(f"\n[1] Активные InOrder (hold): {in_orders.count()} шт, sum usd_amount={in_sum}")
        now = timezone.now()
        past_due_new = 0
        past_due_sum = Decimal("0")
        for o in in_orders.select_related("solution__payment_system"):
            ttl = o.solution.payment_system.expired_time_in
            overdue = o.status.name == "New" and o.creation_date <= now - ttl
            mark = " PAST_DUE_UI_TIMER" if overdue else ""
            if overdue:
                past_due_new += 1
                past_due_sum += o.usd_amount
            self.stdout.write(
                f"  - {o.id}  status={o.status.name}  amount={o.amount}  "
                f"usd={o.usd_amount}  created={o.creation_date}{mark}"
            )
        if past_due_new:
            self.stdout.write(
                self.style.WARNING(
                    f"  !! New с истёкшим expires_at (UI уже «истекла», cron ещё не разморозил): "
                    f"{past_due_new} шт, usd={past_due_sum}. "
                    f"Чинить: manage.py force_expire_stuck_inorders {username} --apply"
                )
            )

        # --- 2. Pending withdrawals ---
        withdrawals = WithdrawalRequest.objects.filter(from_user=trader.user, status=0).order_by("-date")
        wd_sum = withdrawals.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        self.stdout.write(f"\n[2] WithdrawalRequest status=0 (requested): {withdrawals.count()} шт, sum={wd_sum}")
        for w in withdrawals:
            self.stdout.write(
                f"  - {w.id}  amount={w.amount}  address={w.address_to}  date={w.date}  comment={w.comment!r}"
            )

        # --- 3. OutOrder, где на trader.frozen есть Freeze без закрытия ---
        out_freeze_qs = Transaction.objects.filter(
            to_balance=frozen,
            transaction_type__name="Freeze",
            linked_out_order__isnull=False,
        ).select_related("linked_out_order", "linked_out_order__status")
        active_out_holds = []
        out_hold_sum = Decimal("0")
        for tx in out_freeze_qs:
            oo = tx.linked_out_order
            if oo is None:
                continue
            # деньги ушли с frozen через Charge/Deposit/Withdrawal после freeze?
            released = Transaction.objects.filter(
                Q(from_balance=frozen) | Q(to_balance=available),
                linked_out_order=oo,
                creation_date__gte=tx.creation_date,
            ).exclude(id=tx.id).exists()
            if oo.status and oo.status.name in OUT_HOLD_STATUSES and not released:
                active_out_holds.append((oo, tx))
                out_hold_sum += tx.value
            elif not released and oo.status and oo.status.name not in ("Completed",):
                # терминальные без release — подозрительный хвост
                active_out_holds.append((oo, tx))
                out_hold_sum += tx.value

        self.stdout.write(
            f"\n[3] OutOrder Freeze → trader.frozen без release: {len(active_out_holds)} шт, sum={out_hold_sum}"
        )
        for oo, tx in active_out_holds:
            st = oo.status.name if oo.status else None
            self.stdout.write(
                f"  - out={oo.id}  status={st}  freeze_tx={tx.id}  value={tx.value}  "
                f"comment={tx.comment!r}  created={tx.creation_date}"
            )

        expected = in_sum + wd_sum + out_hold_sum
        delta = frozen_amount - expected
        self.stdout.write("\n" + "-" * 72)
        self.stdout.write(f"Ожидаемый hold (InOrder + WD + OutOrder): {expected}")
        self.stdout.write(f"Фактический frozen_balance_usdt:          {frozen_amount}")
        self.stdout.write(f"Разница (факт − ожидание):                {delta}")
        if delta == 0:
            self.stdout.write(self.style.SUCCESS("Сходится: frozen объясняется активными hold'ами."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Не сходится: возможны «хвосты» Freeze без unfreeze/Charge "
                    "(отменённые/просроченные заявки, ручные правки, сбой unfreeze)."
                )
            )

        # --- 4. InOrder с Freeze без симметричного Deposit/Charge на frozen ---
        orphan_sum = Decimal("0")
        orphan_rows = []
        freeze_in = (
            Transaction.objects.filter(
                to_balance=frozen,
                transaction_type__name="Freeze",
                linked_in_order__isnull=False,
            )
            .select_related("linked_in_order", "linked_in_order__status")
            .order_by("-creation_date")
        )
        for tx in freeze_in:
            od = tx.linked_in_order
            if od is None:
                continue
            # unfreeze = Deposit frozen→available; complete = Charge frozen→aggregator
            released = Transaction.objects.filter(
                linked_in_order=od,
                from_balance=frozen,
                creation_date__gte=tx.creation_date,
            ).exists()
            if not released:
                orphan_rows.append((od, tx))
                orphan_sum += tx.value

        self.stdout.write(
            f"\n[4] InOrder Freeze без последующего Deduct с frozen "
            f"(Deposit unfreeze / Charge complete): {len(orphan_rows)} шт, sum={orphan_sum}"
        )
        for od, tx in orphan_rows[: options["txs"]]:
            st = od.status.name if od.status else None
            self.stdout.write(
                f"  - in={od.id}  status={st}  freeze={tx.value}  comment={tx.comment!r}  "
                f"created={tx.creation_date}"
            )
        if len(orphan_rows) > options["txs"]:
            self.stdout.write(f"  ... ещё {len(orphan_rows) - options['txs']}")

        # --- 5. Последние движения по frozen ---
        recent = (
            Transaction.objects.filter(Q(from_balance=frozen) | Q(to_balance=frozen))
            .select_related("transaction_type", "linked_in_order", "linked_out_order")
            .order_by("-creation_date")[: options["txs"]]
        )
        self.stdout.write(f"\n[5] Последние {options['txs']} транзакций по frozen-балансу:")
        for tx in recent:
            direction = "IN " if tx.to_balance_id == frozen.id else "OUT"
            link = ""
            if tx.linked_in_order_id:
                link = f"in={tx.linked_in_order_id}"
            elif tx.linked_out_order_id:
                link = f"out={tx.linked_out_order_id}"
            else:
                link = "no-order"
            tname = tx.transaction_type.name if tx.transaction_type else "?"
            self.stdout.write(
                f"  {direction} {tx.creation_date}  {tname:10}  {tx.value:>12}  "
                f"{link}  {tx.comment!r}"
            )

        self.stdout.write("\nГотово.")
