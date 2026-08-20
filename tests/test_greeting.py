import unittest

from services.poe import strip_greeting


class StripGreetingTests(unittest.TestCase):
    def test_double_greeting_cut(self) -> None:
        text = strip_greeting("Здравствуйте! добрый день!\n\nПо ценам договоримся.")
        self.assertEqual(text, "По ценам договоримся.")

    def test_single_greeting_cut_and_capitalized(self) -> None:
        self.assertEqual(
            strip_greeting("Здравствуйте! спасибо, номер записал."),
            "Спасибо, номер записал.",
        )
        self.assertEqual(
            strip_greeting("Добрый день, замерщик перезвонит."),
            "Замерщик перезвонит.",
        )

    def test_reply_without_greeting_untouched(self) -> None:
        text = "Замер бесплатный и ни к чему не обязывает."
        self.assertEqual(strip_greeting(text), text)

    def test_greeting_only_reply_kept(self) -> None:
        self.assertEqual(strip_greeting("Здравствуйте!"), "Здравствуйте!")

    def test_no_cut_without_punctuation(self) -> None:
        text = "Приветствую вас на связи Илья"
        self.assertEqual(strip_greeting(text), text)

    def test_repeated_greeting_forms(self) -> None:
        self.assertEqual(
            strip_greeting("Здравствуйте ещё раз! замерщик наберёт."),
            "Замерщик наберёт.",
        )
        self.assertEqual(
            strip_greeting("И вам здравствуйте! по цене договоримся."),
            "По цене договоримся.",
        )


if __name__ == "__main__":
    unittest.main()
