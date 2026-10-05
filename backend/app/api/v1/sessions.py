"""Сесії тестування (викладач): запуск за PIN, моніторинг, закриття, результати, аналітика."""
import csv
import io
import secrets

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, OptionalUser, Teacher, get_owned_test
from app.models import (
    ProctoringEvent, Question, SessionParticipant, StudentAnswer, StudentResult, Test, TestSession,
)
from app.models.enums import QuestionStatus, SessionStatus, UserRole
from app.schemas.session import (
    AnalyticsOut, DashboardOut, ItemStatsOut, JoinRequest, JoinResponse, ParticipantRow,
    ProctoringEventOut, ResultRow, SessionCreate, SessionOut, SessionSummary,
)
from app.services.analytics.item_analysis import Response, analyze
from app.services.testing import service

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _owned_session(db, session_id: int, user) -> TestSession:
    session = await db.get(TestSession, session_id)
    if session is None or (session.host_id != user.id and user.role != UserRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сесію не знайдено")
    return session


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(data: SessionCreate, db: DbSession, user: Teacher) -> TestSession:
    test = await get_owned_test(db, data.test_id, user)
    allowed = [QuestionStatus.APPROVED]
    if data.settings.include_ai_verified:
        allowed.append(QuestionStatus.AI_VERIFIED)
    question_ids = list(await db.scalars(
        select(Question.id)
        .where(Question.test_id == test.id, Question.status.in_(allowed))
        .order_by(Question.position, Question.id)
    ))
    if not question_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У тесті немає затверджених питань. Затвердьте питання в редакторі або дозвольте "
            "питання, перевірені лише ШІ.",
        )

    settings = {**data.settings.model_dump(), "question_ids": question_ids}
    session = None
    for _ in range(20):  # PIN унікальний серед активних сесій
        session = TestSession(
            test_id=test.id, host_id=user.id, pin_code=f"{secrets.randbelow(10**6):06d}",
            status=SessionStatus.RUNNING, settings=settings, started_at=service.utcnow(),
        )
        db.add(session)
        try:
            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
            session = None
    if session is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не вдалося підібрати PIN, спробуйте ще раз")
    await db.refresh(session)  # підтягнути created_at перед серіалізацією
    return session


@router.get("", response_model=list[SessionSummary])
async def list_sessions(db: DbSession, user: Teacher, test_id: int | None = None) -> list[SessionSummary]:
    query = (
        select(
            TestSession, Test.title,
            func.count(func.distinct(SessionParticipant.id)),
            func.count(func.distinct(StudentResult.id)),
            func.avg(StudentResult.score),
            func.max(StudentResult.max_score),
        )
        .join(Test, Test.id == TestSession.test_id)
        .outerjoin(SessionParticipant, SessionParticipant.session_id == TestSession.id)
        .outerjoin(StudentResult, StudentResult.participant_id == SessionParticipant.id)
        .where(TestSession.host_id == user.id)
        .group_by(TestSession.id, Test.title)
        .order_by(TestSession.id.desc())
    )
    if test_id is not None:
        query = query.where(TestSession.test_id == test_id)
    return [
        SessionSummary(**SessionOut.model_validate(s).model_dump(), test_title=title, participants=n,
                       finished=done, avg_score=avg, max_score=mx)
        for s, title, n, done, avg, mx in (await db.execute(query)).all()
    ]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: int, db: DbSession, user: Teacher) -> TestSession:
    return await _owned_session(db, session_id, user)


@router.get("/{session_id}/dashboard", response_model=DashboardOut)
async def dashboard(session_id: int, db: DbSession, user: Teacher) -> DashboardOut:
    session = await _owned_session(db, session_id, user)
    await service.finalize_expired(db, session)
    test = await db.get(Test, session.test_id)
    total = len((session.settings or {}).get("question_ids", []))

    answered = dict((await db.execute(
        select(StudentAnswer.participant_id, func.count())
        .where(StudentAnswer.session_id == session.id, func.cardinality(StudentAnswer.selected_option_ids) > 0)
        .group_by(StudentAnswer.participant_id))).all())
    distractions = dict((await db.execute(
        select(ProctoringEvent.participant_id, func.count())
        .where(ProctoringEvent.session_id == session.id)
        .group_by(ProctoringEvent.participant_id))).all())
    results = {r.participant_id: r for r in await db.scalars(
        select(StudentResult).where(StudentResult.session_id == session.id))}
    alerts = await service.active_alerts(db, session.id)

    rows = []
    for p in await db.scalars(select(SessionParticipant).where(SessionParticipant.session_id == session.id)
                              .order_by(SessionParticipant.joined_at)):
        r = results.get(p.id)
        rows.append(ParticipantRow(
            participant_id=p.id, display_name=p.display_name,
            state="finished" if r else "in_progress",
            answered=r.answered_count if r else answered.get(p.id, 0), total=total,
            score=r.score if r else None, max_score=r.max_score if r else None,
            correct_count=r.correct_count if r else None,
            distraction_count=distractions.get(p.id, 0),
            alert_active=p.id in alerts and not r,
            joined_at=p.joined_at, finished_at=r.finished_at if r else None,
        ))
    return DashboardOut(session=SessionOut.model_validate(session), test_title=test.title,
                        total_questions=total, participants=rows)


@router.post("/{session_id}/close", response_model=SessionOut)
async def close(session_id: int, db: DbSession, user: Teacher) -> TestSession:
    session = await _owned_session(db, session_id, user)
    if session.status == SessionStatus.RUNNING:
        await service.close_session(db, session)
        await db.refresh(session)
    return session


