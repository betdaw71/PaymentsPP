"""
Переприменить сумму PayPlat из quote_amount (last_webhook_payload или create_response).

Используйте если заявка Completed с неверной суммой (взяли fiat_amount вместо quote_amount).

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py

Или:
  PAY_IN_ID=0b39b587-2bd5-47bd-915a-8aaa06104b3f docker compose exec -T -e PAY_IN_ID=... app \\
    python manage.py shell < titanpay/basics/shell_payplat_reapply_success_amount.py
"""
import os

from payments.models import PayIn, PayplatPayInSession
from payments.payplat_client import payplat_webhook_paid_amount
from payments.psp_payin import handle_psp_success_webhook
from trade.models import InOrder

PAY_IN_ID = (os.environ.get("PAY_IN_ID") or "").strip()


def run() -> None:
    if not PAY_IN_ID:
        print("ERROR: set PAY_IN_ID env")
        return

    pay_in = PayIn.objects.filter(pk=PAY_IN_ID).select_related("order").first()
    if pay_in is None:
        print(f"PayIn {PAY_IN_ID!r} not found")
        return
    if pay_in.order_id is None:
        print("PayIn without InOrder")
        return

    session = PayplatPayInSession.objects.filter(pay_in=pay_in).first()
    if session is None:
        print("No PayPlat session")
        return

    body = session.last_webhook_payload or session.create_response or {}
    paid = payplat_webhook_paid_amount(body)
    print(f"PayIn amount now: {pay_in.amount}")
    print(f"quote_amount from session: {paid}")
    print(f"webhook status: {(body or {}).get('status')}")

    order = InOrder.objects.get(pk=pay_in.order_id)
    outcome = handle_psp_success_webhook(order, body)
    pay_in.refresh_from_db()
    order.refresh_from_db()
    print(f"outcome: {outcome}")
    print(f"PayIn amount after: {pay_in.amount}")
    print(f"InOrder amount after: {order.amount} recalculated={order.recalculated}")


run()
