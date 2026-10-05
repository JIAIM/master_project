"""Юніт-тести детермінованого рівня перевірки (без БД і LLM)."""
import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace as NS

# Завантажуємо rules.py напряму, без залежностей пакета app
_path = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "verification" / "rules.py"
_spec = importlib.util.spec_from_file_location("rules", _path)
rules = importlib.util.module_from_spec(_spec)
sys.modules["rules"] = rules
_spec.loader.exec_module(rules)

CONTEXT = (
    "Протокол TCP забезпечує надійну доставку даних завдяки механізму підтверджень "
    "та повторної передачі втрачених сегментів. На відміну від нього, UDP не гарантує доставку."
)


def q(options, question="Який механізм забезпечує надійність доставки даних у TCP?",
      quote="забезпечує надійну доставку даних завдяки механізму підтверджень"):
    return NS(question=question, options=[NS(text=t, is_correct=c) for t, c in options], evidence_quote=quote)


GOOD = [
    ("Підтвердження та повторна передача", True),
    ("Шифрування кожного сегмента", False),
    ("Широкомовна розсилка пакетів", False),
    ("Стиснення заголовків пакетів", False),
]


def codes(question, qtype="single_choice", n=4):
    return {i.code for i in rules.check_question(question, question_type=qtype, expected_options=n, context=CONTEXT)}


class RulesTest(unittest.TestCase):
    def test_good_question_passes(self):
        self.assertEqual(codes(q(GOOD)), set())

    def test_two_correct_in_single_choice(self):
        opts = [(t, True) if i < 2 else (t, c) for i, (t, c) in enumerate(GOOD)]
        self.assertIn("correct_count", codes(q(opts)))

    def test_option_count(self):
        self.assertIn("option_count", codes(q(GOOD[:3])))

    def test_duplicates(self):
        opts = GOOD[:3] + [("шифрування кожного сегмента!", False)]
        self.assertIn("duplicate_options", codes(q(opts)))

    def test_banned_all_of_the_above(self):
        opts = GOOD[:3] + [("Усі перелічені варіанти", False)]
        self.assertIn("banned_option", codes(q(opts)))

    def test_length_bias(self):
        opts = [("Механізм підтверджень отримання сегментів та повторної передачі всіх втрачених сегментів", True),
                ("Шифрування", False), ("Маршрутизація", False), ("Стиснення", False)]
        self.assertIn("length_bias", codes(q(opts)))

    def test_hallucinated_quote(self):
        self.assertIn("quote_not_found", codes(q(GOOD, quote="TCP використовує квантове шифрування для захисту")))

    def test_quote_tolerates_punctuation(self):
        self.assertEqual(rules.quote_grounding("UDP, не гарантує доставку!", CONTEXT), 1.0)

    def test_refers_to_text(self):
        self.assertIn("refers_to_text", codes(q(GOOD, question="Що сказано у тексті про TCP?")))

    def test_multiple_choice_needs_two_correct(self):
        opts = GOOD + [("Керування перевантаженням", False)]
        self.assertIn("correct_count", codes(q(opts), "multiple_choice", 5))
        opts2 = [(GOOD[0][0], True), ("Повторна передача втрачених сегментів", True)] + GOOD[1:]
        self.assertNotIn("correct_count", codes(q(opts2), "multiple_choice", 5))


if __name__ == "__main__":
    unittest.main()
