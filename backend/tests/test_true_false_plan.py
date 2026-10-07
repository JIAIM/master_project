import unittest

try:
    from app.services.generation.context import plan_true_false
    from app.services.generation.prompts import type_rules
except ImportError:  # потрібні залежності з контейнера
    plan_true_false = None


@unittest.skipIf(plan_true_false is None, "потрібні залежності бекенду")
class TestPlanTrueFalse(unittest.TestCase):
    def test_balanced(self):
        plan = plan_true_false(["true_false"] * 12)
        self.assertEqual(plan.count("true"), 6)
        self.assertEqual(plan.count("false"), 6)

    def test_not_all_in_a_row(self):
        plan = plan_true_false(["true_false"] * 12)
        self.assertNotEqual(plan, sorted(plan))

    def test_only_true_false_items(self):
        types = ["single_choice", "true_false", "single_choice", "true_false", "true_false"]
        plan = plan_true_false(types)
        self.assertEqual([plan[0], plan[2]], [None, None])
        self.assertTrue(all(plan[i] in ("true", "false") for i in (1, 3, 4)))
        self.assertIn(plan[1:].count("false"), (1, 2))

    def test_prompt_mentions_target(self):
        self.assertIn("MUST be FALSE", type_rules("true_false", 2, "Ukrainian", "false"))
        self.assertIn("MUST be TRUE", type_rules("true_false", 2, "Ukrainian", "true"))
        self.assertNotIn("MUST be", type_rules("single_choice", 4, "Ukrainian", None))


if __name__ == "__main__":
    unittest.main()
