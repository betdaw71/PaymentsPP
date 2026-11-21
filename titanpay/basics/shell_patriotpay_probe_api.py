"""
Проба PatriotPay Merchant API (методы оплаты).

Нужны PATRIOTPAY_API_KEY (X-Identity) и PATRIOTPAY_SECRET_KEY из ЛК, не пароль docs.patriotpay.club.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_patriotpay_probe_api.py
"""
from payments.patriotpay_client import (
    patriotpay_get_payment_methods,
    _api_key,
    _secret_key,
    _api_base,
)


def run():
    print("=== PatriotPay API probe ===")
    print(f"base={_api_base()}")
    print(f"api_key_set={bool(_api_key())} secret_set={bool(_secret_key())}")
    if not _api_key() or not _secret_key():
        print("Set PATRIOTPAY_API_KEY and PATRIOTPAY_SECRET_KEY in server .env")
        return
    for currency in ("KZT", "RUB"):
        ok, data = patriotpay_get_payment_methods(currency=currency)
        print(f"\n--- payment-methods currency={currency} ok={ok} ---")
        items = data.get("items") if isinstance(data, dict) else data
        print(items if items is not None else data)


run()
