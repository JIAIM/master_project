"""Проходження тесту студентом (доступ за токеном учасника, виданим при вході за PIN)."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import SessionParticipant, StudentResult, Test, TestSession
from app.models.enums import SessionStatus
from app.schemas.session import (
    AnswerIn, PlayOption, PlayQuestion, PlayResult, PlayState, ProctoringIn, ReviewItem, ReviewOption,
)
from app.services.testing import service
from app.services.testing.service import PlayError

router = APIRouter(prefix="/play", tags=["play"])


async def _load(db, token: str) -> tuple[TestSession, SessionParticipant]:
    participant = await db.scalar(select(SessionParticipant).where(SessionParticipant.reconnect_token == token))
    if participant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Учасника не знайдено — увійдіть за PIN ще раз")
    session = await db.get(TestSession, participant.session_id)
    return session, participant


async def _result(db, session: TestSession, participant: SessionParticipant, result: StudentResult) -> PlayResult:
    review = None
    if (session.settings or {}).get("show_review", True):
        answers = await service.participant_answers(db, participant.id)
        review = []
        for q in await service.session_questions(db, session):
            selected = answers.get(q.id, [])
            correct = service.correct_ids(q)
            review.append(ReviewItem(
                question_id=q.id, text=q.text,
                options=[ReviewOption(id=o.id, text=o.text, is_correct=o.is_correct)
                         for o in service.ordered_options(q, participant.id)],
                selected=selected, is_correct=bool(selected) and set(selected) == set(correct),
                explanation=q.explanation,
            ))
    total = len((session.settings or {}).get("question_ids", []))
    return PlayResult(score=result.score, max_score=result.max_score, correct_count=result.correct_count,
                      answered_count=result.answered_count, total=total, review=review)


@router.get("/{token}", response_model=PlayState)
async def play_state(token: str, db: DbSession) -> PlayState:
    session, participant = await _load(db, token)
    test = await db.get(Test, session.test_id)

    result = await db.scalar(select(StudentResult).where(StudentResult.participant_id == participant.id))
    if result is None and (session.status != SessionStatus.RUNNING or service.is_expired(session, participant)):
        result = await service.finalize(db, session, participant)

    questions = await service.session_questions(db, session)
    d = service.deadline(session, participant)
    return PlayState(
        test_title=test.title,
        display_name=participant.display_name,
        state="finished" if result else "in_progress",
        session_open=session.status == SessionStatus.RUNNING,
        server_time_ms=int(service.utcnow().timestamp() * 1000),
        deadline_ms=int(d.timestamp() * 1000) if d else None,
        distraction_threshold_sec=(session.settings or {}).get("distraction_threshold_sec", 3),
        questions=[] if result else [
            PlayQuestion(id=q.id, type=q.type, text=q.text,
                         options=[PlayOption(id=o.id, text=o.text) for o in service.ordered_options(q, participant.id)])
            for q in questions
        ],
        answers=await service.participant_answers(db, participant.id),
        result=await _result(db, session, participant, result) if result else None,
    )


@router.put("/{token}/answers/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def save_answer(token: str, question_id: int, data: AnswerIn, db: DbSession) -> None:
    session, participant = await _load(db, token)
    try:
        await service.save_answer(db, session, participant, question_id, data.option_ids)
    except PlayError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.post("/{token}/finish", response_model=PlayResult)
async def finish(token: str, db: DbSession) -> PlayResult:
    session, participant = await _load(db, token)
    result = await service.finalize(db, session, participant)
    return await _result(db, session, participant, result)


@router.post("/{token}/proctoring", status_code=status.HTTP_204_NO_CONTENT)
async def proctoring(token: str, data: ProctoringIn, db: DbSession) -> None:
    session, participant = await _load(db, token)
    await service.record_proctoring(db, session, participant, data.event, data.question_id,
                                    data.duration_ms, data.client_ts, data.details)
