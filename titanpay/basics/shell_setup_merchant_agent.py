"""
Django shell: тестовый агент (TeamLead) + привязка мерчанта.

Запуск:
  docker compose exec app python manage.py shell < titanpay/basics/shell_setup_merchant_agent.py

Или в shell:
  exec(open('titanpay/basics/shell_setup_merchant_agent.py').read())

Переменные (опционально):
  AGENT_USERNAME — логин агента (TeamLead), по умолчанию agent_demo
  AGENT_PASSWORD — пароль, по умолчанию AgentDemo1!Q
  MERCHANT_USERNAME — мерчант для привязки (должен существовать)
  TURNOVER_IN / TURNOVER_OUT — % от оборота, по умолчанию 0.5
"""
import os
from decimal import Decimal

from django.contrib.auth.models import User

from basics.models import Balance, Language, TeamLead
from merchant.models import Merchant, MerchantAgentAssignment

AGENT_USERNAME = os.getenv("AGENT_USERNAME", "agent_demo")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "AgentDemo1!Q")
MERCHANT_USERNAME = os.getenv("MERCHANT_USERNAME", "merchant")
TURNOVER_IN = Decimal(os.getenv("TURNOVER_IN", "0.5"))
TURNOVER_OUT = Decimal(os.getenv("TURNOVER_OUT", "0.5"))

language = Language.objects.first()
if language is None:
    language = Language.objects.create(name="English")

user, created = User.objects.get_or_create(
    username=AGENT_USERNAME,
    defaults={"email": f"{AGENT_USERNAME}@example.com"},
)
if created:
    user.set_password(AGENT_PASSWORD)
    user.save()
    print(f"Created user {AGENT_USERNAME} / {AGENT_PASSWORD}")
else:
    print(f"Using existing user {AGENT_USERNAME}")

teamlead, tl_created = TeamLead.objects.get_or_create(
    user=user,
    defaults={"language": language},
)
if tl_created or teamlead.balance is None:
    bal = Balance.objects.create(type=0, amount=Decimal("0"))
    teamlead.balance = bal
    teamlead.save(update_fields=["balance"])
    print(f"TeamLead balance id={bal.id}")

merchant = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
if merchant is None:
    raise SystemExit(f"Merchant user {MERCHANT_USERNAME!r} not found — create merchant first")

assignment, a_created = MerchantAgentAssignment.objects.update_or_create(
    merchant=merchant,
    defaults={
        "agent": teamlead,
        "turnover_percent_in": TURNOVER_IN,
        "turnover_percent_out": TURNOVER_OUT,
        "is_active": True,
    },
)
print(
    f"Assignment {'created' if a_created else 'updated'}: "
    f"{merchant.user.username} → {teamlead.user.username} "
    f"in={assignment.turnover_percent_in}% out={assignment.turnover_percent_out}%"
)
print(f"TeamLead id={teamlead.id}  login={AGENT_USERNAME}")
