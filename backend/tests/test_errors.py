import unittest

try:
    from app.core.errors import translate
except ImportError:  # потрібні залежності з контейнера
    translate = None


@unittest.skipIf(translate is None, "потрібні залежності бекенду")
class TestTranslate(unittest.TestCase):
    def test_short_string(self):
        msg = translate({"type": "string_too_short", "loc": ("body", "password"), "ctx": {"min_length": 8}})
        self.assertEqual(msg, "Пароль: щонайменше 8 символів")

    def test_plural(self):
        msg = translate({"type": "string_too_short", "loc": ("body", "display_name"), "ctx": {"min_length": 2}})
        self.assertEqual(msg, "Ім'я: щонайменше 2 символи")

    def test_pin(self):
        msg = translate({"type": "string_pattern_mismatch", "loc": ("body", "pin"), "ctx": {}})
        self.assertEqual(msg, "PIN: має складатися з 6 цифр")

    def test_own_value_error(self):
        msg = translate({"type": "value_error", "loc": ("body",), "msg": "Value error, Має бути рівно один правильний варіант"})
        self.assertEqual(msg, "Має бути рівно один правильний варіант")

    def test_unknown(self):
        self.assertIn("некоректне значення", translate({"type": "weird", "loc": ("body", "title")}))


if __name__ == "__main__":
    unittest.main()
