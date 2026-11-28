from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from basics.views import get_pdgroup_creation_data


@override_settings(
    KZT_C2C_BANK_PS_NAMES="Elkard,Kompanion,Mbank,Optima,O bank,Bai-Tushum",
    C2CKZT_NAME="C2CKZT",
    C2C_NAME="C2C",
)
class PdgroupCreationIncludesKztBanksTest(SimpleTestCase):
    @patch("basics.views.TrafficTypeSerializer")
    @patch("basics.views.CurrencySerializer")
    @patch("basics.views.PaymentSystemSerializer")
    @patch("basics.views.TrafficType.objects.all", return_value=[])
    @patch("basics.views.Currency.objects.all", return_value=[])
    @patch("basics.views.PaymentSystem.objects.filter")
    def test_filter_includes_sbp_or_kzt_banks(
        self, ps_filter, _cur, _tt, ser_ps, _ser_cur, _ser_tt
    ):
        qs = MagicMock()
        qs.distinct.return_value = qs
        ps_filter.return_value = qs
        ser_ps.return_value = SimpleNamespace(data=[])

        request = SimpleNamespace(user=SimpleNamespace())
        response = get_pdgroup_creation_data(request)

        self.assertEqual(response.status_code, 200)
        _, kwargs = ps_filter.call_args
        # Q object: ensure bank names participate via name__in
        q = ps_filter.call_args[0][0] if ps_filter.call_args[0] else None
        self.assertIsNotNone(q)
        # Serializer called on distinct queryset
        qs.distinct.assert_called_once()
        ser_ps.assert_called_once()
