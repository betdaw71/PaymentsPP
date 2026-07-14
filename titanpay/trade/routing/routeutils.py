from django.db.models import Exists, OuterRef
from basics.models import TraderTeam, TraderTeamRates


def get_teams_for_ps(payment_system):
    return TraderTeam.objects.filter(
        Exists(TraderTeamRates.objects.filter(
            team=OuterRef('pk'),
            payment_system=payment_system
        ))
    )