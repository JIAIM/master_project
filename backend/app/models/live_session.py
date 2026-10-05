from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, str_enum
from app.models.enums import SessionStatus

if TYPE_CHECKING:
    from app.models.result import StudentAnswer, StudentResult
    from app.models.test import Test
    from app.models.user import User


class TestSession(TimestampMixin, Base):
    """Сесія тестування за PIN. Названа TestSession, щоб не плутати із сесією SQLAlchemy."""

    __tablename__ = "test_sessions"
    __table_args__ = (
        # PIN унікальний лише серед активних сесій
        Index(
            "uq_test_sessions_active_pin",
            "pin_code",
            unique=True,
            postgresql_where=text("status IN ('lobby', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pin_code: Mapped[str] = mapped_column(String(8))
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus), default=SessionStatus.LOBBY
    )
    current_question_index: Mapped[int | None]
    # налаштування сесії та question_ids (зафіксований набір питань)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    test: Mapped[Test] = relationship()
    host: Mapped[User] = relationship()
    participants: Mapped[list[SessionParticipant]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionParticipant(Base):
    """Учасник сесії. user_id може бути порожнім — вхід за PIN без облікового запису."""

    __tablename__ = "session_participants"
    __table_args__ = (UniqueConstraint("session_id", "display_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    # Токен учасника: за ним студент повертається до своєї спроби
    reconnect_token: Mapped[str] = mapped_column(String(64), unique=True)
    is_connected: Mapped[bool] = mapped_column(default=True, server_default=true())
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[TestSession] = relationship(back_populates="participants")
    user: Mapped[User | None] = relationship()
    answers: Mapped[list[StudentAnswer]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
    result: Mapped[StudentResult | None] = relationship(
        back_populates="participant", cascade="all, delete-orphan", uselist=False
    )
