"""
Блокирует retired PSP-трейдеров botonpay1 / paymap_kzt и выключает их группы.

Не трогает ключи мерчантов и другие PSP.

  docker compose exec -T app python manage.py shell < titanpay/basics/shell_disable_retired_psp_traders.py
"""
from django.contrib.auth.models import User

from basics.models import PaymentDetails, PaymentDetailsGroup, Trader

USERNAMES = ("botonpay1", "paymap_kzt")

print("Disable retired PSP traders")
for username in USERNAMES:
    user = User.objects.filter(username=username).first()
    if user is None:
        print(f"  ~ {username}: user not found")
        continue
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
        print(f"  + {username}: User.is_active=False")
    else:
        print(f"  ~ {username}: user already inactive")
    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        print(f"  ~ {username}: trader not found")
        continue
    if not trader.blocked:
        trader.blocked = True
        trader.save(update_fields=["blocked"])
        print(f"  + {username}: Trader.blocked=True")
    else:
        print(f"  ~ {username}: trader already blocked")
    groups = PaymentDetailsGroup.objects.filter(trader=trader)
    n_g = groups.update(status=0, in_active=False, out_active=False)
    n_pd = PaymentDetails.objects.filter(group__trader=trader).update(status=0)
    print(f"  + {username}: groups_updated={n_g} details_updated={n_pd}")
print("done")
