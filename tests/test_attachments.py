import asyncio
import tempfile
import unittest
from pathlib import Path

from avito.api import attachment_url, best_image_url
from avito.bot_worker import AvitoBot
from avito.gatekeeper import BOT_OWNED, MANUAL
from config.settings import SETTINGS
from db.database import Database


class FakeTelegram:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.media: list[tuple[str, str, bytes]] = []

    async def send(self, text: str) -> bool:
        self.texts.append(text)
        return True

    async def send_photo(self, data: bytes, *, filename: str = "", caption: str = "") -> bool:
        self.media.append(("photo", filename, data))
        return True

    async def send_audio(self, data: bytes, *, filename: str = "", caption: str = "") -> bool:
        self.media.append(("audio", filename, data))
        return True

    async def send_document(self, data: bytes, *, filename: str = "", caption: str = "") -> bool:
        self.media.append(("document", filename, data))
        return True


class UrlTests(unittest.TestCase):
    def test_best_image_url_picks_largest(self) -> None:
        message = {
            "content": {
                "image": {
                    "sizes": {
                        "140x105": "https://avito/small.jpg",
                        "1280x960": "https://avito/big.jpg",
                    }
                }
            }
        }
        self.assertEqual(best_image_url(message), "https://avito/big.jpg")

    def test_attachment_url_finds_nested_link(self) -> None:
        message = {"content": {"file": {"name": "смета.pdf", "url": "https://avito/f.pdf"}}}
        self.assertEqual(attachment_url(message), "https://avito/f.pdf")

    def test_no_url_returns_none(self) -> None:
        self.assertIsNone(attachment_url({"content": {"location": {"lat": 55.7}}}))


class HandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = AvitoBot(SETTINGS)
        self.bot.db = Database(path=Path(self.tmp.name) / "dialogs.db")
        self.bot._user_id = 999
        self.bot.db.create(chat_id="c1", status=BOT_OWNED)
        self.tg = FakeTelegram()
        self.bot.tg = self.tg

        async def fake_download(url: str) -> bytes:
            return b"binary"

        self.bot.api.download = fake_download

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_photo_stops_bot_and_goes_to_group(self) -> None:
        message = {
            "author_id": 111,
            "created": 10,
            "type": "image",
            "content": {"image": {"sizes": {"1280x960": "https://avito/big.jpg"}}},
        }
        asyncio.run(self.bot._handoff_attachment("c1", [message]))
        self.assertEqual(self.bot.db.get("c1")["status"], MANUAL)
        self.assertEqual([m[0] for m in self.tg.media], ["photo"])
        self.assertIn("фото", self.tg.texts[0])

    def test_unknown_file_goes_as_document(self) -> None:
        message = {
            "author_id": 111,
            "created": 10,
            "type": "file",
            "content": {"file": {"name": "смета.pdf", "url": "https://avito/f.pdf"}},
        }
        asyncio.run(self.bot._handoff_attachment("c1", [message]))
        self.assertEqual(self.bot.db.get("c1")["status"], MANUAL)
        self.assertEqual(self.tg.media[0][:2], ("document", "смета.pdf"))

    def test_call_only_keeps_bot_working(self) -> None:
        message = {"author_id": 111, "created": 10, "type": "call", "content": {"call": {}}}
        asyncio.run(self.bot._handoff_attachment("c1", [message]))
        self.assertEqual(self.bot.db.get("c1")["status"], BOT_OWNED)
        self.assertEqual(self.tg.media, [])

    def test_text_next_to_photo_lands_in_history(self) -> None:
        message = {"author_id": 111, "created": 10, "type": "image", "content": {"image": {}}}
        asyncio.run(
            self.bot._handoff_attachment("c1", [message], ["Посчитайте по этому фото"])
        )
        history = [m["content"] for m in self.bot.db.history("c1")]
        self.assertEqual(history, ["Посчитайте по этому фото", "[клиент прислал фото]"])
        self.assertIn("Посчитайте по этому фото", self.tg.texts[0])

    def test_history_keeps_attachment_fact(self) -> None:
        message = {"author_id": 111, "created": 10, "type": "image", "content": {"image": {}}}
        asyncio.run(self.bot._handoff_attachment("c1", [message]))
        self.assertEqual(self.bot.db.history("c1")[-1]["content"], "[клиент прислал фото]")


if __name__ == "__main__":
    unittest.main()
