"""
Application settings loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Async DB URL (used by FastAPI endpoints via asyncpg)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/certificates_db"

    # Sync DB URL (used by Celery worker via psycopg2)
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/certificates_db"

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Directory where generated PDFs are stored
    CERTIFICATES_DIR: str = "certificates"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
