import asyncio
import unittest

from app.services.llm.token_budget import TokenBudget


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def make(tpm: int = 6000, max_completion: int = 1000) -> tuple[TokenBudget, FakeClock]:
    clock = FakeClock()
    return TokenBudget(tpm, max_completion, clock=clock, sleep=clock.sleep), clock


def run(coro):
    return asyncio.run(coro)


class TestTokenBudget(unittest.TestCase):
    def test_within_budget_no_wait(self):
        budget, _ = make(6000)
        self.assertEqual(run(budget.acquire(2000)), 0.0)
        self.assertEqual(run(budget.acquire(4000)), 0.0)

    def test_over_budget_waits_for_refill(self):
        budget, clock = make(6000)  # 100 токенів/с
        run(budget.acquire(6000))
        waited = run(budget.acquire(1500))
        self.assertAlmostEqual(waited, 15.0, places=6)
        self.assertAlmostEqual(clock.now, 15.0, places=6)

    def test_refills_over_time_but_not_above_capacity(self):
        budget, clock = make(6000)
        run(budget.acquire(6000))
        clock.now += 600
        self.assertEqual(run(budget.acquire(6000)), 0.0)

    def test_request_larger_than_capacity_is_capped(self):
        budget, _ = make(6000)
        self.assertEqual(run(budget.acquire(50_000)), 0.0)

    def test_reservation_includes_max_completion(self):
        budget, _ = make(6000, max_completion=2500)
        self.assertGreaterEqual(budget.reservation(3000), 1000 + 2500)

    def test_failed_request_refunds_reservation(self):
        budget, _ = make(6000)
        run(budget.acquire(6000))
        budget.refund(3000)
        self.assertEqual(run(budget.acquire(3000)), 0.0)

    def test_settle_returns_unused_part_of_reservation(self):
        budget, _ = make(6000)
        run(budget.acquire(5000))                 # лишилося 1000
        budget.settle(prompt_chars=0, reserved=5000, actual_input=None, actual_total=2000)
        self.assertEqual(run(budget.acquire(4000)), 0.0)  # 1000 + 3000 повернених

    def test_settle_learns_prompt_scale(self):
        budget, _ = make(6000, max_completion=0)
        chars = 3000                              # база 1000 токенів
        for _ in range(20):
            r = budget.reservation(chars)
            budget.settle(chars, r, actual_input=1200, actual_total=1200)
        self.assertAlmostEqual(budget.reservation(chars), 1200, delta=15)


if __name__ == "__main__":
    unittest.main()
