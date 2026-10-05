"""Ручне редагування, затвердження, видалення та ШІ-трансформація питань.

Питання, на яке вже відповідали студенти, не змінюється, а отримує нову версію.
"""
import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.api.deps import DbSession, Teacher, get_owned_question, get_owned_test
from app.models import AnswerOption, Question
from app.models.enums import QuestionOrigin, QuestionStatus
from app.schemas.test import (
    QuestionCreate, QuestionDetail, QuestionOut, QuestionUpdate, ReorderRequest, TransformRequest,
    _validate_options,
)
from app.services.generation.pipeline import GenerationFailedError
from app.services.generation.service import next_position, question_has_answers, transform_question
from app.services.llm.factory import exhausted_message

router = APIRouter(tags=["questions"])
logger = logging.getLogger(__name__)


def _options_from(data) -> list[AnswerOption]:
    return [
        AnswerOption(
            position=i, text=o.text.strip(), is_correct=o.is_correct,
            distractor_rationale=o.distractor_rationale,
        )
        for i, o in enumerate(data)
    ]


async def _reload(db, question_id: int) -> Question:
    """Перечитує питання з варіантами та журналом перевірки."""
    from sqlalchemy.orm import selectinload

    db.expire_all()
    return await db.scalar(
        select(Question).where(Question.id == question_id).options(selectinload(Question.verifications))
    )


@router.get("/tests/{test_id}/questions", response_model=list[QuestionOut])
async def list_questions(
    test_id: int, db: DbSession, user: Teacher,
    status_filter: QuestionStatus | None = None, include_archived: bool = False,
) -> list[Question]:
    test = await get_owned_test(db, test_id, user)
    query = select(Question).where(Question.test_id == test.id)
    if status_filter is not None:
        query = query.where(Question.status == status_filter)
    elif not include_archived:
        query = query.where(Question.status != QuestionStatus.ARCHIVED)
    return list(await db.scalars(query.order_by(Question.position, Question.id)))


@router.post("/tests/{test_id}/questions", response_model=QuestionDetail, status_code=status.HTTP_201_CREATED)
async def create_question(test_id: int, data: QuestionCreate, db: DbSession, user: Teacher) -> Question:
    test = await get_owned_test(db, test_id, user)
    question = Question(
        test_id=test.id,
        position=await next_position(db, test.id),
        type=data.type,
        text=data.text.strip(),
        explanation=data.explanation,
        difficulty=data.difficulty,
        points=data.points,
        time_limit_sec=data.time_limit_sec,
        status=QuestionStatus.APPROVED,       # створене людиною
        origin=QuestionOrigin.MANUAL,
        generation_attempts=0,
    )
    question.options = _options_from(data.options)
    db.add(question)
    await db.commit()
    return await _reload(db, question.id)


@router.get("/questions/{question_id}", response_model=QuestionDetail)
async def get_question(question_id: int, db: DbSession, user: Teacher) -> Question:
    question, _ = await get_owned_question(db, question_id, user)
    return question


@router.patch("/questions/{question_id}", response_model=QuestionDetail)
async def edit_question(question_id: int, data: QuestionUpdate, db: DbSession, user: Teacher) -> Question:
    question, _ = await get_owned_question(db, question_id, user)
    if question.status == QuestionStatus.ARCHIVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Архівне питання не можна редагувати")

    changes = data.model_dump(exclude_unset=True, exclude={"options"})
    if data.options is not None:
        try:
            _validate_options(question.type, data.options)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None

    content_changed = "text" in changes or data.options is not None

    if content_changed and await question_has_answers(db, question.id):
        # Нова версія, стара — в архів
        target = Question(
            test_id=question.test_id,
            position=question.position,
            type=question.type,
            text=question.text,
            explanation=question.explanation,
            source_quote=question.source_quote,
            difficulty=question.difficulty,
            points=question.points,
            time_limit_sec=question.time_limit_sec,
            source_chunk_ids=list(question.source_chunk_ids or []),
            llm_model=question.llm_model,
            parent_id=question.id,
            version=question.version + 1,
            generation_attempts=0,
        )
        target.options = [
            AnswerOption(position=o.position, text=o.text, is_correct=o.is_correct,
                         distractor_rationale=o.distractor_rationale)
            for o in question.options
        ]
        question.status = QuestionStatus.ARCHIVED
        db.add(target)
    else:
        target = question

    for field, value in changes.items():
        setattr(target, field, value.strip() if isinstance(value, str) else value)
    if data.options is not None:
        target.options = _options_from(data.options)
    if content_changed:
        target.origin = QuestionOrigin.MANUAL
    target.status = QuestionStatus.APPROVED  # правка викладачем = перевірено людиною

    await db.commit()
    return await _reload(db, target.id)


