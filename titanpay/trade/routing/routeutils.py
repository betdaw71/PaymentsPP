from django.db.models import Exists, OuterRef
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
