from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, str_enum
from app.models.enums import JobStatus


class GenerationJob(TimestampMixin, Base):
    """Фонова задача генерації питань; прогрес оновлюється після кожного питання."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus), default=JobStatus.PENDING)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    total: Mapped[int] = mapped_column(default=0)
    completed: Mapped[int] = mapped_column(default=0)       # скільки питань оброблено
    verified_count: Mapped[int] = mapped_column(default=0)  # пройшли перевірку
    rejected_count: Mapped[int] = mapped_column(default=0)  # не пройшли за N спроб
    failed_count: Mapped[int] = mapped_column(default=0)    # помилки LLM/API

    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
