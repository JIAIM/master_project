from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, false, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, str_enum
from app.models.enums import (
    Difficulty, QuestionOrigin, QuestionStatus, QuestionType, VerificationVerdict,
)

if TYPE_CHECKING:
    from app.models.material import Material
    from app.models.user import User

# Тест може будуватися на кількох матеріалах
test_materials = Table(
    "test_materials",
    Base.metadata,
    Column("test_id", ForeignKey("tests.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True),
)


class Test(TimestampMixin, Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    default_time_limit_sec: Mapped[int] = mapped_column(default=30, server_default="30")
    is_published: Mapped[bool] = mapped_column(default=False, server_default=false())

    # Експорт у Google Форми
    google_form_id: Mapped[str | None] = mapped_column(String(128))
    google_form_url: Mapped[str | None] = mapped_column(String(512))

    owner: Mapped[User] = relationship(back_populates="tests")
    materials: Mapped[list[Material]] = relationship(secondary=test_materials)
    questions: Mapped[list[Question]] = relationship(
        back_populates="test",
        order_by="Question.position",
        cascade="all, delete-orphan",
    )


class Question(TimestampMixin, Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)

    type: Mapped[QuestionType] = mapped_column(
        str_enum(QuestionType), default=QuestionType.SINGLE_CHOICE
    )
    text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)  # пояснення правильної відповіді
    # Дослівна цитата з матеріалу, що підтверджує відповідь
    source_quote: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(str_enum(Difficulty), default=Difficulty.MEDIUM)
    status: Mapped[QuestionStatus] = mapped_column(
        str_enum(QuestionStatus), default=QuestionStatus.DRAFT, index=True
    )
    origin: Mapped[QuestionOrigin] = mapped_column(
        str_enum(QuestionOrigin), default=QuestionOrigin.AI_GENERATED
    )
    points: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    time_limit_sec: Mapped[int | None] = mapped_column(Integer)  # перевизначає Test.default_time_limit_sec

    # --- Звідки взято питання (фрагменти RAG) ---
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    llm_model: Mapped[str | None] = mapped_column(String(128))
    generation_attempts: Mapped[int] = mapped_column(default=1, server_default="1")

    # --- Версіонування: питання з відповідями не редагується, а отримує нову версію ---
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    # --- Параметри IRT (3PL), заповнюються після калібрування ---
    irt_discrimination: Mapped[float | None] = mapped_column(Float)  # a
    irt_difficulty: Mapped[float | None] = mapped_column(Float)      # b
    irt_guessing: Mapped[float | None] = mapped_column(Float)        # c
    irt_calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    test: Mapped[Test] = relationship(back_populates="questions")
    # lazy="selectin": ліниве завантаження в async-режимі недоступне
    options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question",
        order_by="AnswerOption.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    verifications: Mapped[list[QuestionVerification]] = relationship(
        back_populates="question",
        order_by="QuestionVerification.attempt",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Question | None] = relationship(remote_side="Question.id")


class AnswerOption(Base):
    """Варіант відповіді: правильний або хибний."""

    __tablename__ = "answer_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(default=0)
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Чому хибний варіант правдоподібний (яку типову помилку перевіряє)
    distractor_rationale: Mapped[str | None] = mapped_column(Text)

    question: Mapped[Question] = relationship(back_populates="options")


class QuestionVerification(Base):
    """Журнал перевірки питання: один запис — одна спроба."""

    __tablename__ = "question_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int]
    verdict: Mapped[VerificationVerdict] = mapped_column(str_enum(VerificationVerdict))
    # бали Критика, відповідь Розв'язувача, порушення правил
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    critique: Mapped[str | None] = mapped_column(Text)
    critic_model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[Question] = relationship(back_populates="verifications")