@router.post("/join", response_model=JoinResponse)
async def join_session(data: JoinRequest, db: DbSession, user: OptionalUser) -> JoinResponse:
    session = await db.scalar(
        select(TestSession).where(TestSession.pin_code == data.pin, TestSession.status == SessionStatus.RUNNING)
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тест із таким PIN не знайдено або його вже закрито")
    test = await db.get(Test, session.test_id)

    if user is not None:
        existing = await db.scalar(select(SessionParticipant).where(
            SessionParticipant.session_id == session.id, SessionParticipant.user_id == user.id))
        if existing is not None:  # повторний вхід того самого студента — повертаємо його спробу
            return JoinResponse(token=existing.reconnect_token, display_name=existing.display_name,
                                test_title=test.title)

    name = data.display_name.strip()
    participant = SessionParticipant(
        session_id=session.id, user_id=user.id if user else None, display_name=name,
        reconnect_token=secrets.token_urlsafe(32), is_connected=True,
    )
    db.add(participant)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Це ім'я вже зайняте в цьому тесті — додайте, наприклад, прізвище") from None
    return JoinResponse(token=participant.reconnect_token, display_name=name, test_title=test.title)


async def _result_rows(db, session_id: int) -> list[ResultRow]:
    rows = (await db.execute(
        select(StudentResult, SessionParticipant.display_name)
        .join(SessionParticipant, SessionParticipant.id == StudentResult.participant_id)
        .where(StudentResult.session_id == session_id)
        .order_by(StudentResult.score.desc(), StudentResult.finished_at)
    )).all()
    return [
        ResultRow(rank=i, participant_id=r.participant_id, display_name=name, score=r.score,
                  max_score=r.max_score, correct_count=r.correct_count,
                  answered_count=r.answered_count, distraction_count=r.distraction_count,
                  finished_at=r.finished_at)
        for i, (r, name) in enumerate(rows, start=1)
    ]


@router.get("/{session_id}/results", response_model=list[ResultRow])
async def session_results(session_id: int, db: DbSession, user: Teacher) -> list[ResultRow]:
    await _owned_session(db, session_id, user)
    return await _result_rows(db, session_id)


@router.get("/{session_id}/results.csv")
async def session_results_csv(session_id: int, db: DbSession, user: Teacher) -> StreamingResponse:
    session = await _owned_session(db, session_id, user)
    buf = io.StringIO()
    buf.write("﻿")  # BOM — щоб Excel правильно відкрив кирилицю
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Місце", "Студент", "Бали", "Максимум", "Правильних", "Відповідей",
                     "Порушень уваги", "Завершено"])
    for r in await _result_rows(db, session_id):
        writer.writerow([r.rank, r.display_name, f"{r.score:g}", f"{r.max_score:g}", r.correct_count,
                         r.answered_count, r.distraction_count, r.finished_at.strftime("%d.%m.%Y %H:%M")])
    filename = f"results_session_{session.id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/proctoring", response_model=list[ProctoringEventOut])
async def session_proctoring(session_id: int, db: DbSession, user: Teacher) -> list[ProctoringEventOut]:
    await _owned_session(db, session_id, user)
    rows = (await db.execute(
        select(ProctoringEvent, SessionParticipant.display_name)
        .join(SessionParticipant, SessionParticipant.id == ProctoringEvent.participant_id)
        .where(ProctoringEvent.session_id == session_id)
        .order_by(ProctoringEvent.id.desc())
        .limit(300)
    )).all()
    return [
        ProctoringEventOut(id=e.id, participant_id=e.participant_id, display_name=name,
                           question_id=e.question_id, event_type=e.event_type,
                           duration_ms=e.duration_ms, received_at=e.received_at)
        for e, name in rows
    ]


@router.get("/{session_id}/analytics", response_model=AnalyticsOut)
async def session_analytics(session_id: int, db: DbSession, user: Teacher) -> AnalyticsOut:
    """Аналіз якості питань (CTT) за завершеними спробами."""
    session = await _owned_session(db, session_id, user)
    finished = select(StudentResult.participant_id).where(StudentResult.session_id == session.id)
    answers = list(await db.scalars(select(StudentAnswer).where(
        StudentAnswer.session_id == session.id, StudentAnswer.participant_id.in_(finished))))
    q_ids = {a.question_id for a in answers}
    questions = {q.id: q for q in await db.scalars(select(Question).where(Question.id.in_(q_ids)))} if q_ids else {}

    stats = analyze(
        [Response(a.participant_id, a.question_id, a.is_correct, a.response_time_ms,
                  tuple(a.selected_option_ids or ())) for a in answers],
        correct_options={qid: {o.id for o in q.options if o.is_correct} for qid, q in questions.items()},
        all_options={qid: {o.id for o in q.options} for qid, q in questions.items()},
    )
    order = {qid: i for i, qid in enumerate((session.settings or {}).get("question_ids", []), start=1)}
    return AnalyticsOut(
        n_participants=stats.n_participants, n_items=stats.n_items,
        mean_score=stats.mean_score, kr20=stats.kr20,
        items=sorted([
            ItemStatsOut(
                question_id=i.question_id, position=order.get(i.question_id),
                text=questions[i.question_id].text if i.question_id in questions else None,
                n=i.n, p_value=i.p_value, discrimination=i.discrimination,
                avg_response_ms=i.avg_response_ms, option_counts=i.option_counts, flags=i.flags,
            )
            for i in stats.items
        ], key=lambda x: x.position or 0),
    )
