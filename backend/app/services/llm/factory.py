"""Фабрика LLM-клієнтів: Groq як основний провайдер і резервні (Gemini, Cerebras, OpenRouter),
перемикання між ними з circuit breaker та облік бюджету токенів Groq."""
from __future__ import annotations

import logging
import math
import re
import time
from functools import lru_cache
from typing import Any, Literal

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_groq import ChatGroq

from app.core.config import get_settings
from app.services.llm.token_budget import TokenBudget

logger = logging.getLogger(__name__)

AgentRole = Literal["generator", "critic", "solver"]


@lru_cache
def _rate_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(
        requests_per_second=get_settings().LLM_REQUESTS_PER_SECOND,
        check_every_n_seconds=0.1,
        max_bucket_size=2,
    )


# --- Circuit breaker: модель, що щойно впала, пробуємо останньою, доки не мине пауза ---
DEFAULT_COOLDOWN_SECONDS = 90.0
MIN_COOLDOWN_SECONDS = 20.0
MAX_COOLDOWN_SECONDS = 20 * 60.0

_cooldown_until: dict[str, float] = {}

_RETRY_MIN_SEC_RE = re.compile(r"(\d+)\s*m\s*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
_RETRY_SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*s(?:econds)?\b", re.IGNORECASE)


def _model_key(model: BaseChatModel) -> str:
    name = getattr(model, "model_name", None) or getattr(model, "model", "?")
    return f"{type(model).__name__}:{name}"


def _parse_retry_seconds(message: str) -> float | None:
    m = _RETRY_MIN_SEC_RE.search(message)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = _RETRY_SEC_RE.search(message)
    if m:
        return float(m.group(1))
    return None


def _mark_failed(key: str, exc: Exception) -> None:
    hint = _parse_retry_seconds(str(exc))
    cooldown = DEFAULT_COOLDOWN_SECONDS if hint is None else hint
    cooldown = max(MIN_COOLDOWN_SECONDS, min(MAX_COOLDOWN_SECONDS, cooldown))
    _cooldown_until[key] = time.monotonic() + cooldown
    logger.warning("Модель %s недоступна, відкладено на %.0f с: %s", key, cooldown, exc)


def _mark_ok(key: str) -> None:
    _cooldown_until.pop(key, None)


def _is_cooling_down(key: str) -> bool:
    return time.monotonic() < _cooldown_until.get(key, 0.0)


# --- Вичерпання лімітів: усі моделі ролі відповіли помилкою ліміту ---
_LIMIT_MARKERS = (
    "429", "402", "rate limit", "rate_limit", "ratelimit", "quota", "resource_exhausted",
    "resource has been exhausted", "tokens per day", "payment required", "insufficient",
)
_exhausted_until: dict[str, float] = {}


class LLMLimitExhaustedError(RuntimeError):
    """Ліміти запитів вичерпано на всіх доступних моделях."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(limit_message(retry_after))


def limit_message(seconds: float) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    return (f"Ліміт запитів до ШІ вичерпано на всіх доступних моделях. "
            f"Спробуйте приблизно через {minutes} хв.")


def _is_limit_error(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in (402, 429):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(m in text for m in _LIMIT_MARKERS)


def exhausted_message(roles: tuple[str, ...] = ("generator", "critic")) -> str | None:
    """Повідомлення для користувача, якщо ліміти потрібних ролей зараз вичерпано."""
    now = time.monotonic()
    remaining = max((_exhausted_until.get(r, 0.0) - now for r in roles), default=0.0)
    return limit_message(remaining) if remaining > 0 else None


# --- Бюджет токенів Groq (ліміт рахується окремо для кожної моделі) ---
@lru_cache
def _groq_budget(model: str) -> TokenBudget:
    s = get_settings()
    return TokenBudget(s.GROQ_TOKENS_PER_MINUTE, s.GROQ_MAX_COMPLETION_TOKENS)


class _UsageCapture(BaseCallbackHandler):
    """Забирає фактичну витрату токенів з відповіді моделі."""

    run_inline = True

    def __init__(self) -> None:
        self.input: int | None = None
        self.total: int | None = None

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for gens in response.generations:
            for gen in gens:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if usage:
                    self.input = usage.get("input_tokens")
                    self.total = usage.get("total_tokens")
                    return
        token_usage = (response.llm_output or {}).get("token_usage") or {}
        self.input = token_usage.get("prompt_tokens")
        self.total = token_usage.get("total_tokens")


def _prompt_chars(value: Any) -> int:
    to_string = getattr(value, "to_string", None)
    return len(to_string() if callable(to_string) else str(value))


def model_name(role: AgentRole) -> str:
    s = get_settings()
    return {
        "generator": s.LLM_GENERATOR_MODEL,
        "critic": s.LLM_CRITIC_MODEL,
        "solver": s.LLM_SOLVER_MODEL,
    }[role]


def _temperature(role: AgentRole) -> float:
    s = get_settings()
    return s.LLM_GENERATOR_TEMPERATURE if role == "generator" else 0.0


def _groq(role: AgentRole) -> BaseChatModel:
    s = get_settings()
    return ChatGroq(
        model=model_name(role),
        temperature=_temperature(role),
        api_key=s.GROQ_API_KEY,
        max_tokens=s.GROQ_MAX_COMPLETION_TOKENS,
        max_retries=3,
        timeout=60,
        rate_limiter=_rate_limiter(),
    )


def _gemini(role: AgentRole) -> list[BaseChatModel]:
    s = get_settings()
    if not s.GOOGLE_API_KEY:
        return []
    from langchain_google_genai import ChatGoogleGenerativeAI

    return [ChatGoogleGenerativeAI(
        model=s.LLM_GEMINI_MODEL,
        temperature=_temperature(role),
        google_api_key=s.GOOGLE_API_KEY,
        max_retries=2,
        timeout=60,
    )]


def _cerebras(role: AgentRole) -> list[BaseChatModel]:
    s = get_settings()
    if not s.CEREBRAS_API_KEY:
        return []
    from langchain_cerebras import ChatCerebras

    return [ChatCerebras(
        model=s.LLM_CEREBRAS_MODEL,
        temperature=_temperature(role),
        api_key=s.CEREBRAS_API_KEY,
        max_retries=2,
        timeout=60,
    )]


def _openrouter(role: AgentRole) -> list[BaseChatModel]:
    """Кілька безкоштовних моделей OpenRouter — останній рівень резерву."""
    s = get_settings()
    if not s.OPENROUTER_API_KEY:
        return []
    from langchain_openai import ChatOpenAI

    names = [m.strip() for m in s.LLM_OPENROUTER_MODELS.split(",") if m.strip()]
    return [
        ChatOpenAI(
            model=name,
            temperature=_temperature(role),
            api_key=s.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            max_retries=1,
            timeout=60,
        )
        for name in names
    ]


# Порядок пріоритету резервних провайдерів після Groq
_FALLBACK_BUILDERS = (_gemini, _cerebras, _openrouter)


class FallbackLLM:
    """Обгортка над кількома моделями з тим самим інтерфейсом `with_structured_output`:
    запит іде першій доступній моделі, при помилці — наступній."""

    def __init__(self, models: list[BaseChatModel], role: str = "generator") -> None:
        if not models:
            raise RuntimeError("Потрібна хоча б одна модель LLM (чи задано GROQ_API_KEY?)")
        self.role = role
        self.models = models
        self.keys = [_model_key(m) for m in models]
        self.budgets = [_groq_budget(m.model_name) if isinstance(m, ChatGroq) else None for m in models]

    def _priority_order(self) -> list[int]:
        # Спершу доступні моделі, потім ті, що на паузі, — від найближчого відновлення
        idx = range(len(self.models))
        healthy = [i for i in idx if not _is_cooling_down(self.keys[i])]
        cooling = sorted(
            (i for i in idx if _is_cooling_down(self.keys[i])),
            key=lambda i: _cooldown_until.get(self.keys[i], 0.0),
        )
        return healthy + cooling

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        chains = [m.with_structured_output(schema, **kwargs) for m in self.models]

        async def _call(input: Any) -> Any:
            remaining = _exhausted_until.get(self.role, 0.0) - time.monotonic()
            if remaining > 0:
                raise LLMLimitExhaustedError(remaining)
            last_exc: Exception | None = None
            only_limits = True
            for i in self._priority_order():
                key = self.keys[i]
                budget = self.budgets[i]
                reserved = 0
                chars = _prompt_chars(input)
                if budget is not None:
                    reserved = budget.reservation(chars)
                    waited = await budget.acquire(reserved)
                    if waited >= 1:
                        logger.info("Модель %s: очікування бюджету токенів %.1f с", key, waited)
                usage = _UsageCapture()
                try:
                    result = await chains[i].ainvoke(input, config={"callbacks": [usage]})
                except Exception as exc:  # noqa: BLE001
                    if budget is not None:
                        budget.refund(reserved)
                    _mark_failed(key, exc)
                    only_limits = only_limits and _is_limit_error(exc)
                    last_exc = exc
                    continue
                if budget is not None and usage.total is not None:
                    logger.debug("Модель %s: резерв %d, фактично %s/%d токенів", key, reserved, usage.input, usage.total)
                    budget.settle(chars, reserved, usage.input, usage.total)
                _mark_ok(key)
                _exhausted_until.pop(self.role, None)
                return result
            assert last_exc is not None
            if only_limits:
                now = time.monotonic()
                retry = min(_cooldown_until.get(k, now) for k in self.keys) - now
                retry = max(MIN_COOLDOWN_SECONDS, retry)
                _exhausted_until[self.role] = now + retry
                logger.warning("Роль %s: ліміти вичерпано на всіх моделях, пауза %.0f с", self.role, retry)
                raise LLMLimitExhaustedError(retry) from last_exc
            raise last_exc

        return RunnableLambda(_call)


@lru_cache
def get_llm(role: AgentRole) -> FallbackLLM:
    s = get_settings()
    if not s.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY не задано в .env")
    models: list[BaseChatModel] = [_groq(role)]
    for build in _FALLBACK_BUILDERS:
        models.extend(build(role))
    return FallbackLLM(models, role)
