import random
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    Difficulty, JobStatus, QuestionOrigin, QuestionStatus, QuestionType, VerificationVerdict,
)
from app.schemas.material import MaterialBrief


# --- Тести ---
class TestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    material_ids: list[int] = Field(min_length=1)
    default_time_limit_sec: int = Field(30, ge=5, le=600)


class TestUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    default_time_limit_sec: int | None = Field(None, ge=5, le=600)
    is_published: bool | None = None


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    default_time_limit_sec: int
    is_published: bool
    google_form_url: str | None
    created_at: datetime
    materials: list[MaterialBrief]


class GoogleFormOut(BaseModel):
    edit_url: str
    respond_url: str
    shared: Literal["editor", "link"]


# --- Питання ---
class OptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    is_correct: bool
    distractor_rationale: str | None


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt: int
    verdict: VerificationVerdict
    scores: dict[str, Any]
    critique: str | None
    critic_model: str | None
    created_at: datetime


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_id: int
    position: int
    type: QuestionType
    text: str
    explanation: str | None
    source_quote: str | None
    difficulty: Difficulty
    status: QuestionStatus
    origin: QuestionOrigin
    points: float
    time_limit_sec: int | None
    version: int
    parent_id: int | None
    generation_attempts: int
    options: list[OptionOut]


class QuestionDetail(QuestionOut):
    verifications: list[VerificationOut]
    source_chunk_ids: list[str]


class TestDetail(TestOut):
    questions: list[QuestionOut]


class OptionIn(BaseModel):
    text: str = Field(min_length=1)
    is_correct: bool = False
    distractor_rationale: str | None = None


def _validate_options(qtype: QuestionType, options: list[OptionIn]) -> None:
    n_correct = sum(o.is_correct for o in options)
    if len({o.text.strip().lower() for o in options}) != len(options):
        raise ValueError("Варіанти відповіді не повинні повторюватися")
    if qtype == QuestionType.MULTIPLE_CHOICE:
        if not 1 <= n_correct < len(options):
            raise ValueError("Потрібен хоча б один правильний і один неправильний варіант")
    elif n_correct != 1:
        raise ValueError("Має бути рівно один правильний варіант")
    if qtype == QuestionType.TRUE_FALSE and len(options) != 2:
        raise ValueError("Для питання «правда/неправда» потрібно рівно 2 варіанти")


class QuestionCreate(BaseModel):
    type: QuestionType = QuestionType.SINGLE_CHOICE
    text: str = Field(min_length=5)
    explanation: str | None = None
    difficulty: Difficulty = Difficulty.MEDIUM
    points: float = Field(1.0, gt=0)
    time_limit_sec: int | None = Field(None, ge=5, le=600)
    options: list[OptionIn] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def _check(self):
        _validate_options(self.type, self.options)
        return self


class QuestionUpdate(BaseModel):
    text: str | None = Field(None, min_length=5)
    explanation: str | None = None
    difficulty: Difficulty | None = None
    points: float | None = Field(None, gt=0)
    time_limit_sec: int | None = Field(None, ge=5, le=600)
    options: list[OptionIn] | None = Field(None, min_length=2, max_length=8)


class TransformRequest(BaseModel):
    action: Literal["simplify", "complicate", "rephrase", "improve_distractors", "regenerate"]
    instruction: str | None = Field(None, max_length=500)
    language: str = "uk"


class ReorderRequest(BaseModel):
    question_ids: list[int] = Field(min_length=1)


# --- Генерація ---
MAX_QUESTIONS_PER_JOB = 20


class GenerateTestRequest(BaseModel):
    single_choice_count: int = Field(10, ge=0, le=MAX_QUESTIONS_PER_JOB)
    true_false_count: int = Field(0, ge=0, le=MAX_QUESTIONS_PER_JOB)
    difficulty: Difficulty | Literal["mixed"] = "mixed"
    topic: str | None = Field(None, max_length=300)
    language: str = Field("uk", max_length=8)

    @model_validator(mode="after")
    def _check_total(self):
        if not 1 <= self.num_questions <= MAX_QUESTIONS_PER_JOB:
            raise ValueError(f"Загальна кількість питань має бути від 1 до {MAX_QUESTIONS_PER_JOB}")
        return self

    @property
    def num_questions(self) -> int:
        return self.single_choice_count + self.true_false_count

    def question_types(self) -> list[str]:
        """Тип кожного питання по порядку (перемішано детерміновано)."""
        types = ([QuestionType.SINGLE_CHOICE.value] * self.single_choice_count
                 + [QuestionType.TRUE_FALSE.value] * self.true_false_count)
        random.Random(self.num_questions).shuffle(types)
        return types


class GenerationJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_id: int
    status: JobStatus
    params: dict[str, Any]
    total: int
    completed: int
    verified_count: int
    rejected_count: int
    failed_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
