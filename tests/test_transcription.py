import unittest

from services.transcription import _dedupe, failed


class DedupeTest(unittest.TestCase):
    def test_doubled_text_collapses(self):
        self.assertEqual(_dedupe("нужно три окна нужно три окна"), "нужно три окна")

    def test_normal_text_untouched(self):
        text = "Здравствуйте, нужны четыре стеклопакета по нашим размерам"
        self.assertEqual(_dedupe(text), text)


class FailedTest(unittest.TestCase):
    def test_service_message_is_failure(self):
        self.assertTrue(failed("[ошибка транскрибации]"))
        self.assertTrue(failed(""))

    def test_speech_is_not_failure(self):
        self.assertFalse(failed("Нужны три окна на дачу"))


if __name__ == "__main__":
    unittest.main()
