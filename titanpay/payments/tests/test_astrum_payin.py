from django.test import SimpleTestCase, override_settings

from payments.astrum_client import (
    astrum_map_requisite,
    astrum_payin_webhook_outcome,
)


class AstrumMapRequisiteTest(SimpleTestCase):
    def test_card_from_result(self):
        req = astrum_map_requisite(
            {
                "success": True,
                "result": {
                    "innerId": "deal-1",
                    "requisite": "4400 4301 8283 9016",
                    "methodName": "Kaspi",
                    "firstName": "IVAN",
                    "lastName": "PETROV",
                },
            }
        )
        self.assertEqual(req["card_number"], "4400430182839016")
        self.assertEqual(req["bank"], "Kaspi")
        self.assertEqual(req["owner"], "IVAN PETROV")

    def test_phone_requisite(self):
        req = astrum_map_requisite({"result": {"requisite": "+77001234567", "methodName": "SBP"}})
        self.assertEqual(req["phone"], "+77001234567")
        self.assertEqual(req["bank"], "SBP")

    def test_empty_without_requisite(self):
        self.assertEqual(astrum_map_requisite({"success": True, "result": {}}), {})


class AstrumPayinWebhookOutcomeTest(SimpleTestCase):
    def test_success_statuses(self):
        for st in ("auto_success", "hand_success", "corrected"):
            self.assertEqual(astrum_payin_webhook_outcome({"status": st}), "success")

    def test_fail_statuses(self):
        for st in ("auto_decline", "chargeback"):
            self.assertEqual(astrum_payin_webhook_outcome({"status": st}), "fail")

    def test_nested_result_and_ignore(self):
        self.assertEqual(
            astrum_payin_webhook_outcome({"result": {"status": "auto_success"}}),
            "success",
        )
        self.assertIsNone(astrum_payin_webhook_outcome({"status": "waiting"}))


@override_settings(ASTRUM_TRADER_USERNAME="astrum_kzt")
class AstrumShareAliasTest(SimpleTestCase):
    def test_asterisk_alias_in_share_map(self):
        from payments.psp_payin import parse_routing_share_map

        parsed = parse_routing_share_map({"asterisk": 30, "gipay1": 70})
        self.assertEqual(str(parsed["astrum_kzt"]), "30")
        self.assertEqual(str(parsed["gipay1"]), "70")
