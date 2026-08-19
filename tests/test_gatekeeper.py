import unittest

from avito.gatekeeper import BOT_OWNED, NOT_OURS, classify_first_contact, bot_owns


class GatekeeperTests(unittest.TestCase):
    def test_empty_incoming_is_ours(self):
        messages = [
            {"type": "text", "author_id": 111, "created": 10},
        ]
        self.assertEqual(classify_first_contact(messages, self_user_id=999), BOT_OWNED)

    def test_prior_outgoing_is_not_ours(self):
        messages = [
            {"type": "text", "author_id": 999, "created": 5},
            {"type": "text", "author_id": 111, "created": 10},
        ]
        self.assertEqual(classify_first_contact(messages, self_user_id=999), NOT_OURS)

    def test_system_outgoing_ignored(self):
        messages = [
            {"type": "system", "author_id": 999, "created": 5},
            {"type": "text", "author_id": 111, "created": 10},
        ]
        self.assertEqual(classify_first_contact(messages, self_user_id=999), BOT_OWNED)

    def test_bot_owns(self):
        self.assertTrue(bot_owns({"status": "new"}))
        self.assertFalse(bot_owns({"status": "existing"}))
        self.assertFalse(bot_owns({"status": "manual"}))
        self.assertFalse(bot_owns(None))


if __name__ == "__main__":
    unittest.main()
