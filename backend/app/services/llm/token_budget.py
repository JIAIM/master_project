"""Бюджет токенів на хвилину для моделі Groq: резерв «промпт + max_tokens» перед
запитом і повернення невикористаного після відповіді (так само рахує Groq).
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

CHARS_PER_TOKEN = 3.0
INITIAL_PROMPT_SCALE = 1.5     
PROMPT_SCALE_EMA_WEIGHT = 0.3


class TokenBudget:
    def __init__(
        self,
        tokens_per_minute: int,
        max_completion_tokens: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.capacity = float(tokens_per_minute)
        self.rate = tokens_per_minute / 60.0
        self.max_completion = max_completion_tokens
        self.available = self.capacity
        self.prompt_scale = INITIAL_PROMPT_SCALE
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock: asyncio.Lock | None = None

    def _refill(self) -> None:
        now = self._clock()
        self.available = min(self.capacity, self.available + (now - self._updated) * self.rate)
        self._updated = now

    def reservation(self, prompt_chars: int) -> int:
        """Скільки токенів Groq зарезервує під запит: промпт + max_tokens."""
        return int(prompt_chars / CHARS_PER_TOKEN * self.prompt_scale) + self.max_completion

    async def acquire(self, tokens: int) -> float:
        """Чекає, доки в бюджеті вистачить токенів, і списує їх. Повертає час очікування."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        need = min(float(tokens), self.capacity)
        waited = 0.0
        async with self._lock:
            while True:
                self._refill()
                if self.available >= need:
                    self.available -= need
                    return waited
                delay = (need - self.available) / self.rate
                await self._sleep(delay)
                waited += delay

    def refund(self, tokens: int) -> None:
        """Запит не пройшов — резерв повертається."""
        self._refill()
        self.available = min(self.capacity, self.available + tokens)

    def settle(self, prompt_chars: int, reserved: int, actual_input: int | None, actual_total: int) -> None:
        """Повертає невикористану частину резерву й уточнює оцінку промпту."""
        self._refill()
        self.available = min(self.capacity, self.available + (reserved - actual_total))
        if actual_input and prompt_chars:
            ratio = actual_input / (prompt_chars / CHARS_PER_TOKEN)
            self.prompt_scale += PROMPT_SCALE_EMA_WEIGHT * (ratio - self.prompt_scale)
