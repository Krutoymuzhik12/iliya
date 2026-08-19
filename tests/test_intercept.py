import tempfile
import unittest
from pathlib import Path

from avito.bot_worker import AvitoBot
from avito.gatekeeper import BOT_OWNED, MANUAL
from config.settings import SETTINGS
from db.database import Database


class InterceptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = AvitoBot(SETTINGS)
        self.bot.db = Database(path=Path(self.tmp.name) / "dialogs.db")
        self.bot._user_id = 999
        self.bot.db.create(chat_id="c1", status=BOT_OWNED)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_manager_hand_message_stops_bot(self) -> None:
        self.bot.db.remember_sent("c1", "Здравствуйте! На связи Илья")
        status = self.bot._apply_owner_messages(
            "c1",
            [
                {
                    "author_id": 999,
                    "created": 10,
                    "type": "text",
                    "content": {"text": "Здравствуйте! На связи Илья"},
                },
                {
                    "author_id": 999,
                    "created": 20,
                    "type": "text",
                    "content": {"text": "Добрый день, это живой менеджер"},
                },
            ],
        )
        self.assertEqual(status, MANUAL)
        self.assertEqual(self.bot.db.get("c1")["status"], MANUAL)

    def test_bots_own_outgoing_does_not_stop(self) -> None:
        self.bot.db.remember_sent("c1", "Здравствуйте! На связи Илья")
        status = self.bot._apply_owner_messages(
            "c1",
            [
                {
                    "author_id": 999,
                    "created": 10,
                    "type": "text",
                    "content": {"text": "Здравствуйте! На связи Илья"},
                }
            ],
        )
        self.assertEqual(status, BOT_OWNED)

    def test_stop_and_start_commands(self) -> None:
        self.bot._apply_owner_messages(
            "c1",
            [{"author_id": 999, "created": 10, "type": "text", "content": {"text": "#стоп"}}],
        )
        self.assertEqual(self.bot.db.get("c1")["status"], MANUAL)
        self.bot._apply_owner_messages(
            "c1",
            [{"author_id": 999, "created": 20, "type": "text", "content": {"text": "#старт"}}],
        )
        self.assertEqual(self.bot.db.get("c1")["status"], BOT_OWNED)

    def test_messages_before_bot_start_are_not_ours(self) -> None:
        self.bot._started_at = 1000
        chat = {
            "id": "c-old",
            "users": [{"id": 111, "name": "Клиент"}],
            "context": {"type": "item", "value": {"id": 1, "title": "Окна"}},
        }
        dialog = self.bot._register_new_chat(
            chat,
            [{"author_id": 111, "created": 500, "type": "text", "content": {"text": "здравствуйте"}}],
        )
        self.assertEqual(dialog["status"], "existing")

    def test_empty_chat_after_start_is_ours(self) -> None:
        self.bot._started_at = 1000
        chat = {
            "id": "c-new",
            "users": [{"id": 111, "name": "Клиент"}],
            "context": {"type": "item", "value": {"id": 1, "title": "Окна"}},
        }
        dialog = self.bot._register_new_chat(
            chat,
            [{"author_id": 111, "created": 1500, "type": "text", "content": {"text": "здравствуйте"}}],
        )
        self.assertEqual(dialog["status"], BOT_OWNED)


class HistoryLimitTests(unittest.TestCase):
    def test_history_keeps_last_40(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(path=Path(tmp) / "dialogs.db")
            db.create(chat_id="c1", status=BOT_OWNED)
            for i in range(50):
                db.append_message("c1", "user" if i % 2 == 0 else "assistant", f"msg-{i}")
            history = db.history("c1")
            self.assertEqual(len(history), SETTINGS.history_limit)
            self.assertEqual(history[0]["content"], "msg-10")
            self.assertEqual(history[-1]["content"], "msg-49")


if __name__ == "__main__":
    unittest.main()