@router.post("/questions/{question_id}/approve", response_model=QuestionOut)
async def approve_question(question_id: int, db: DbSession, user: Teacher) -> Question:
    question, _ = await get_owned_question(db, question_id, user)
    if question.status == QuestionStatus.ARCHIVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Питання в архіві")
    question.status = QuestionStatus.APPROVED
    await db.commit()
    return question


@router.post("/tests/{test_id}/questions/approve-verified")
async def approve_all_verified(test_id: int, db: DbSession, user: Teacher) -> dict[str, int]:
    """Масово затверджує питання, що пройшли перевірку ШІ."""
    test = await get_owned_test(db, test_id, user)
    result = await db.execute(
        update(Question)
        .where(Question.test_id == test.id, Question.status == QuestionStatus.AI_VERIFIED)
        .values(status=QuestionStatus.APPROVED)
    )
    await db.commit()
    return {"approved": result.rowcount or 0}


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: int, db: DbSession, user: Teacher) -> None:
    question, _ = await get_owned_question(db, question_id, user)
    if await question_has_answers(db, question.id):
        question.status = QuestionStatus.ARCHIVED   # історія відповідей потрібна для IRT
    else:
        await db.execute(
            update(Question).where(Question.parent_id == question.id).values(parent_id=None)
        )
        await db.delete(question)
    await db.commit()


@router.post("/questions/{question_id}/transform", response_model=QuestionDetail)
async def transform(question_id: int, data: TransformRequest, db: DbSession, user: Teacher) -> Question:
    """ШІ-трансформація питання; нова версія проходить повний цикл перевірки."""
    question, test = await get_owned_question(db, question_id, user)
    if question.status == QuestionStatus.ARCHIVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Архівне питання не можна змінювати")
    try:
        new_q = await transform_question(db, question, test, data.action, data.instruction, data.language)
    except (ValueError, GenerationFailedError) as exc:
        await db.rollback()
        limit_msg = exhausted_message()
        if limit_msg:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, limit_msg) from None
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except Exception:
        await db.rollback()
        limit_msg = exhausted_message()
        if limit_msg:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, limit_msg) from None
        logger.exception("Не вдалося трансформувати питання %s", question_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Сервіс ШІ зараз недоступний, спробуйте пізніше") from None
    await db.commit()
    return await _reload(db, new_q.id)


@router.put("/tests/{test_id}/questions/order", response_model=list[QuestionOut])
async def reorder_questions(test_id: int, data: ReorderRequest, db: DbSession, user: Teacher) -> list[Question]:
    test = await get_owned_test(db, test_id, user)
    questions = {
        q.id: q for q in await db.scalars(
            select(Question).where(Question.test_id == test.id, Question.status != QuestionStatus.ARCHIVED)
        )
    }
    if set(data.question_ids) != set(questions):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Список має містити всі активні питання тесту")
    for pos, qid in enumerate(data.question_ids, start=1):
        questions[qid].position = pos
    await db.commit()
    return [questions[qid] for qid in data.question_ids]
