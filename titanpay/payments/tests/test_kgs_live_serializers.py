"""Живые Melbet KGS реквизиты: phone для PHONE/QR, card для C2CKGS."""
from django.test import SimpleTestCase

from payments.serializers import (
    PaymentDetailsCardSerializer,
    PaymentDetailsSberPaySerializer,
    get_in_ps_serializer,
)


class MelbetKgsLiveSerializerTest(SimpleTestCase):
    def test_phone_and_qr_use_phone_serializer(self):
        self.assertIs(get_in_ps_serializer("PHONEKGS"), PaymentDetailsSberPaySerializer)
        self.assertIs(get_in_ps_serializer("QRKGS"), PaymentDetailsSberPaySerializer)
        self.assertIs(get_in_ps_serializer("phonekgs"), PaymentDetailsSberPaySerializer)

    def test_c2ckgs_uses_card_serializer(self):
        self.assertIs(get_in_ps_serializer("C2CKGS"), PaymentDetailsCardSerializer)
