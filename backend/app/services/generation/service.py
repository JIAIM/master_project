"""Генерація тестів: фонові задачі, ШІ-трансформація питань, відновлення після перезапуску."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import GenerationJob, Material, Question, StudentAnswer, Test
from app.models.enums import (
    Difficulty, JobStatus, MaterialStatus, QuestionOrigin, QuestionStatus,
)
from app.services.generation.context import build_contexts, plan_difficulties
from app.services.generation.generator import GenerationSpec
from app.services.generation.persistence import build_question, save_question
from app.services.generation.pipeline import GenerationFailedError, QuestionPipeline, get_pipeline
from app.services.generation.prompts import TRANSFORM_INSTRUCTIONS
from app.services.generation.schemas import LLMOption, LLMQuestion
from app.services.llm.factory import exhausted_message
from app.services.rag.vectorstore import Chunk, get_vector_store

logger = logging.getLogger(__name__)

DIFFICULTY_ORDER = [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def active_stems(db: AsyncSession, test_id: int) -> list[str]:
    rows = await db.scalars(
        select(Question.text)
        .where(Question.test_id == test_id, Question.status != QuestionStatus.ARCHIVED)
        .order_by(Question.position)
    )
    return list(rows)


async def next_position(db: AsyncSession, test_id: int) -> int:
    current = await db.scalar(select(func.max(Question.position)).where(Question.test_id == test_id))
    return (current or 0) + 1


async def question_has_answers(db: AsyncSession, question_id: int) -> bool:
    return bool(await db.scalar(
        select(select(StudentAnswer.id).where(StudentAnswer.question_id == question_id).exists())
    ))


# --- Фонова генерація ---
@dataclass
class _TaskOutcome:
    index: int
    spec: GenerationSpec
    result: object | None   # PipelineResult у разі успіху
    error: Exception | None


async def _run_one(pipeline: QuestionPipeline, index: int, chunks: list[Chunk],
                    spec: GenerationSpec, stems_snapshot: list[str]) -> _TaskOutcome:
    """Запуск пайплайна для одного питання (без звернень до БД)."""
    try:
        result = await pipeline.run(chunks, spec, stems_snapshot)
    except GenerationFailedError as exc:
        return _TaskOutcome(index, spec, None, exc)
    return _TaskOutcome(index, spec, result, None)


async def run_generation_job(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(GenerationJob, job_id)
        if job is None:
            return
        test = await db.scalar(
            select(Test).where(Test.id == job.test_id).options(selectinload(Test.materials))
        )
        job.status = JobStatus.RUNNING
        job.started_at = _now()
        await db.commit()

        try:
            params = job.params
            n: int = params["num_questions"]
            types: list[str] = params["question_types"]
            language: str = params.get("language", "uk")
            material_ids = [m.id for m in test.materials if m.status == MaterialStatus.INDEXED]

            contexts = await build_contexts(get_vector_store(), material_ids, n, params.get("topic"))
            difficulties = plan_difficulties(n, params["difficulty"])
            stems = await active_stems(db, test.id)
            position = await next_position(db, test.id)
            pipeline = get_pipeline()
            batch_size = max(1, get_settings().GENERATION_CONCURRENCY)

            # Питання генеруються паралельними батчами; між батчами оновлюємо stems проти дублів
            for batch_start in range(0, n, batch_size):
                limit_msg = exhausted_message()
                if limit_msg:
                    logger.warning("Задача %s зупинена: ліміти ШІ вичерпано", job.id)
                    job.status = JobStatus.FAILED
                    saved = job.verified_count + job.rejected_count
                    job.error = f"Генерацію зупинено. {limit_msg}" + (
                        f" Уже створені питання ({saved}) збережено." if saved else "")
                    break
                batch = list(enumerate(contexts))[batch_start:batch_start + batch_size]
                stems_snapshot = list(stems)
                tasks = [
                    asyncio.create_task(_run_one(
                        pipeline, i, chunks,
                        GenerationSpec(difficulty=difficulties[i], question_type=types[i % len(types)], language=language),
                        stems_snapshot,
                    ))
                    for i, chunks in batch
                ]
                for coro in asyncio.as_completed(tasks):
                    outcome = await coro
                    if outcome.error is not None:
                        logger.warning("Задача %s: не вдалося згенерувати питання %s: %s", job.id, outcome.index + 1, outcome.error)
                        job.failed_count += 1
                    else:
                        question = build_question(outcome.result, outcome.spec, test_id=test.id, position=position)
                        await save_question(db, question)
                        stems.append(question.text)
                        position += 1
                        if outcome.result.passed:
                            job.verified_count += 1
                        else:
                            job.rejected_count += 1
                    job.completed += 1
                    await db.commit()  # прогрес видно одразу
            else:
                job.status = JobStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001
            logger.exception("Задача генерації %s завершилася з помилкою", job_id)
            await db.rollback()
            job = await db.get(GenerationJob, job_id)
            job.status = JobStatus.FAILED
            job.error = str(exc)[:2000]

        job.finished_at = _now()
        await db.commit()


async def recover_interrupted_work() -> None:
    """Під час старту позначає задачі, перервані перезапуском, як невдалі."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(GenerationJob)
            .where(GenerationJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
            .values(status=JobStatus.FAILED, error="Перервано перезапуском сервера", finished_at=_now())
        )
        await db.execute(
            update(Material)
            .where(Material.status == MaterialStatus.PROCESSING)
            .values(status=MaterialStatus.FAILED, error_message="Перервано перезапуском сервера")
        )
        await db.commit()


