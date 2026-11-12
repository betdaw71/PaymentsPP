from django.db.models import Exists, OuterRef, Q
from basics.models import TraderTeam, TraderTeamRates


def get_teams_for_ps(payment_system):
    return get_teams_for_payment_systems([payment_system])


def get_teams_for_payment_systems(payment_systems):
    systems = [ps for ps in payment_systems if ps is not None]
    if not systems:
        return TraderTeam.objects.none()
    return TraderTeam.objects.filter(
        Exists(TraderTeamRates.objects.filter(
            team=OuterRef("pk"),
            payment_system__in=systems,
        ))
    )


def in_order_amount_q(amount, *, psp_q=None):
    """Сумма одного in-ордера в [min_amount_in, max_amount_in]. PSP не ограничиваем."""
    in_range = Q(min_amount_in__lte=amount) & Q(max_amount_in__gte=amount)
    if psp_q is None:
        return in_range
    return in_range | psp_q
