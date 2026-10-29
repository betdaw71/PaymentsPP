"""
Срочно выключить Protocol PSP (protocol1) из выдачи.

Ставит User.is_active=False, Trader.blocked=True, группы status=0 / in_active=False.
До деплоя с DISABLED_PSP этого скрипта достаточно, чтобы убрать protocol из cascade.

  docker compose exec -T app python manage.py shell \
    < titanpay/basics/shell_disable_protocol_psp.py

Из контейнера (/app):
  python manage.py shell < basics/shell_disable_protocol_psp.py
"""
from django.conf import settings
from django.contrib.auth.models import User

from basics.models import PaymentDetails, PaymentDetailsGroup, Trader

USERNAME = (getattr(settings, "PROTOCOL_TRADER_USERNAME", None) or "protocol1").strip() or "protocol1"

print(f"Disable Protocol PSP: {USERNAME}")
user = User.objects.filter(username__iexact=USERNAME).first()
if user is None:
    raise SystemExit(f"  ! user {USERNAME!r} not found")

if user.is_active:
    user.is_active = False
    user.save(update_fields=["is_active"])
    print(f"  + {USERNAME}: User.is_active=False")
else:
    print(f"  ~ {USERNAME}: user already inactive")

trader = Trader.objects.filter(user=user).first()
if trader is None:
    raise SystemExit(f"  ! trader for {USERNAME!r} not found")

if not trader.blocked:
    trader.blocked = True
    trader.save(update_fields=["blocked"])
    print(f"  + {USERNAME}: Trader.blocked=True")
else:
    print(f"  ~ {USERNAME}: trader already blocked")

groups = PaymentDetailsGroup.objects.filter(trader=trader)
n_g = groups.update(status=0, in_active=False, out_active=False)
n_pd = PaymentDetails.objects.filter(group__trader=trader).update(status=0)
print(f"  + {USERNAME}: groups_updated={n_g} details_updated={n_pd}")

for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
    ps = g.payment_system.name if g.payment_system_id else "?"
    print(f"    group {g.id} ps={ps} status={g.status} in_active={g.in_active} out_active={g.out_active}")

print("done — protocol1 вне выдачи (in_active=False + blocked)")
