"""
Shell-обёртка: merchant_order_id → provider_id.

  docker compose exec app python manage.py shell
  >>> exec(open("basics/shell_merchant_to_provider.py").read())
  >>> resolve_ids(["23501162683", "23500174835"])
  >>> print_map()  # встроенный список

Или:
  python manage.py merchant_to_provider --builtin
  python manage.py merchant_to_provider --file /tmp/ids.txt --csv
"""
from payments.management.commands.merchant_to_provider import (
    BUILTIN_MERCHANT_ORDER_IDS,
    resolve_ids,
)


def print_map(ids=None, *, provider_only: bool = False):
    rows = resolve_ids(ids or BUILTIN_MERCHANT_ORDER_IDS)
    if provider_only:
        for r in rows:
            print(r["provider_id"] or "")
        return rows
    print("merchant_order_id\tprovider\tprovider_id\ttype\tstatus")
    for r in rows:
        print(
            f"{r['merchant_order_id']}\t{r['provider']}\t{r['provider_id']}\t"
            f"{r['type']}\t{r['status']}"
        )
    found = sum(1 for r in rows if r["found"])
    with_p = sum(1 for r in rows if r["provider_id"])
    print(f"\nfound={found} with_provider_id={with_p} missing={len(rows) - found}")
    return rows


print("shell_merchant_to_provider loaded:")
print("  print_map()                  # builtin list")
print("  print_map(['23501162683'])")
print("  resolve_ids(['23501162683'])")
