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

_FALSE_PREFIXES = ("false", "неправ", "невір", "хиб", "неістин", "ні")
_TRUE_PREFIXES = ("true", "правд", "правил", "вірн", "істин", "так")
_UK_LABELS = {True: "Правда", False: "Неправда"}


def true_false_kind(text: str) -> bool | None:
    key = text.strip().lower()
    if key.startswith(_FALSE_PREFIXES):
        return False
    if key.startswith(_TRUE_PREFIXES):
        return True
    return None


def true_false_labels(texts: list[str], language: str) -> list[str]:
    """Однакові мітки «Правда / Неправда» незалежно від слів, які обрала модель."""
    texts = [t.strip() for t in texts]
    if language != "uk" or len(texts) != 2:
        return texts
    kinds = [true_false_kind(t) for t in texts]
    if kinds.count(None) == 1:
        known = next(k for k in kinds if k is not None)
        kinds = [k if k is not None else not known for k in kinds]
    if None in kinds or kinds[0] == kinds[1]:
        return texts
    return [_UK_LABELS[k] for k in kinds]


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
    texts = [o.text for o in options]
    if is_true_false:
        texts = true_false_labels(texts, spec.language)
    question.options = [
        AnswerOption(
            position=i,
            text=texts[i].strip(),
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
