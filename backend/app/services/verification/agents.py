"""Рівень 2 перевірки: агенти Розв'язувач і Критик.

Рішення «прийнято/відхилено» ухвалює код за порогами, а не сама LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import Runnable

from app.services.generation.formatting import format_question_block, keyed_numbers
from app.services.generation.generator import GenerationSpec
from app.services.generation.prompts import CRITIC_PROMPT, SOLVER_PROMPT
from app.services.generation.schemas import CriticReport, LLMQuestion, SolverAnswer


class IndependentSolver:
    def __init__(self, llm) -> None:
        self._chain: Runnable = (
            SOLVER_PROMPT | llm.with_structured_output(SolverAnswer)
        ).with_retry(stop_after_attempt=2, wait_exponential_jitter=True)

    async def solve(self, context: str, question: LLMQuestion) -> SolverAnswer:
        result = await self._chain.ainvoke({
            "context": context,
            "question_block": format_question_block(question),
        })
        return result if isinstance(result, SolverAnswer) else SolverAnswer.model_validate(result)


@dataclass(frozen=True)
class CriticThresholds:
    min_grounding: float = 0.7
    min_distractor_quality: float = 0.6
    min_clarity: float = 0.6


class QuestionCritic:
    def __init__(self, llm, thresholds: CriticThresholds) -> None:
        self.thresholds = thresholds
        self._chain: Runnable = (
            CRITIC_PROMPT | llm.with_structured_output(CriticReport)
        ).with_retry(stop_after_attempt=2, wait_exponential_jitter=True)

    async def review(
        self,
        context: str,
        question: LLMQuestion,
        spec: GenerationSpec,
        solver: SolverAnswer | None = None,
    ) -> CriticReport:
        solver_block = ""
        if solver is not None:
            agrees = sorted(solver.chosen_options) == keyed_numbers(question)
            solver_block = (
                f"\nINDEPENDENT SOLVER (did not see the key) chose: {solver.chosen_options} "
                f"(confidence {solver.confidence:.2f}). Reasoning: {solver.reasoning}\n"
            )
            if not agrees:
                solver_block += (
                    "The solver DISAGREES with the key. Decide whether the key is wrong, "
                    "the item is ambiguous, or the solver simply erred, and reflect it in your scores.\n"
                )

        result = await self._chain.ainvoke({
            "context": context,
            "language": spec.language_name,
            "difficulty": spec.difficulty,
            "bloom": spec.bloom,
            "question_type": spec.question_type,
            "question_block": format_question_block(question),
            "keyed": ", ".join(map(str, keyed_numbers(question))),
            "explanation": question.explanation,
            "evidence_quote": question.evidence_quote,
            "solver_block": solver_block,
        })
        return result if isinstance(result, CriticReport) else CriticReport.model_validate(result)

    def decide(self, report: CriticReport) -> tuple[bool, list[str]]:
        t = self.thresholds
        problems: list[str] = []
        if not report.key_is_correct:
            problems.append("Критик: позначена правильна відповідь насправді неправильна")
        if not report.unambiguous:
            problems.append("Критик: питання неоднозначне — хибний варіант можна обґрунтувати як правильний")
        if report.grounding_score < t.min_grounding:
            problems.append(f"Критик: відповідь слабко підтверджена матеріалом ({report.grounding_score:.2f})")
        if report.distractor_quality < t.min_distractor_quality:
            problems.append(f"Критик: слабкі хибні варіанти ({report.distractor_quality:.2f})")
        if report.clarity < t.min_clarity:
            problems.append(f"Критик: недостатньо чітке формулювання ({report.clarity:.2f})")
        # difficulty_match не блокує, але потрапляє в зауваження
        if problems:
            problems.extend(report.issues)
            if report.suggestions:
                problems.append(f"Рекомендація: {report.suggestions}")
        return (not problems), problems
