import tempfile
import unittest
from pathlib import Path

from avito.gatekeeper import BOT_OWNED
from db.database import Database


class FollowupOncePerChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(path=Path(self.tmp.name) / "dialogs.db")
        self.db.create(chat_id="c1", status=BOT_OWNED)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_chat_becomes_candidate_after_client_message(self) -> None:
        self.db.append_message("c1", "user", "здравствуйте, сколько стоит")
        self.db.append_message("c1", "assistant", "Договоримся по цене")
        chats = [row["chat_id"] for row in self.db.candidates_for_followup()]
        self.assertIn("c1", chats)

    def test_no_second_followup_after_client_replies(self) -> None:
        self.db.append_message("c1", "user", "сколько стоит")
        self.db.append_message("c1", "assistant", "Договоримся по цене")
        self.db.record_followup_sent("c1", 1)
        self.assertEqual(self.db.candidates_for_followup(), [])

        self.db.append_message("c1", "user", "я подумаю")
        self.db.append_message("c1", "assistant", "Хорошо, буду на связи")
        self.assertEqual(self.db.candidates_for_followup(), [])


if __name__ == "__main__":
    unittest.main()
