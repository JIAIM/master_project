# Імпорт усіх моделей, щоб Alembic бачив їх через Base.metadata
from app.db.base import Base
from app.models.enums import *  # noqa: F401,F403
from app.models.generation_job import GenerationJob
from app.models.live_session import SessionParticipant, TestSession
from app.models.material import Material
from app.models.result import ProctoringEvent, StudentAnswer, StudentResult
from app.models.test import AnswerOption, Question, QuestionVerification, Test, test_materials
from app.models.user import User

__all__ = [
    "Base", "User", "Material", "Test", "test_materials", "Question", "AnswerOption",
    "QuestionVerification", "TestSession", "SessionParticipant", "StudentAnswer",
    "StudentResult", "ProctoringEvent", "GenerationJob",
]
