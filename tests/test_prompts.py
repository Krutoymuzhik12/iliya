import unittest
from pathlib import Path

from config.settings import PROMPTS_DIR
from services.poe import _sanitize_reply


class ManagerPromptTests(unittest.TestCase):
    def test_prompt_is_center_balkon_alexey(self) -> None:
        text = (PROMPTS_DIR / "manager.txt").read_text(encoding="utf-8")
        self.assertIn("Алексей", text)
        self.assertIn("Центр-Балкон", text)
        self.assertIn("чате Авито", text)
        self.assertNotIn("чате в ТГ", text)
        self.assertIn("[НУЖЕН_МЕНЕДЖЕР]", text)
        self.assertIn("110% разницы", text)

    def test_need_manager_marker_stripped(self) -> None:
        text, need = _sanitize_reply("Секунду, уточню.\n[НУЖЕН_МЕНЕДЖЕР]")
        self.assertTrue(need)
        self.assertEqual(text, "Секунду, уточню.")
        self.assertNotIn("НУЖЕН_МЕНЕДЖЕР", text)

    def test_emdash_replaced(self) -> None:
        text, need = _sanitize_reply("Замер бесплатный — ни к чему не обязывает.")
        self.assertFalse(need)
        self.assertNotIn("—", text)
        self.assertIn("-", text)


if __name__ == "__main__":
    unittest.main()
