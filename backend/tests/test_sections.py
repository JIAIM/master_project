import unittest
from dataclasses import dataclass

from app.services.generation.sections import section_chunks, topic_section


@dataclass
class C:
    text: str
    chunk_index: int
    material_id: int = 1


def make(*texts: str) -> list[C]:
    return [C(t, i) for i, t in enumerate(texts)]


class TestTopicSection(unittest.TestCase):
    def test_lecture_number(self):
        self.assertEqual(topic_section("Лекція 6"), (6, ""))
        self.assertEqual(topic_section("ТЕМА 3."), (3, ""))
        self.assertEqual(topic_section("6 лекція"), (6, ""))

    def test_rest_of_topic(self):
        self.assertEqual(topic_section("Лекція 6. Амортизація"), (6, "Амортизація"))

    def test_no_section(self):
        self.assertIsNone(topic_section("Амортизація основних фондів"))


class TestSectionChunks(unittest.TestCase):
    def test_skips_table_of_contents(self):
        chunks = make(
            "Зміст. Лекція 6. Основні фонди. Лекція 7. Оборотні засоби. Тема 8. Витрати",
            "Вступ до курсу",
            "ЛЕКЦІЯ 6. Основні фонди підприємства",
            "Поняття основних фондів",
            "Амортизація основних фондів",
            "ЛЕКЦІЯ 7. Оборотні засоби",
            "Склад оборотних засобів",
        )
        self.assertEqual([c.chunk_index for c in section_chunks(chunks, 6)], [2, 3, 4])
        self.assertEqual([c.chunk_index for c in section_chunks(chunks, 7)], [5, 6])

    def test_missing_section(self):
        self.assertEqual(section_chunks(make("Лекція 1", "текст"), 9), [])


if __name__ == "__main__":
    unittest.main()
