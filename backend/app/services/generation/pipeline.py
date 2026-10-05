"""Багаторівнева перевірка питання: Генератор → Правила → Розв'язувач → Критик.
У разі провалу зауваження повертаються Генератору (до N спроб).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.services.generation.formatting import format_context
from app.services.generation.generator import GenerationSpec, QuestionGenerator
from app.services.generation.schemas import LLMQuestion
from app.services.llm.factory import get_llm, model_name
from app.services.rag.vectorstore import Chunk
from app.services.verification import rules
from app.services.verification.agents import CriticThresholds, IndependentSolver, QuestionCritic

logger = logging.getLogger(__name__)


class GenerationFailedError(RuntimeError):
    """LLM не повернула жодної валідної чернетки за всі спроби."""


@dataclass
class AttemptRecord:
    attempt: int
    passed: bool
    stage: str                                   
    issues: list[str] = field(default_factory=list)
    rule_issues: list[dict[str, Any]] = field(default_factory=list)
    critic: dict[str, Any] | None = None
    solver: dict[str, Any] | None = None
    solver_agrees: bool | None = None


@dataclass
class PipelineResult:
    question: LLMQuestion
    passed: bool
    attempts: list[AttemptRecord]
    chunks: list[Chunk]


class QuestionPipeline:
    def __init__(
        self,
        generator: QuestionGenerator,
        critic: QuestionCritic,
        solver: IndependentSolver | None,
        max_attempts: int,
    ) -> None:
        self.generator = generator
        self.critic = critic
        self.solver = solver
        self.max_attempts = max_attempts

    async def run(
        self,
        chunks: list[Chunk],
        spec: GenerationSpec,
        existing_stems: list[str],
        *,
        base: LLMQuestion | None = None,
        instruction: str | None = None,
    ) -> PipelineResult:
        context = format_context(chunks)
        draft: LLMQuestion | None = None
        previous = base
        feedback: list[str] | None = None
        attempts: list[AttemptRecord] = []

        for attempt in range(1, self.max_attempts + 1):
            # --- 1. Генерація ---
            try:
                draft = await self.generator.generate(
                    context=context, spec=spec, existing_stems=existing_stems,
                    previous=previous, feedback=feedback, instruction=instruction,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Генератор: помилка на спробі %s: %s", attempt, exc)
                attempts.append(AttemptRecord(attempt, False, "llm_error", [f"Помилка генерації: {exc}"]))
                continue

            # --- 2. Детерміновані правила ---
            rule_issues = rules.check_question(
                draft, question_type=spec.question_type,
                expected_options=spec.num_options, context=context,
            )
            blocking = rules.blocking(rule_issues)
            if blocking:
                msgs = [i.message for i in blocking]
                attempts.append(AttemptRecord(
                    attempt, False, "rules", msgs, [asdict(i) for i in rule_issues],
                ))
                previous, feedback = draft, msgs
                continue  # Критика не викликаємо — економимо ліміт API

            # --- 3. Незалежний Розв'язувач (опційно) ---
            solver_answer = None
            solver_agrees = None
            if self.solver is not None:
                try:
                    solver_answer = await self.solver.solve(context, draft)
                    keyed = [i for i, o in enumerate(draft.options, start=1) if o.is_correct]
                    solver_agrees = sorted(solver_answer.chosen_options) == keyed
                except Exception as exc:  # noqa: BLE001 — Розв'язувач не обов'язковий
                    logger.warning("Розв'язувач: помилка: %s", exc)

            # --- 4. Критик ---
            try:
                report = await self.critic.review(context, draft, spec, solver_answer)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Критик: помилка на спробі %s: %s", attempt, exc)
                attempts.append(AttemptRecord(attempt, False, "llm_error", [f"Помилка Критика: {exc}"]))
                previous, feedback = draft, None
                continue

            passed, problems = self.critic.decide(report)
            attempts.append(AttemptRecord(
                attempt=attempt,
                passed=passed,
                stage="critic",
                issues=problems,
                rule_issues=[asdict(i) for i in rule_issues],
                critic=report.model_dump(),
                solver=solver_answer.model_dump() if solver_answer else None,
                solver_agrees=solver_agrees,
            ))
            if passed:
                return PipelineResult(draft, True, attempts, chunks)
            previous, feedback = draft, problems

        if draft is None:
            raise GenerationFailedError("; ".join(i for a in attempts for i in a.issues))
        return PipelineResult(draft, False, attempts, chunks)


@lru_cache
def get_pipeline() -> QuestionPipeline:
    s = get_settings()
    return QuestionPipeline(
        generator=QuestionGenerator(get_llm("generator")),
        critic=QuestionCritic(
            get_llm("critic"),
            CriticThresholds(
                min_grounding=s.CRITIC_MIN_GROUNDING,
                min_distractor_quality=s.CRITIC_MIN_DISTRACTOR_QUALITY,
                min_clarity=s.CRITIC_MIN_CLARITY,
            ),
        ),
        solver=IndependentSolver(get_llm("solver")) if s.ENABLE_SOLVER else None,
        max_attempts=s.MAX_VERIFICATION_ATTEMPTS,
    )


def pipeline_models() -> dict[str, str]:
    return {r: model_name(r) for r in ("generator", "critic", "solver")}
