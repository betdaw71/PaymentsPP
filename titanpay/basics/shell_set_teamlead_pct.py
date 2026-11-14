"""Проставить teamlead_percentage на всех командах тимлида.

PCT = % от оборота сделки (usd_amount), не от trader_fee.
Пример: 0.5 → тимлид получает 0.5% оборота resdfe.

  # dry-run (neuyz → 0.5% от оборота)
  docker compose exec -T -e TEAMLEAD=neuyz -e PCT=0.5 app python manage.py shell \\
    < titanpay/basics/shell_set_teamlead_pct.py

  APPLY=1 — записать.
"""
from __future__ import annotations

import os
from decimal import Decimal

from basics.models import TeamLead, TraderTeam

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
USERNAME = (os.environ.get("TEAMLEAD") or "neuyz").strip()
PCT = Decimal((os.environ.get("PCT") or "0.5").strip())

tl = TeamLead.objects.select_related("user").filter(user__username__iexact=USERNAME).first()
if tl is None:
    print(f"FAIL: teamlead username={USERNAME!r} not found")
    # hint similar names
    near = list(
        TeamLead.objects.select_related("user")
        .filter(user__username__icontains=USERNAME[:4])
        .values_list("user__username", flat=True)[:10]
    )
    if near:
        print(f"  similar: {near}")
    raise SystemExit(1)

teams = list(TraderTeam.objects.filter(teamlead=tl).order_by("name"))
print(f"teamlead={tl.user.username} teams={len(teams)} target pct={PCT}% APPLY={APPLY}")
for team in teams:
    if Decimal(str(team.teamlead_percentage or 0)) != PCT:
        print(f"  team={team.name}: {team.teamlead_percentage}% → {PCT}%")
        if APPLY:
            team.teamlead_percentage = PCT
            team.save(update_fields=["teamlead_percentage"])
    else:
        print(f"  team={team.name}: {team.teamlead_percentage}% (ok)")
if not teams:
    print("  ! no teams linked to this teamlead")
print("DONE")
