from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import ProctoringEventType, QuestionType, SessionStatus


# --- Викладач ---
class SessionSettings(BaseModel):
    include_ai_verified: bool = False       # за замовчуванням лише затверджені людиною
    show_review: bool = True                # після завершення студент бачить розбір
    time_limit_min: int | None = Field(None, ge=1, le=300)
    distraction_threshold_sec: int = Field(3, ge=1, le=30)


class SessionCreate(BaseModel):
    test_id: int
    settings: SessionSettings = SessionSettings()


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_id: int
    pin_code: str
    status: SessionStatus
    settings: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SessionSummary(SessionOut):
    test_title: str
    participants: int
    finished: int
    avg_score: float | None
    max_score: float | None


ParticipantState = Literal["in_progress", "finished"]


class ParticipantRow(BaseModel):
    participant_id: int
    display_name: str
    state: ParticipantState
    answered: int
    total: int
    score: float | None
    max_score: float | None
    correct_count: int | None
    distraction_count: int
    alert_active: bool
    camera_off: bool = False
    joined_at: datetime
    finished_at: datetime | None


class DashboardOut(BaseModel):
    session: SessionOut
    test_title: str
    total_questions: int
    participants: list[ParticipantRow]


class ResultRow(BaseModel):
    rank: int
    participant_id: int
    display_name: str
    score: float
    max_score: float
    correct_count: int
    answered_count: int
    distraction_count: int
    finished_at: datetime


class ProctoringEventOut(BaseModel):
    id: int
    participant_id: int
    display_name: str
    question_id: int | None
    event_type: ProctoringEventType
    duration_ms: int | None
    received_at: datetime


class ItemStatsOut(BaseModel):
    question_id: int
    position: int | None
    text: str | None
    n: int
    p_value: float | None
    discrimination: float | None
    avg_response_ms: float | None
    option_counts: dict[int, int]
    flags: list[str]


class AnalyticsOut(BaseModel):
    n_participants: int
    n_items: int
    mean_score: float | None
    kr20: float | None
    items: list[ItemStatsOut]


# --- Студент ---
class JoinRequest(BaseModel):
    pin: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


class JoinResponse(BaseModel):
    token: str
    display_name: str
    test_title: str


class PlayOption(BaseModel):
    id: int
    text: str


class PlayQuestion(BaseModel):
    id: int
    type: QuestionType
    text: str
    options: list[PlayOption]


class ReviewOption(PlayOption):
    is_correct: bool


class ReviewItem(BaseModel):
    question_id: int
    text: str
    options: list[ReviewOption]
    selected: list[int]
    is_correct: bool
    explanation: str | None


class PlayResult(BaseModel):
    score: float
    max_score: float
    correct_count: int
    answered_count: int
    total: int
    review: list[ReviewItem] | None     # None — викладач вимкнув розбір


class PlayState(BaseModel):
    test_title: str
    display_name: str
    state: Literal["in_progress", "finished"]
    session_open: bool
    server_time_ms: int
    deadline_ms: int | None
    distraction_threshold_sec: int
    questions: list[PlayQuestion]
    answers: dict[int, list[int]]
    result: PlayResult | None


class AnswerIn(BaseModel):
    option_ids: list[int] = Field(default_factory=list, max_length=10)


class ProctoringIn(BaseModel):
    event: str = Field(max_length=40)
    question_id: int | None = None
    duration_ms: int | None = Field(None, ge=0, le=24 * 3600 * 1000)
    client_ts: int | None = None
    details: dict[str, Any] | None = None
