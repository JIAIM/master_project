"""Самостійне проходження тесту: збереження відповідей, завершення й оцінювання, прокторинг."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProctoringEvent, Question, SessionParticipant, StudentAnswer, StudentResult, TestSession,
)
from app.models.enums import ProctoringEventType, QuestionType, SessionStatus
from app.services.testing.grading import GradedItem, grade

ANSWER_GRACE = timedelta(seconds=10)     # запас на мережеву затримку останньої відповіді
PROCTOR_REPEAT_WINDOW = timedelta(seconds=2)
ATTENTION_RESTORED = "attention_restored"
LASTING_EVENTS = {                        # події, після яких буває «повернення уваги»
    ProctoringEventType.DISTRACTION_WARNING, ProctoringEventType.FACE_NOT_DETECTED,
    ProctoringEventType.MULTIPLE_FACES, ProctoringEventType.TAB_HIDDEN,
}


class PlayError(Exception):
    """Помилка, яку можна показати студенту без змін."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Питання сесії ---
async def session_questions(db: AsyncSession, session: TestSession) -> list[Question]:
    """Питання, зафіксовані під час створення сесії."""
    ids: list[int] = (session.settings or {}).get("question_ids", [])
    if not ids:
        return []
    by_id = {q.id: q for q in await db.scalars(select(Question).where(Question.id.in_(ids)))}
    return [by_id[i] for i in ids if i in by_id]


def ordered_options(question: Question, participant_id: int) -> list:
    """Варіанти перемішані для кожного студента по-своєму (стабільно між перезавантаженнями)."""
    options = sorted(question.options, key=lambda o: o.position)
    if question.type != QuestionType.TRUE_FALSE:
        random.Random(participant_id * 100_003 + question.id).shuffle(options)
    return options


def correct_ids(question: Question) -> list[int]:
    return [o.id for o in question.options if o.is_correct]


# --- Час ---
def deadline(session: TestSession, participant: SessionParticipant) -> datetime | None:
    minutes = (session.settings or {}).get("time_limit_min")
    return participant.joined_at + timedelta(minutes=minutes) if minutes else None


def is_expired(session: TestSession, participant: SessionParticipant, now: datetime | None = None) -> bool:
    d = deadline(session, participant)
    return d is not None and (now or utcnow()) > d + ANSWER_GRACE


async def is_finished(db: AsyncSession, participant_id: int) -> bool:
    return await db.scalar(select(StudentResult.id).where(StudentResult.participant_id == participant_id)) is not None


# --- Відповіді ---
async def save_answer(
    db: AsyncSession, session: TestSession, participant: SessionParticipant,
    question_id: int, option_ids: list[int],
) -> None:
    if session.status != SessionStatus.RUNNING:
        raise PlayError("Сесію закрито викладачем")
    if await is_finished(db, participant.id):
        raise PlayError("Тест уже завершено")
    if is_expired(session, participant):
        await finalize(db, session, participant)
        raise PlayError("Час на тест вичерпано")

    questions = {q.id: q for q in await session_questions(db, session)}
    question = questions.get(question_id)
    if question is None:
        raise PlayError("Такого питання немає в цьому тесті")
    valid = {o.id for o in question.options}
    chosen = sorted(set(option_ids))
    if any(o not in valid for o in chosen):
        raise PlayError("Невідомий варіант відповіді")
    if question.type != QuestionType.MULTIPLE_CHOICE and len(chosen) > 1:
        raise PlayError("У цьому питанні можна обрати лише один варіант")

    if not chosen:
        await db.execute(StudentAnswer.__table__.delete().where(
            StudentAnswer.participant_id == participant.id, StudentAnswer.question_id == question_id))
        await db.commit()
        return

    # Час на питання — від попередньої збереженої відповіді (або від початку тесту)
    last = await db.scalar(select(func.max(StudentAnswer.answered_at))
                           .where(StudentAnswer.participant_id == participant.id))
    since = last or participant.joined_at
    elapsed_ms = max(0, int((utcnow() - since).total_seconds() * 1000))
    is_correct = set(chosen) == set(correct_ids(question))

    stmt = pg_insert(StudentAnswer).values(
        participant_id=participant.id, session_id=session.id, question_id=question_id,
        selected_option_ids=chosen, is_correct=is_correct,
        score=question.points if is_correct else 0.0, response_time_ms=elapsed_ms,
    ).on_conflict_do_update(
        index_elements=["participant_id", "question_id"],
        set_={"selected_option_ids": chosen, "is_correct": is_correct,
              "score": question.points if is_correct else 0.0},
    )
    await db.execute(stmt)
    await db.commit()


async def participant_answers(db: AsyncSession, participant_id: int) -> dict[int, list[int]]:
    rows = await db.execute(select(StudentAnswer.question_id, StudentAnswer.selected_option_ids)
                            .where(StudentAnswer.participant_id == participant_id))
    return {qid: list(opts or []) for qid, opts in rows.all()}


