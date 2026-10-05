"""Юніт-тести оцінювання та аналізу питань."""
import importlib.util
import pathlib
import sys
import unittest

from app.services.testing.grading import GradedItem, grade, is_answer_correct

ROOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ia = _load("item_analysis", "analytics/item_analysis.py")


class GradingTest(unittest.TestCase):
    def test_exact_set_required(self):
        self.assertTrue(is_answer_correct([3, 1], [1, 3]))
        self.assertFalse(is_answer_correct([1], [1, 3]))
        self.assertFalse(is_answer_correct([], []))

    def test_score_is_sum_of_points_for_correct(self):
        g = grade([
            GradedItem(1, 1.0, (10,), (10,)),     # правильно
            GradedItem(2, 2.0, (21,), (20,)),     # неправильно
            GradedItem(3, 1.0, (), (30,)),        # без відповіді
            GradedItem(4, 1.0, (40,), (40,)),     # правильно
        ])
        self.assertEqual(g.score, 2.0)
        self.assertEqual(g.max_score, 5.0)
        self.assertEqual(g.correct_count, 2)
        self.assertEqual(g.answered_count, 3)
        self.assertEqual(g.total, 4)

    def test_empty_test(self):
        g = grade([])
        self.assertEqual((g.score, g.max_score, g.total), (0, 0, 0))


def _responses(matrix, qids=(10, 20, 30)):
    out = []
    for pid, row in enumerate(matrix, start=1):
        for qid, v in zip(qids, row):
            out.append(ia.Response(pid, qid, bool(v), 1000, (qid + (1 if v else 2),)))
    return out


class ItemAnalysisTest(unittest.TestCase):
    # Q10 — добре питання, Q20 — занадто легке, Q30 — «перевернуте» (помилка в ключі)
    MATRIX = [
        [1, 1, 0],
        [1, 1, 0],
        [1, 1, 0],
        [1, 1, 1],
        [0, 1, 1],
        [0, 1, 1],
    ]

    def test_p_values(self):
        stats = ia.analyze(_responses(self.MATRIX))
        p = {i.question_id: i.p_value for i in stats.items}
        self.assertAlmostEqual(p[10], 4 / 6)
        self.assertAlmostEqual(p[20], 1.0)

    def test_flags(self):
        stats = ia.analyze(_responses(self.MATRIX))
        flags = {i.question_id: i.flags for i in stats.items}
        self.assertIn("too_easy", flags[20])
        self.assertIn("negative_discrimination", flags[30])

    def test_kr20_perfect_scale(self):
        guttman = [[1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0]]
        self.assertAlmostEqual(ia.kr20(guttman), 0.75)

    def test_kr20_degenerate(self):
        self.assertIsNone(ia.kr20([[1, 1], [1, 1]]))

    def test_nonfunctional_distractor(self):
        # 20 відповідей: 15 правильних (100), 5 обрали 101, варіант 102 не обрав ніхто
        resp = [ia.Response(p, 1, p > 5, None, (100 if p > 5 else 101,)) for p in range(1, 21)]
        stats = ia.analyze(resp, correct_options={1: {100}}, all_options={1: {100, 101, 102}})
        item = stats.items[0]
        self.assertIn("nonfunctional_distractor:102", item.flags)
        self.assertNotIn("nonfunctional_distractor:101", item.flags)
        self.assertEqual(item.option_counts[102], 0)


if __name__ == "__main__":
    unittest.main()
