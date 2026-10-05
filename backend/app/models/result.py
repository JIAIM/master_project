from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, str_enum
from app.models.enums import ProctoringEventType

if TYPE_CHECKING:
    from app.models.live_session import SessionParticipant
    from app.models.test import Question


class StudentAnswer(Base):
    """Відповідь студента на питання — основні дані для аналітики та IRT."""

    __tablename__ = "student_answers"
    __table_args__ = (UniqueConstraint("participant_id", "question_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("session_participants.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT: питання з історією відповідей не видаляється, лише архівується
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    selected_option_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    is_correct: Mapped[bool]
    score: Mapped[float] = mapped_column(Float, default=0.0)
    response_time_ms: Mapped[int | None]      # для аналізу швидкості та вгадування
    had_distraction: Mapped[bool] = mapped_column(default=False)  # чи був сигнал прокторингу під час питання
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participant: Mapped[SessionParticipant] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()


class StudentResult(Base):
    """Підсумок студента за сесію; запис з'являється, коли спробу завершено."""

    __tablename__ = "student_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("session_participants.id", ondelete="CASCADE"), unique=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_count: Mapped[int] = mapped_column(default=0)
    answered_count: Mapped[int] = mapped_column(default=0)
    distraction_count: Mapped[int] = mapped_column(default=0)
    ability_theta: Mapped[float | None] = mapped_column(Float)  # оцінка здібності за IRT
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participant: Mapped[SessionParticipant] = relationship(back_populates="result")


class ProctoringEvent(Base):
    """Події прокторингу з браузера (лише сигнали, без відео)."""

    __tablename__ = "proctoring_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("session_participants.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    event_type: Mapped[ProctoringEventType] = mapped_column(str_enum(ProctoringEventType))
    duration_ms: Mapped[int | None]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    client_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
