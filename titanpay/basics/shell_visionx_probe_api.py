"""
Проба VisionX Merchant API (методы оплаты, баланс).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_visionx_probe_api.py
"""
from payments.visionx_client import visionx_get_payment_methods, _api_key, _secret_key, _api_base


def run():
    print("=== VisionX API probe ===")
    print(f"base={_api_base()}")
    print(f"api_key_set={bool(_api_key())} secret_set={bool(_secret_key())}")
    if not _api_key() or not _secret_key():
        print("Set VISIONX_API_KEY and VISIONX_SECRET_KEY in .env")
        return
    for currency in ("KZT", "RUB"):
        ok, data = visionx_get_payment_methods(currency=currency)
        print(f"\n--- payment-methods currency={currency} ok={ok} ---")
        print(data)


run()
