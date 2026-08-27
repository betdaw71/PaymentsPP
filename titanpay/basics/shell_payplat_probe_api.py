"""
Проба PayPlat Merchant API (создание тестовой сделки).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_payplat_probe_api.py
"""
import time
import uuid

from payments.payplat_client import (
    _api_base,
    _secret_key,
    _shop_id,
    payplat_create_deal,
)


def run():
    print("=== PayPlat API probe ===")
    print(f"base={_api_base()}")
    print(f"shop_id={_shop_id()} secret_set={bool(_secret_key())}")
    if not _shop_id() or not _secret_key():
        print("Set PAYPLAT_SHOP_ID and PAYPLAT_SECRET_KEY in .env")
        return
    external_id = f"probe-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    ok, data = payplat_create_deal(
        amount=5000,
        shop_internal_id=external_id,
        requisite_type="c2c_ab",
        id_contragent=f"probe-{uuid.uuid4().hex[:12]}",
        payer="kz",
        pay_in=None,
    )
    print(f"\n--- create deal ok={ok} shop_internal_id={external_id} ---")
    print(data)


run()
