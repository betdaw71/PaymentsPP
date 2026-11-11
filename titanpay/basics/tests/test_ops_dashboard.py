from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from basics.ops_dashboard import resolve_period

MSK = ZoneInfo("Europe/Moscow")


class OpsDashboardPeriodTest(SimpleTestCase):
    def test_today_window(self):
        now = datetime(2026, 11, 3, 18, 30, tzinfo=MSK)
        start, end, kind = resolve_period(preset="today", now=now)
        self.assertEqual(kind, "today")
        self.assertEqual(start.isoformat(), "2026-11-03T00:00:00+03:00")
        self.assertEqual(end.isoformat(), "2026-11-04T00:00:00+03:00")

    def test_7d_includes_today(self):
        now = datetime(2026, 11, 3, 12, 0, tzinfo=MSK)
        start, end, kind = resolve_period(preset="7d", now=now)
        self.assertEqual(kind, "7d")
        self.assertEqual(start.date().isoformat(), "2026-10-28")
        self.assertEqual(end.date().isoformat(), "2026-11-04")

    def test_custom_range(self):
        start, end, kind = resolve_period(
            preset="custom",
            date_from="2026-10-01",
            date_to="2026-10-09",
            now=datetime(2026, 11, 3, tzinfo=MSK),
        )
        self.assertEqual(kind, "custom")
        self.assertEqual(start.isoformat(), "2026-10-01T00:00:00+03:00")
        self.assertEqual(end.isoformat(), "2026-10-10T00:00:00+03:00")
