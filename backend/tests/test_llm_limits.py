import asyncio
import unittest

try:
    from langchain_core.runnables import RunnableLambda

    from app.services.llm import factory
    from app.services.llm.factory import (
        FallbackLLM, LLMLimitExhaustedError, _is_limit_error, exhausted_message,
    )
except ImportError:  # LangChain є лише в контейнері
    factory = None


class HttpError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeModel:
    def __init__(self, name: str, behaviour) -> None:
        self.model_name = name
        self.behaviour = behaviour
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        async def _run(_input):
            self.calls += 1
            return self.behaviour()
        return RunnableLambda(_run)


def raises(exc):
    def _b():
        raise exc
    return _b


def run(coro):
    return asyncio.run(coro)


@unittest.skipIf(factory is None, "потрібен LangChain")
class TestLimitDetection(unittest.TestCase):
    def test_status_codes(self):
        self.assertTrue(_is_limit_error(HttpError("boom", 429)))
        self.assertTrue(_is_limit_error(HttpError("payment", 402)))

    def test_message_markers(self):
        self.assertTrue(_is_limit_error(Exception("Rate limit reached for model, tokens per day (TPD)")))
        self.assertTrue(_is_limit_error(Exception("429 RESOURCE_EXHAUSTED: quota exceeded")))

    def test_other_errors(self):
        self.assertFalse(_is_limit_error(TimeoutError("Request timed out")))
        self.assertFalse(_is_limit_error(HttpError("Internal server error", 500)))


@unittest.skipIf(factory is None, "потрібен LangChain")
class TestFallbackExhaustion(unittest.TestCase):
    def setUp(self):
        factory._cooldown_until.clear()
        factory._exhausted_until.clear()

    tearDown = setUp

    def test_all_limits_raise_clear_error(self):
        a = FakeModel("a", raises(HttpError("rate limit, retry in 120s", 429)))
        b = FakeModel("b", raises(Exception("quota exceeded")))
        chain = FallbackLLM([a, b], role="generator").with_structured_output(dict)
        with self.assertRaises(LLMLimitExhaustedError) as ctx:
            run(chain.ainvoke("prompt"))
        self.assertIn("Ліміт запитів до ШІ вичерпано", str(ctx.exception))
        self.assertIsNotNone(exhausted_message())

    def test_next_call_skips_models_while_exhausted(self):
        a = FakeModel("a", raises(HttpError("rate limit", 429)))
        chain = FallbackLLM([a], role="critic").with_structured_output(dict)
        with self.assertRaises(LLMLimitExhaustedError):
            run(chain.ainvoke("prompt"))
        with self.assertRaises(LLMLimitExhaustedError):
            run(chain.ainvoke("prompt"))
        self.assertEqual(a.calls, 1)

    def test_mixed_errors_keep_original(self):
        a = FakeModel("a", raises(HttpError("rate limit", 429)))
        b = FakeModel("b", raises(TimeoutError("timed out")))
        chain = FallbackLLM([a, b], role="generator").with_structured_output(dict)
        with self.assertRaises(TimeoutError):
            run(chain.ainvoke("prompt"))
        self.assertIsNone(exhausted_message())

    def test_fallback_success_is_not_exhaustion(self):
        a = FakeModel("a", raises(HttpError("rate limit", 429)))
        b = FakeModel("b", lambda: {"ok": True})
        chain = FallbackLLM([a, b], role="generator").with_structured_output(dict)
        self.assertEqual(run(chain.ainvoke("prompt")), {"ok": True})
        self.assertIsNone(exhausted_message())

    def test_solver_exhaustion_does_not_block_generation(self):
        a = FakeModel("a", raises(HttpError("rate limit", 429)))
        chain = FallbackLLM([a], role="solver").with_structured_output(dict)
        with self.assertRaises(LLMLimitExhaustedError):
            run(chain.ainvoke("prompt"))
        self.assertIsNone(exhausted_message())


if __name__ == "__main__":
    unittest.main()
