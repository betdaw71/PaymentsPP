import unittest

import bot


class LookupGateTest(unittest.TestCase):
    def test_public_start_has_no_counterparty_names(self):
        text = bot.PUBLIC_HELP_TEXT.lower()
        for word in ("melbet", "мелбет", "aggrepay", "mostbet", "pandapay", "resdfe", "astrum", "gipay", "visionx", "patriot"):
            self.assertNotIn(word, text)
        self.assertNotIn("/lookup", bot.PUBLIC_HELP_TEXT)

    def test_lookup_only_in_ops_group(self):
        self.assertTrue(bot._is_ops_lookup_chat(-5584894348))
        self.assertTrue(bot._is_ops_lookup_chat("-5584894348"))
        self.assertFalse(bot._is_ops_lookup_chat(12345))
        self.assertFalse(bot._is_ops_lookup_chat(-100123))
        self.assertNotIn("/lookup", bot._help_text_for_chat(12345))
        self.assertIn("/lookup", bot._help_text_for_chat(-5584894348))


if __name__ == "__main__":
    unittest.main()
