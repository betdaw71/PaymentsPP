from django.test import SimpleTestCase

from basics.qr_payload import payment_page_fields_from_qr_payload


class QrPayloadTest(SimpleTestCase):
    def test_data_uri_passthrough(self):
        raw = "data:image/png;base64,aaa"
        self.assertEqual(
            payment_page_fields_from_qr_payload(raw),
            {"qr_image_url": raw},
        )

    def test_image_url_passthrough(self):
        url = "https://cdn.example/qr.png"
        self.assertEqual(
            payment_page_fields_from_qr_payload(url),
            {"qr_image_url": url},
        )

    def test_media_pd_qr_url_passthrough(self):
        url = "https://api.example/media/pd_qr/abc/deadbeef.jpg"
        self.assertEqual(
            payment_page_fields_from_qr_payload(url),
            {"qr_image_url": url},
        )

    def test_emv_string_becomes_qr_image(self):
        fields = payment_page_fields_from_qr_payload("00020101021238570010A0000007270139")
        self.assertTrue(fields["qr_image_url"].startswith("data:image/png;base64,"))

    def test_http_link_gets_qr_and_form_url(self):
        url = "https://qrnspk.ru/l/abc"
        fields = payment_page_fields_from_qr_payload(url)
        self.assertEqual(fields["payment_form_url"], url)
        self.assertTrue(fields["qr_image_url"].startswith("data:image/png;base64,"))


class QrKgsSerializerPickTest(SimpleTestCase):
    def test_get_in_ps_serializer_qrkgs(self):
        from payments.serializers import (
            PaymentDetailsQrKgsSerializer,
            get_in_ps_serializer,
        )

        self.assertIs(get_in_ps_serializer("QRKGS"), PaymentDetailsQrKgsSerializer)