# --- ШІ-трансформація питань ---
def question_to_llm(q: Question) -> LLMQuestion:
    return LLMQuestion(
        question=q.text,
        options=[
            LLMOption(text=o.text, is_correct=o.is_correct, rationale=o.distractor_rationale or "")
            for o in q.options
        ],
        explanation=q.explanation or "",
        evidence_quote=q.source_quote or "",
        bloom_level="",
    )


def shifted_difficulty(current: Difficulty, action: str) -> Difficulty:
    idx = DIFFICULTY_ORDER.index(current)
    if action == "simplify":
        idx = max(0, idx - 1)
    elif action == "complicate":
        idx = min(len(DIFFICULTY_ORDER) - 1, idx + 1)
    return DIFFICULTY_ORDER[idx]


async def transform_question(
    db: AsyncSession,
    question: Question,
    test: Test,
    action: str,
    extra_instruction: str | None,
    language: str,
) -> Question:
    """Створює нову версію питання (стара архівується); вона проходить повну перевірку."""
    store = get_vector_store()
    chunks = await store.get_by_ids(question.source_chunk_ids or [])
    if not chunks:
        # Питання створене вручну — шукаємо контекст за його текстом
        material_ids = [m.id for m in test.materials]
        chunks = await store.search(question.text, material_ids, k=2) if material_ids else []
    if not chunks:
        raise ValueError("Не знайдено вихідний матеріал для цього питання")

    instruction = TRANSFORM_INSTRUCTIONS[action]
    if extra_instruction:
        instruction += f" Additional teacher request: {extra_instruction}"

    spec = GenerationSpec(
        difficulty=shifted_difficulty(question.difficulty, action).value,
        question_type=question.type.value,
        language=language,
    )
    stems = [s for s in await active_stems(db, test.id) if s != question.text]
    result = await get_pipeline().run(
        chunks, spec, stems, base=question_to_llm(question), instruction=instruction
    )

    new_q = build_question(
        result, spec,
        test_id=test.id, position=question.position,
        origin=QuestionOrigin.AI_MODIFIED, parent=question,
    )
    question.status = QuestionStatus.ARCHIVED
    await save_question(db, new_q)
    return new_q
