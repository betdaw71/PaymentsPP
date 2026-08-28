"""
Поиск заявки BotonPay по deal_uuid / deal_id (сверка с кабинетом провайдера).

Запуск:
  docker compose exec app python manage.py shell -c "
from payments.models import BotonpayPayInSession
deal='32ea82be-014d-4aea-80d2-ffb3a593fca7'
s=BotonpayPayInSession.objects.filter(provider_deal_uuid=deal).first()
if not s:
    s=BotonpayPayInSession.objects.filter(last_webhook_payload__deal_uuid=deal).first()
print('pay_in', s.pay_in_id if s else None, 'platform', s.external_id if s else None)
"

Или по PayIn UUID:
  docker compose exec app python manage.py diagnose_payin <pay_in_uuid>
"""
from __future__ import annotations

import os

from payments.models import BotonpayPayInSession
from payments.psp_payin import _botonpay_deal_uuid_from_session

DEAL_ID = os.environ.get("DEAL_ID", "").strip()


def run(deal_id: str = DEAL_ID) -> None:
    if not deal_id:
        raise SystemExit("Set DEAL_ID=... or pass deal_id to run()")

    session = (
        BotonpayPayInSession.objects.filter(provider_deal_uuid=deal_id)
        .select_related("pay_in", "pay_in__merchant", "pay_in__order", "pay_in__status")
        .first()
    )
    if session is None:
        session = (
            BotonpayPayInSession.objects.filter(last_webhook_payload__deal_uuid=deal_id)
            .select_related("pay_in", "pay_in__merchant", "pay_in__order", "pay_in__status")
            .first()
        )
    if session is None:
        session = (
            BotonpayPayInSession.objects.filter(last_webhook_payload__deal_id=deal_id)
            .select_related("pay_in", "pay_in__merchant", "pay_in__order", "pay_in__status")
            .first()
        )

    if session is None:
        print(f"BotonPay deal {deal_id!r} not found")
        return

    pay_in = session.pay_in
    order = pay_in.order if pay_in else None
    print("=" * 60)
    print(f"BotonPay deal_id:     {deal_id}")
    print(f"provider_deal_uuid:   {_botonpay_deal_uuid_from_session(session)}")
    print(f"platform pay_in_id:   {session.external_id}")
    print(f"merchant_order_id:    {pay_in.merchant_order_id if pay_in else ''}")
    print(f"in_order_id:          {order.id if order else ''}")
    print(f"merchant:             {pay_in.merchant.user.username if pay_in and pay_in.merchant else ''}")
    print(f"amount:               {pay_in.amount if pay_in else ''} {pay_in.currency.symbol if pay_in and pay_in.currency else ''}")
    print(f"pay_in status:        {pay_in.status.name if pay_in and pay_in.status else ''}")
    print(f"in_order status:      {order.status.name if order and order.status else ''}")
    print(f"last webhook status:  {session.last_notified_status}")
    print("=" * 60)
    print(f"diagnose: python manage.py diagnose_payin {pay_in.id}")


if DEAL_ID:
    run()