# --- Завершення ---
async def finalize(db: AsyncSession, session: TestSession, participant: SessionParticipant) -> StudentResult:
    """Завершує спробу й рахує бали; повторний виклик повертає вже готовий результат."""
    existing = await db.scalar(select(StudentResult).where(StudentResult.participant_id == participant.id))
    if existing is not None:
        return existing

    questions = await session_questions(db, session)
    answers = await participant_answers(db, participant.id)

    # Питання без відповіді зараховуються як неправильні (потрібно для IRT)
    missing = [q for q in questions if q.id not in answers]
    if missing:
        await db.execute(pg_insert(StudentAnswer).values([
            {"participant_id": participant.id, "session_id": session.id, "question_id": q.id,
             "selected_option_ids": [], "is_correct": False, "score": 0.0, "response_time_ms": None}
            for q in missing
        ]).on_conflict_do_nothing(index_elements=["participant_id", "question_id"]))

    distracted_q = set(await db.scalars(
        select(ProctoringEvent.question_id).where(
            ProctoringEvent.participant_id == participant.id, ProctoringEvent.question_id.is_not(None))))
    if distracted_q:
        await db.execute(update(StudentAnswer).where(
            StudentAnswer.participant_id == participant.id,
            StudentAnswer.question_id.in_(distracted_q)).values(had_distraction=True))

    g = grade([GradedItem(q.id, q.points, tuple(answers.get(q.id, ())), tuple(correct_ids(q)))
               for q in questions])
    distractions = await db.scalar(select(func.count()).select_from(ProctoringEvent)
                                   .where(ProctoringEvent.participant_id == participant.id)) or 0

    await db.execute(pg_insert(StudentResult).values(
        participant_id=participant.id, session_id=session.id, score=g.score, max_score=g.max_score,
        correct_count=g.correct_count, answered_count=g.answered_count, distraction_count=distractions,
    ).on_conflict_do_nothing(index_elements=["participant_id"]))
    await db.execute(update(SessionParticipant).where(SessionParticipant.id == participant.id)
                     .values(is_connected=False, left_at=utcnow()))
    await db.commit()
    return await db.scalar(select(StudentResult).where(StudentResult.participant_id == participant.id))


async def finalize_expired(db: AsyncSession, session: TestSession) -> None:
    """Завершує спроби, у яких минув ліміт часу."""
    if not (session.settings or {}).get("time_limit_min"):
        return
    done = set(await db.scalars(select(StudentResult.participant_id).where(StudentResult.session_id == session.id)))
    now = utcnow()
    for p in await db.scalars(select(SessionParticipant).where(SessionParticipant.session_id == session.id)):
        if p.id not in done and is_expired(session, p, now):
            await finalize(db, session, p)


async def close_session(db: AsyncSession, session: TestSession) -> None:
    """Закриває сесію й завершує всі незавершені спроби."""
    done = set(await db.scalars(select(StudentResult.participant_id).where(StudentResult.session_id == session.id)))
    for p in list(await db.scalars(select(SessionParticipant).where(SessionParticipant.session_id == session.id))):
        if p.id not in done:
            await finalize(db, session, p)
    session.status = SessionStatus.FINISHED
    session.finished_at = utcnow()
    await db.commit()


# --- Прокторинг ---
async def record_proctoring(
    db: AsyncSession, session: TestSession, participant: SessionParticipant,
    event: str, question_id: int | None, duration_ms: int | None,
    client_ts_ms: int | None, details: dict | None,
) -> None:
    if session.status != SessionStatus.RUNNING or await is_finished(db, participant.id):
        return

    if event == ATTENTION_RESTORED:
        if duration_ms:
            last_id = await db.scalar(select(func.max(ProctoringEvent.id)).where(
                ProctoringEvent.participant_id == participant.id, ProctoringEvent.duration_ms.is_(None),
                ProctoringEvent.event_type.in_(LASTING_EVENTS)))
            if last_id:
                await db.execute(update(ProctoringEvent).where(ProctoringEvent.id == last_id)
                                 .values(duration_ms=duration_ms))
                await db.commit()
        return

    try:
        event_type = ProctoringEventType(event)
    except ValueError:
        return
    # Захист від флуду: однакова подія не частіше ніж раз на 2 с
    recent = await db.scalar(select(ProctoringEvent.id).where(
        ProctoringEvent.participant_id == participant.id, ProctoringEvent.event_type == event_type,
        ProctoringEvent.received_at > utcnow() - PROCTOR_REPEAT_WINDOW).limit(1))
    if recent:
        return

    questions = {q.id for q in await session_questions(db, session)}
    db.add(ProctoringEvent(
        participant_id=participant.id, session_id=session.id,
        question_id=question_id if question_id in questions else None,
        event_type=event_type, duration_ms=None, payload=details or {},
        client_timestamp=datetime.fromtimestamp(client_ts_ms / 1000, tz=timezone.utc) if client_ts_ms else None,
    ))
    await db.commit()


async def active_alerts(db: AsyncSession, session_id: int) -> set[int]:
    """Учасники, які зараз відволіклися (остання подія ще без повернення уваги)."""
    rows = await db.execute(
        select(ProctoringEvent.participant_id, ProctoringEvent.event_type, ProctoringEvent.duration_ms,
               ProctoringEvent.received_at)
        .where(ProctoringEvent.session_id == session_id)
        .order_by(ProctoringEvent.participant_id, ProctoringEvent.id.desc())
        .distinct(ProctoringEvent.participant_id)
    )
    horizon = utcnow() - timedelta(minutes=10)
    return {pid for pid, et, dur, at in rows.all()
            if et in LASTING_EVENTS and dur is None and at > horizon}
