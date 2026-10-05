"""Налаштування застосунку (читаються з .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Інфраструктура ---
    DATABASE_URL: str = "postgresql+asyncpg://edu:edu_password@localhost:5432/edu_platform"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION: str = "course_materials"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 50
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- Автентифікація ---
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # --- RAG ---
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    MIN_CHUNK_CHARS: int = 80

    # --- LLM (Groq). Ліміти Groq рахуються окремо для кожної моделі, тому ролі на різних моделях ---
    GROQ_API_KEY: str = ""
    LLM_GENERATOR_MODEL: str = "openai/gpt-oss-120b"
    LLM_CRITIC_MODEL: str = "qwen/qwen3.8-27b"
    LLM_SOLVER_MODEL: str = "openai/gpt-oss-20b"
    LLM_GENERATOR_TEMPERATURE: float = 0.7
    LLM_REQUESTS_PER_SECOND: float = 2.0
    GROQ_TOKENS_PER_MINUTE: int = 7200          # 90% від ліміту Groq (8000 токенів/хв)
    GROQ_MAX_COMPLETION_TOKENS: int = 2500
    ENABLE_SOLVER: bool = True
    GENERATION_CONCURRENCY: int = 4             # скільки питань генеруються паралельно

    # --- Резервні LLM-провайдери (вмикаються, якщо задано ключ) ---
    GOOGLE_API_KEY: str = ""
    LLM_GEMINI_MODEL: str = "gemini-flash-latest"
    CEREBRAS_API_KEY: str = ""
    LLM_CEREBRAS_MODEL: str = "gpt-oss-120b"
    OPENROUTER_API_KEY: str = ""
    LLM_OPENROUTER_MODELS: str = "qwen/qwen3.8-27b:free,z-ai/glm-5.2:free,google/gemma-4-31b-it:free"

    # --- Експорт у Google Форми (веб-застосунок Apps Script) ---
    GOOGLE_APPS_SCRIPT_URL: str = ""
    GOOGLE_APPS_SCRIPT_SECRET: str = ""

    # --- Верифікація ---
    MAX_VERIFICATION_ATTEMPTS: int = 3
    CRITIC_MIN_GROUNDING: float = 0.7
    CRITIC_MIN_DISTRACTOR_QUALITY: float = 0.6
    CRITIC_MIN_CLARITY: float = 0.6

    SQL_ECHO: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
