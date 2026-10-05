"""Збереження результату пайплайна в БД: питання, варіанти, журнал перевірки."""
from __future__ import annotations

import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnswerOption, Question, QuestionVerification
from app.models.enums import (
    Difficulty, QuestionOrigin, QuestionStatus, QuestionType, VerificationVerdict,
)
from app.services.generation.generator import GenerationSpec
from app.services.generation.pipeline import PipelineResult, pipeline_models

_TRUE_WORDS = {"true", "правда", "так", "вірно", "істина"}
_FALSE_WORDS = {"false", "неправда", "ні", "невірно", "хибно", "хиба"}


def true_false_label(text: str, language: str) -> str:
    if language != "uk":
        return text
    key = text.strip().lower().rstrip(".!")
    if key in _TRUE_WORDS:
        return "Правда"
    if key in _FALSE_WORDS:
        return "Неправда"
    return text


def build_question(
    result: PipelineResult,
    spec: GenerationSpec,
    *,
    test_id: int,
    position: int,
    origin: QuestionOrigin = QuestionOrigin.AI_GENERATED,
    parent: Question | None = None,
) -> Question:
    draft = result.question
    models = pipeline_models()

    options = list(draft.options)
    is_true_false = spec.question_type == QuestionType.TRUE_FALSE.value
    if not is_true_false:
        random.shuffle(options)

    question = Question(
        test_id=test_id,
        position=position,
        type=QuestionType(spec.question_type),
        text=draft.question.strip(),
        explanation=draft.explanation.strip() or None,
        source_quote=draft.evidence_quote.strip() or None,
        difficulty=Difficulty(spec.difficulty),
        status=QuestionStatus.AI_VERIFIED if result.passed else QuestionStatus.AI_REJECTED,
        origin=origin,
        source_chunk_ids=[c.id for c in result.chunks],
        llm_model=models["generator"],
        generation_attempts=len(result.attempts),
        parent_id=parent.id if parent else None,
        version=(parent.version + 1) if parent else 1,
        points=parent.points if parent else 1.0,
        time_limit_sec=parent.time_limit_sec if parent else None,
    )
    question.options = [
        AnswerOption(
            position=i,
            text=true_false_label(o.text, spec.language) if is_true_false else o.text.strip(),
            is_correct=o.is_correct,
            distractor_rationale=o.rationale.strip() or None,
        )
        for i, o in enumerate(options)
    ]
    question.verifications = [
        QuestionVerification(
            attempt=a.attempt,
            verdict=VerificationVerdict.PASSED if a.passed else VerificationVerdict.FAILED,
            scores={
                "stage": a.stage,
                "critic": a.critic,
                "solver": a.solver,
                "solver_agrees": a.solver_agrees,
                "rule_issues": a.rule_issues,
            },
            critique="\n".join(a.issues) or None,
            critic_model=models["critic"] if a.stage == "critic" else None,
        )
        for a in result.attempts
    ]
    return question


async def save_question(db: AsyncSession, question: Question) -> Question:
    db.add(question)
    await db.flush()
    return question
