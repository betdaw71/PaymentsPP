"""
Django shell: сводка по апелляциям за последние N часов.

Показывает:
  - статусы PayInAppeal (created / sent_to_provider / failed / no_provider_chat / …)
  - разбивку по провайдерам (psp_provider) и мерчантам
  - необработанные и проблемные апелляции
  - lookup конкретных Melbet order_id / PayIn UUID / тикетов
  - InOrder в Arbitrage без закрытия

Запуск на проде (из ~/project):

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_analyze_appeals_24h.py

Или интерактивно:

  docker compose exec -T app python manage.py shell
  >>> exec(open("basics/shell_analyze_appeals_24h.py").read())
  >>> run()
  >>> run(hours=48)
  >>> lookup("24805994773", "9869c736-e2e4-474d-a6fe-0e1293c59738")

Параллельно логи userbot / appealbot (👎 = backend rejected):

  docker compose logs --since=24h appeal-userbot 2>&1 | grep -E 'outcome=|👎|LISTEN|rejected|ID не распознан|ERROR|Traceback' | tail -200
  docker compose logs --since=24h appealbot 2>&1 | grep -E 'outcome=|rejected|ERROR|Traceback' | tail -100
  docker compose ps | grep -E 'appeal|userbot'
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from appeals.id_resolve import resolve_pay_in_from_message
from appeals.models import PayInAppeal, PayInAppealStatus
from payments.integrations.melbet.models import MelbetTransactionSession
from payments.models import PayIn
from trade.models import InOrder

# Тикеты из Melbet Support (скриншоты 21.11) — можно переопределить в run(lookup_ids=...).
DEFAULT_LOOKUP_IDS = [
    "24790313993",
    "24790116125",
    "24791390383",
    "24800428707",
    "24805994773",
    "52c9127d-0526-4b81-9f86-198e54d28b30",
    "54c5b4ab-14e6-412d-a351-7f4b7ea5aa6b",
    "91ac1b28-d37a-4eef-aff0-5d6e374a141b",
    "9540c2e6-8268-4e63-9614-61c54460e08a",
    "9869c736-e2e4-474d-a6fe-0e1293c59738",
]

OPEN_STATUSES = (
    PayInAppealStatus.CREATED,
    PayInAppealStatus.SENT_TO_PROVIDER,
)
PROBLEM_STATUSES = (
    PayInAppealStatus.FAILED,
    PayInAppealStatus.NO_PROVIDER_CHAT,
    PayInAppealStatus.DUPLICATE,
)


def _since(hours: int):
    return timezone.now() - timedelta(hours=hours)


def _short(value, n: int = 80) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def lookup(*ids: str) -> None:
    """Разобрать конкретные Melbet order_id / PayIn UUID / короткий тикет."""
    _print_section("LOOKUP конкретных ID")
    if not ids:
        print("(пусто)")
        return

    for raw in ids:
        token = (raw or "").strip()
        if not token:
            continue
        print(f"\n--- {token} ---")
        resolved = resolve_pay_in_from_message(token)
        pay_in = resolved.pay_in if resolved.ok else None

        if pay_in is None:
            # Прямой fallback на Melbet session / merchant_order_id
            session = MelbetTransactionSession.objects.filter(order_id=token).select_related(
                "pay_in__status", "pay_in__merchant__user", "pay_in__order__status"
            ).first()
            if session and session.pay_in_id:
                pay_in = session.pay_in
                print(f"  via MelbetTransactionSession.order_id  session={session.id}")
            else:
                pay_in = PayIn.objects.filter(merchant_order_id=token).select_related(
                    "status", "merchant__user", "order__status"
                ).first()
                if pay_in:
                    print("  via PayIn.merchant_order_id")

        if pay_in is None:
            if resolved.error_message:
                print(
                    f"  resolve: FAIL recognized={resolved.recognized} "
                    f"err={resolved.error_message}"
                )
            else:
                print("  resolve: NOT FOUND")
            continue

        # resolved.pay_in может прийти без select_related — подгружаем связи
        pay_in = (
            PayIn.objects.filter(pk=pay_in.pk)
            .select_related("status", "currency", "merchant__user", "order__status")
            .first()
        )
        if pay_in is None:
            print("  resolve: NOT FOUND (исчез после resolve)")
            continue

        order = pay_in.order
        merchant = getattr(getattr(pay_in, "merchant", None), "user", None)
        print(
            f"  pay_in={pay_in.id} status={getattr(pay_in.status, 'name', None)} "
            f"amount={pay_in.amount} {getattr(pay_in.currency, 'symbol', '')} "
            f"merchant={getattr(merchant, 'username', None)} "
            f"moid={pay_in.merchant_order_id}"
        )
        if order is not None:
            print(
                f"  in_order={order.id} status={getattr(order.status, 'name', None)} "
                f"updated={order.updated_date}"
            )

        appeals = list(
            PayInAppeal.objects.filter(pay_in=pay_in)
            .order_by("-created_at")
            .values(
                "id",
                "status",
                "psp_provider",
                "provider_external_id",
                "error_message",
                "source",
                "created_at",
                "merchant_inline_clicked",
            )
        )
        if not appeals:
            print("  appeals: NONE (бот тикет не принял / не дошёл process_message)")
            continue
        for row in appeals:
            print(
                f"  appeal={row['id']} status={row['status']} psp={row['psp_provider'] or '—'} "
                f"src={row['source']} clicked={row['merchant_inline_clicked']} "
                f"at={row['created_at']} err={_short(row['error_message'])}"
            )


def run(hours: int = 24, lookup_ids: list[str] | None = None, limit: int = 40) -> None:
    since = _since(hours)
    qs = PayInAppeal.objects.filter(created_at__gte=since).select_related(
        "pay_in__merchant__user",
        "pay_in__status",
        "in_order__status",
        "source_counterparty",
    )

    _print_section(f"Апелляции за последние {hours}ч (с {since.isoformat()})")
    total = qs.count()
    print(f"всего: {total}")

    by_status = list(qs.values("status").annotate(n=Count("id")).order_by("-n"))
    print("\nпо статусам:")
    for row in by_status:
        print(f"  {row['status'] or '—'}: {row['n']}")

    by_provider = list(
        qs.values("psp_provider", "status").annotate(n=Count("id")).order_by("psp_provider", "status")
    )
    print("\nпо провайдерам × статус:")
    if not by_provider:
        print("  (пусто)")
    for row in by_provider:
        print(f"  {row['psp_provider'] or '—'} / {row['status']}: {row['n']}")

    by_merchant = list(
        qs.values("pay_in__merchant__user__username", "status")
        .annotate(n=Count("id"))
        .order_by("pay_in__merchant__user__username", "status")
    )
    print("\nпо мерчантам × статус:")
    for row in by_merchant:
        print(f"  {row['pay_in__merchant__user__username'] or '—'} / {row['status']}: {row['n']}")

    open_qs = qs.filter(status__in=OPEN_STATUSES).order_by("created_at")
    _print_section(f"Необработанные (created / sent_to_provider): {open_qs.count()}")
    for appeal in open_qs[:limit]:
        merchant = getattr(getattr(appeal.pay_in, "merchant", None), "user", None)
        order_status = getattr(getattr(appeal.in_order, "status", None), "name", None)
        print(
            f"  {appeal.created_at} [{appeal.status}] psp={appeal.psp_provider or '—'} "
            f"merchant={getattr(merchant, 'username', None)} "
            f"pay_in={appeal.pay_in_id} moid={appeal.pay_in.merchant_order_id} "
            f"in_order={appeal.in_order_id} order_st={order_status} "
            f"ext={_short(appeal.provider_external_id, 36)} "
            f"err={_short(appeal.error_message)}"
        )
    if open_qs.count() > limit:
        print(f"  … ещё {open_qs.count() - limit}")

    problem_qs = qs.filter(status__in=PROBLEM_STATUSES).order_by("status", "created_at")
    _print_section(f"Проблемные (failed / no_provider_chat / duplicate): {problem_qs.count()}")
    err_counter: Counter[str] = Counter()
    for appeal in problem_qs:
        key = appeal.error_message.strip() or appeal.status
        err_counter[key] += 1
    print("топ ошибок:")
    for msg, n in err_counter.most_common(15):
        print(f"  {n:4d}  {_short(msg, 100)}")
    print("\nдетали:")
    for appeal in problem_qs[:limit]:
        merchant = getattr(getattr(appeal.pay_in, "merchant", None), "user", None)
        print(
            f"  {appeal.created_at} [{appeal.status}] psp={appeal.psp_provider or '—'} "
            f"merchant={getattr(merchant, 'username', None)} "
            f"pay_in={appeal.pay_in_id} moid={appeal.pay_in.merchant_order_id} "
            f"err={_short(appeal.error_message)}"
        )
    if problem_qs.count() > limit:
        print(f"  … ещё {problem_qs.count() - limit}")

    # Melbet в арбитраже / money sent — без апелляции (реальные «тикет не дошёл»)
    melbet_arb = (
        PayIn.objects.filter(melbet_session__isnull=False)
        .filter(order__status__name__in=["Arbitrage", "Money sent by user"])
        .filter(order__updated_date__gte=since)
        .select_related("status", "merchant__user", "order__status")
        .order_by("-order__updated_date")
    )
    melbet_arb_ids = list(melbet_arb.values_list("id", flat=True)[:500])
    appealed_ids = set(
        PayInAppeal.objects.filter(pay_in_id__in=melbet_arb_ids).values_list("pay_in_id", flat=True)
    )
    missing_arb = [p for p in melbet_arb[:500] if p.id not in appealed_ids]
    _print_section(
        f"Melbet Arbitrage/MoneySent без PayInAppeal (order updated за {hours}ч): "
        f"{len(missing_arb)} из {len(melbet_arb_ids)}"
    )
    for pay_in in missing_arb[:limit]:
        print(
            f"  pay_in={pay_in.id} moid={pay_in.merchant_order_id} "
            f"st={getattr(pay_in.status, 'name', None)} "
            f"order_st={getattr(getattr(pay_in.order, 'status', None), 'name', None)} "
            f"amount={pay_in.amount}"
        )
    if len(missing_arb) > limit:
        print(f"  … ещё {len(missing_arb) - limit}")

    arb = InOrder.objects.filter(
        status__name="Arbitrage",
        updated_date__gte=since,
    ).select_related("status", "solution__merchant__user")
    _print_section(f"InOrder Arbitrage (updated за {hours}ч): {arb.count()}")
    by_m: dict[str, int] = defaultdict(int)
    for order in arb[:200]:
        m = getattr(getattr(getattr(order, "solution", None), "merchant", None), "user", None)
        by_m[getattr(m, "username", None) or "—"] += 1
    for name, n in sorted(by_m.items(), key=lambda x: -x[1]):
        print(f"  {name}: {n}")

    ids = list(lookup_ids) if lookup_ids is not None else list(DEFAULT_LOOKUP_IDS)
    lookup(*ids)
    print("\nГотово.")


run()
