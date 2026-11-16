"""Живые Melbet KGS реквизиты: phone для PHONE, QR payload для QRKGS, card для C2CKGS."""
from django.test import SimpleTestCase

from payments.serializers import (
    PaymentDetailsCardSerializer,
    PaymentDetailsQrKgsSerializer,
    PaymentDetailsSberPaySerializer,
    get_in_ps_serializer,
)


class MelbetKgsLiveSerializerTest(SimpleTestCase):
    def test_phone_uses_phone_serializer(self):
        self.assertIs(get_in_ps_serializer("PHONEKGS"), PaymentDetailsSberPaySerializer)
        self.assertIs(get_in_ps_serializer("phonekgs"), PaymentDetailsSberPaySerializer)

    def test_qrkgs_uses_qr_serializer(self):
        self.assertIs(get_in_ps_serializer("QRKGS"), PaymentDetailsQrKgsSerializer)

    def test_c2ckgs_uses_card_serializer(self):
        self.assertIs(get_in_ps_serializer("C2CKGS"), PaymentDetailsCardSerializer)
