"""
Shell-обёртка для экспорта PayIn / PayOut CSV (1C).

  docker compose exec app python manage.py shell
  >>> exec(open("basics/shell_export_merchant_deals_1c.py").read())
  >>> export_deals_1c("merchant_username", "2026-04-13", "2026-04-20")
  >>> export_deals_1c("merchant_username", days=30)
  >>> list_merchants_with_deals(days=90)

Или через manage.py (рекомендуется):
  python manage.py export_deals_1c --merchant USERNAME --days 30 --out /tmp
"""
from payments.merchant_deals_export import (
    export_merchant_deals_csv as export_deals_1c,
    list_merchants_with_deals,
)

print("shell_export_merchant_deals_1c loaded:")
print("  list_merchants_with_deals(days=90)")
print("  export_deals_1c(username, '2026-01-01', '2026-04-20')")
print("  export_deals_1c(username, days=30, out_dir='/tmp')")
