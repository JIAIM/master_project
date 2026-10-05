import unittest

from app.services.generation.content_filters import is_reference_like


class TestIsReferenceLike(unittest.TestCase):
    def test_recognizes_ukrainian_heading(self):
        text = "Рекомендована література\n1. Іванов І. Основи програмування. Київ, 2020."
        self.assertTrue(is_reference_like(text))

    def test_recognizes_reference_list_heading_ru(self):
        text = "Список использованных источников\n[1] см. документацию проекта."
        self.assertTrue(is_reference_like(text))

    def test_recognizes_english_heading(self):
        text = "References\n[1] Smith, J. (2019). Some Paper. Journal of Things."
        self.assertTrue(is_reference_like(text))

    def test_recognizes_dense_url_list_without_heading(self):
        text = (
            "Gorilla: https://github.com/gorilla/mux\n"
            "Gin: https://github.com/gin-gonic/gin\n"
            "Echo: https://echo.labstack.com\n"
            "Fiber: https://gofiber.io\n"
        )
        self.assertTrue(is_reference_like(text))

    def test_recognizes_table_of_contents(self):
        text = (
            "Вступ………………………… 4\n"
            "6.1 Поняття основних фондів……………. 5\n"
            "6.2 Показники стану і руху…….. 6\n"
        )
        self.assertTrue(is_reference_like(text))

    def test_regular_teaching_text_is_not_reference_like(self):
        text = (
            "Операційна система — це комплекс програм, що керує апаратними ресурсами "
            "комп'ютера. Основні функції ОС включають управління процесами, пам'яттю "
            "та файловою системою."
        )
        self.assertFalse(is_reference_like(text))

    def test_single_url_in_normal_text_is_not_reference_like(self):
        text = (
            "Офіційна документація фреймворку доступна за адресою https://example.com/docs, "
            "але основна ідея middleware полягає в тому, що кожен обробник може передати "
            "керування наступному в ланцюжку."
        )
        self.assertFalse(is_reference_like(text))


if __name__ == "__main__":
    unittest.main()
