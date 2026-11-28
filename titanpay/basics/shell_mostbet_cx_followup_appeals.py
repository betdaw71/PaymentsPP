"""
Mostbet: статусы апелляций, которые мерчант «уточняет» / ждёт ответа.

Режимы:
  1) По UUID из уточнений (если передали UUIDS=… или после Telethon-скана)
  2) Все открытые Mostbet-апелляции + проблемные за окно (DB overview)

Предпочтительный скан чата CX (any news? / UUID / id / id):

  docker compose --profile userbot run --rm --no-deps \\
    -e HOURS=168 appeal-userbot python scan_mostbet_followups.py

DB overview (из ~/project):

  docker compose exec -T -e HOURS=168 -e MERCHANT=mostbet app \\
    python manage.py shell < titanpay/basics/shell_mostbet_cx_followup_appeals.py

  UUIDS=9020b2c9-…,697c0586-… HOURS=720 \\
    docker compose exec -T -e UUIDS -e HOURS -e MERCHANT=mostbet app \\
    python manage.py shell < titanpay/basics/shell_mostbet_cx_followup_appeals.py
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from appeals.id_resolve import (
    extract_cx_slash_order_ids,
    extract_uuids,
    is_followup_chatter,
    resolve_pay_in_from_message,
)
from appeals.models import (
    AppealCounterparty,
    AppealCounterpartyRole,
    AppealTelegramChat,
    PayInAppeal,
    PayInAppealStatus,
)

MERCHANT = (os.environ.get("MERCHANT") or "mostbet").strip()
HOURS = int(os.environ.get("HOURS") or "168")
UUIDS_RAW = (os.environ.get("UUIDS") or "").strip()
LIMIT = int(os.environ.get("LIMIT") or "80")

OPEN_STATUSES = (
    PayInAppealStatus.CREATED,
    PayInAppealStatus.SENT_TO_PROVIDER,
    PayInAppealStatus.AWAITING_REJECT_REASON,
)
PROBLEM_STATUSES = (
    PayInAppealStatus.FAILED,
    PayInAppealStatus.NO_PROVIDER_CHAT,
    PayInAppealStatus.DUPLICATE,
)


def _short(value, n: int = 72) -> str:
    text = (str(value) if value is not None else "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def _parse_uuids(raw: str) -> list[str]:
    if not raw:
        return []
    tokens: list[str] = []
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        tokens.extend(extract_cx_slash_order_ids(part) or extract_uuids(part) or [part])
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _appeal_row(appeal: PayInAppeal) -> str:
    pay_in = appeal.pay_in
    order = appeal.in_order or getattr(pay_in, "order", None)
    merchant = getattr(getattr(pay_in, "merchant", None), "user", None)
    age_h = (timezone.now() - appeal.created_at).total_seconds() / 3600.0
    return (
        f"  {appeal.created_at} [{appeal.status}] age={age_h:.1f}h "
        f"psp={appeal.psp_provider or '—'} "
        f"merchant={getattr(merchant, 'username', None)} "
        f"moid={getattr(pay_in, 'merchant_order_id', None)} "
        f"pay_in={pay_in.id if pay_in else '—'} "
        f"order_st={getattr(getattr(order, 'status', None), 'name', None)} "
        f"src_chat={appeal.source_telegram_chat_id} "
        f"err={_short(appeal.error_message, 48)}"
    )


def lookup_uuids(uuids: list[str]) -> None:
    _print_section(f"Lookup UUID из уточнений ({len(uuids)})")
    if not uuids:
        print("(пусто — задайте UUIDS=… или сначала scan_mostbet_followups.py)")
        return

    by_status: Counter[str] = Counter()
    interesting = 0
    for token in uuids:
        print(f"\n--- {token} ---")
        resolved = resolve_pay_in_from_message(token)
        if not resolved.ok or resolved.pay_in is None:
            print(f"  NOT_FOUND  {resolved.error_message or ''}")
            by_status["NOT_FOUND"] += 1
            interesting += 1
            continue
        pay_in = resolved.pay_in
        order = pay_in.order
        merchant = getattr(getattr(pay_in, "merchant", None), "user", None)
        print(
            f"  pay_in={pay_in.id} st={getattr(pay_in.status, 'name', None)} "
            f"amount={pay_in.amount} merchant={getattr(merchant, 'username', None)} "
            f"moid={pay_in.merchant_order_id}"
        )
        if order is not None:
            print(
                f"  in_order={order.id} order_st={getattr(order.status, 'name', None)} "
                f"updated={order.updated_date}"
            )
        appeals = list(
            PayInAppeal.objects.filter(pay_in=pay_in)
            .order_by("-created_at")
            .select_related("in_order__status")
        )
        if not appeals:
            print("  appeals: NO_APPEAL (в чате спрашивают, у нас тикет не зарегистрирован)")
            by_status["NO_APPEAL"] += 1
            interesting += 1
            continue
        for appeal in appeals:
            print(_appeal_row(appeal))
            by_status[appeal.status] += 1
            if appeal.status in OPEN_STATUSES or appeal.status in PROBLEM_STATUSES:
                interesting += 1

    print("\nсводка:")
    for status, n in by_status.most_common():
        print(f"  {status}: {n}")
    print(f"интересующих (open/problem/missing): {interesting}")


def mostbet_chats() -> list[AppealTelegramChat]:
    cps = AppealCounterparty.objects.filter(
        role=AppealCounterpartyRole.MERCHANT,
        is_active=True,
    ).filter(
        Q(merchant__user__username__iexact=MERCHANT) | Q(name__icontains=MERCHANT)
    )
    return list(
        AppealTelegramChat.objects.filter(counterparty__in=cps, is_active=True).select_related(
            "counterparty"
        )
    )


def run(hours: int | None = None, uuids: list[str] | None = None, limit: int | None = None) -> None:
    hours = HOURS if hours is None else hours
    limit = LIMIT if limit is None else limit
    since = timezone.now() - timedelta(hours=hours)
    id_list = list(uuids) if uuids is not None else _parse_uuids(UUIDS_RAW)

    _print_section(f"Mostbet CX / merchant={MERCHANT}  window={hours}h  since={since.isoformat()}")

    chats = mostbet_chats()
    print("зарегистрированные чаты Mostbet:")
    if not chats:
        print("  (нет — сделайте /init <uuid Mostbet counterparty> в CX)")
    for chat in chats:
        print(
            f"  chat_id={chat.telegram_chat_id} title={chat.title!r} "
            f"cp={chat.counterparty.name} ({chat.counterparty.id})"
        )

    if id_list:
        lookup_uuids(id_list)

    chat_ids = [c.telegram_chat_id for c in chats]
    qs = PayInAppeal.objects.filter(
        Q(pay_in__merchant__user__username__iexact=MERCHANT)
        | Q(source_telegram_chat_id__in=chat_ids)
    ).filter(created_at__gte=since).select_related(
        "pay_in__merchant__user",
        "pay_in__status",
        "in_order__status",
    )

    _print_section(f"Апелляции Mostbet за {hours}ч: {qs.count()}")
    by_status = Counter(qs.values_list("status", flat=True))
    for status, n in by_status.most_common():
        print(f"  {status}: {n}")

    open_qs = qs.filter(status__in=OPEN_STATUSES).order_by("created_at")
    _print_section(f"Открытые (мерчант ждёт ответа): {open_qs.count()}")
    for appeal in open_qs[:limit]:
        print(_appeal_row(appeal))
    if open_qs.count() > limit:
        print(f"  … ещё {open_qs.count() - limit}")

    problem_qs = qs.filter(status__in=PROBLEM_STATUSES).order_by("status", "created_at")
    _print_section(f"Проблемные (failed / no_provider_chat / duplicate): {problem_qs.count()}")
    for appeal in problem_qs[:limit]:
        print(_appeal_row(appeal))
    if problem_qs.count() > limit:
        print(f"  … ещё {problem_qs.count() - limit}")

    # provider_original_text иногда хранит CX-строку — отметить follow-up-подобные
    follow_hints = 0
    _print_section("В provider_original_text похоже на CX slash / follow-up (сэмпл)")
    for appeal in qs.order_by("-created_at")[:200]:
        text = appeal.provider_original_text or ""
        if not text:
            continue
        if extract_cx_slash_order_ids(text) or is_followup_chatter(text):
            follow_hints += 1
            if follow_hints <= 15:
                print(
                    f"  [{appeal.status}] moid={appeal.pay_in.merchant_order_id} "
                    f"text={_short(text, 90)}"
                )
    print(f"всего с CX/follow-up следом в тексте: {follow_hints} (из последних 200)")

    print()
    print("Чтобы разобрать именно «any news?» из Telegram-истории:")
    print(
        "  docker compose --profile userbot run --rm --no-deps "
        "-e HOURS=%s appeal-userbot python scan_mostbet_followups.py" % hours
    )
    print("\nГотово.")


run()
