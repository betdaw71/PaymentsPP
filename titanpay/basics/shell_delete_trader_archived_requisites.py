"""
Удалить архивированные реквизиты (PaymentDetails.status=2) трейдера.

По умолчанию DRY-RUN. Реальное удаление: APPLY=1.

  # посмотреть что удалится
  docker compose exec -T -e TRADER=resdfe app python manage.py shell \\
    < titanpay/basics/shell_delete_trader_archived_requisites.py

  # удалить
  docker compose exec -T -e TRADER=resdfe -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_delete_trader_archived_requisites.py

Опционально:
  DELETE_ARCHIVED_GROUPS=1  — также удалить группы трейдера со status=2
                              (CASCADE сотрёт и их detail)
"""
from __future__ import annotations

import os

from basics.models import PaymentDetails, PaymentDetailsGroup, Trader

TRADER = (os.environ.get("TRADER") or "resdfe").strip()
APPLY = (os.environ.get("APPLY") or "").strip() in {"1", "true", "yes", "YES"}
DELETE_ARCHIVED_GROUPS = (os.environ.get("DELETE_ARCHIVED_GROUPS") or "").strip() in {
    "1",
    "true",
    "yes",
    "YES",
}

trader = Trader.objects.select_related("user").filter(user__username=TRADER).first()
if trader is None:
    print(f"FAIL: trader username={TRADER!r} not found")
    raise SystemExit(1)

groups = PaymentDetailsGroup.objects.filter(trader=trader)
group_ids = list(groups.values_list("id", flat=True))
archived_details = PaymentDetails.objects.filter(group_id__in=group_ids, status=2)
archived_groups = groups.filter(status=2)

n_details = archived_details.count()
n_groups = archived_groups.count()
sample = list(
    archived_details.order_by("-creation_date").values_list(
        "id", "card_number", "phone", "deposit_number", "creation_date"
    )[:20]
)

print(f"trader={TRADER} id={trader.id}")
print(f"groups total={groups.count()}  archived_groups(status=2)={n_groups}")
print(f"archived PaymentDetails(status=2)={n_details}")
print(f"APPLY={APPLY}  DELETE_ARCHIVED_GROUPS={DELETE_ARCHIVED_GROUPS}")
print("sample (up to 20):")
for row in sample:
    print(f"  id={row[0]} card={row[1]} phone={row[2]} deposit={row[3]} created={row[4]}")

if not APPLY:
    print("DRY-RUN — ничего не удалено. Перезапусти с APPLY=1")
else:
    deleted_details, _ = archived_details.delete()
    print(f"deleted PaymentDetails rows (incl. cascades if any): {deleted_details}")
    if DELETE_ARCHIVED_GROUPS:
        deleted_groups, _ = archived_groups.delete()
        print(f"deleted archived PaymentDetailsGroup rows: {deleted_groups}")
    left = PaymentDetails.objects.filter(group__trader=trader, status=2).count()
    print(f"remaining archived details for trader: {left}")

print("DONE")
