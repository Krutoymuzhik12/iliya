import unittest

from services.leads import booked_from_history, is_measurement_booking, normalize_phone, phones_from_history, transcript


class LeadDetectTests(unittest.TestCase):
    def test_phone_formats(self) -> None:
        self.assertEqual(normalize_phone("89805247203"), "+79805247203")
        self.assertEqual(normalize_phone("+7 980 524-72-03"), "+79805247203")
        self.assertEqual(normalize_phone("номер 8 (980) 524 72 03"), "+79805247203")
        self.assertIsNone(normalize_phone("замер бесплатный"))

    def test_phones_only_from_client(self) -> None:
        history = [
            {"role": "assistant", "content": "Оставьте номер 89805247203"},
            {"role": "user", "content": "8 980 111 22 33"},
        ]
        self.assertEqual(phones_from_history(history), ["+79801112233"])

    def test_booking(self) -> None:
        self.assertTrue(is_measurement_booking("запишите на замер завтра"))
        self.assertTrue(is_measurement_booking("давайте на замер сегодня"))
        self.assertFalse(is_measurement_booking("замер бесплатный?"))
        self.assertFalse(is_measurement_booking("сколько стоит замер"))
        self.assertTrue(booked_from_history([{"role": "user", "content": "запишите на замер завтра"}]))

    def test_transcript(self) -> None:
        text = transcript(
            [
                {"role": "user", "content": "здравствуйте"},
                {"role": "assistant", "content": "Добрый день"},
            ]
        )
        self.assertIn("Клиент: здравствуйте", text)
        self.assertIn("Менеджер: Добрый день", text)


if __name__ == "__main__":
    unittest.main()
