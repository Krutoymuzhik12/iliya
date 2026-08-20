import unittest

from services.names import COMPANY, PERSON, UNKNOWN, address_hint, classify_name


class ClassifyNameTests(unittest.TestCase):
    def test_real_names(self) -> None:
        for raw in ["Юлия", "юлия", "Иван Иванов", "Пётр", "Алёна", "Марат Сафин", "юля"]:
            self.assertEqual(classify_name(raw), PERSON, raw)

    def test_business_names(self) -> None:
        for raw in [
            "Дом Строитель",
            "Окна Самара",
            "Мастер+",
            "ООО Комфорт",
            "СтройДом",
            "Балкон63",
            "Ремонт квартир под ключ",
            "Мебель на заказ",
            "Авто-стекло",
        ]:
            self.assertEqual(classify_name(raw), COMPANY, raw)

    def test_person_names_not_eaten_by_stems(self) -> None:
        for raw in ["Автандил", "Ткачев Сергей", "Ипполит"]:
            self.assertNotEqual(classify_name(raw), COMPANY, raw)

    def test_unclear_stays_unknown(self) -> None:
        for raw in ["Вектор", "Заря", None, "", "   "]:
            self.assertEqual(classify_name(raw), UNKNOWN, raw)

    def test_hint_for_person_forbids_asking(self) -> None:
        hint = address_hint("Юлия")
        self.assertIsNotNone(hint)
        self.assertIn("Юлия", hint)
        self.assertIn("Не спрашивай", hint)

    def test_hint_for_company_allows_one_question(self) -> None:
        hint = address_hint("Дом Строитель")
        self.assertIsNotNone(hint)
        self.assertIn("вывеска", hint)

    def test_no_hint_when_unclear(self) -> None:
        self.assertIsNone(address_hint("Вектор"))
        self.assertIsNone(address_hint(None))


if __name__ == "__main__":
    unittest.main()
