"""Application configuration using pydantic-settings."""

from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
import os

# Get the backend directory (parent of app/)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# Explicitly load .env file before pydantic settings tries to
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseSettings):
    # Groq LLM
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TEMPERATURE: float = 0.3
    GROQ_MAX_TOKENS: int = 4096
    GOOGLE_API_KEY: str
    GOOGLE_MODEL: str = "gemini-2.5-flash"
    GOOGLE_TEMPERATURE: float = 0.3
    GOOGLE_MAX_TOKENS: int = 4096

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/interview_db"
    CHECKPOINT_DB_URL: str = "postgresql://postgres:postgres@localhost:5432/interview_db"
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 5
    
    # ChromaDB (Vector Store)
    CHROMA_SERVER_HOST: str = "localhost"
    CHROMA_SERVER_PORT: int = 8001
    # Use HTTP client if host is set (non-empty)
    USE_CHROMA_SERVER: bool = True

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # SMTP Settings (for Email) - Support both SMTP_ and RELAY_ prefixes
    SMTP_SERVER: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    RELAY_HOST: str = "localhost"  # Alternative to SMTP_SERVER
    RELAY_PORT: int = 587
    RELAY_USERNAME: str = ""
    RELAY_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "noreply@interview-platform.com"

    @property
    def smtp_host(self) -> str:
        """Get SMTP host, preferring RELAY_HOST if set."""
        return self.RELAY_HOST if self.RELAY_HOST != "localhost" else self.SMTP_SERVER

    @property
    def smtp_port(self) -> int:
        """Get SMTP port, preferring RELAY_PORT if different from default."""
        return self.RELAY_PORT if self.RELAY_PORT != 587 else self.SMTP_PORT

    @property
    def smtp_username(self) -> str:
        """Get SMTP username, preferring RELAY_USERNAME if set."""
        return self.RELAY_USERNAME if self.RELAY_USERNAME else self.SMTP_USERNAME

    @property
    def smtp_password(self) -> str:
        """Get SMTP password, preferring RELAY_PASSWORD if set."""
        return self.RELAY_PASSWORD if self.RELAY_PASSWORD else self.SMTP_PASSWORD

    # Interview Config
    RESUME_SHORTLIST_THRESHOLD: float = 0.65
    MAX_QUESTIONS_PER_TOPIC: int = 5
    READING_TIME_SECONDS: int = 20
    ANSWER_TIME_SECONDS: int = 45

    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "interview-audio-uploads"

    # Cognito
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_APP_CLIENT_ID: str = ""

    # Session Settings (for candidate login)
    SESSION_EXPIRY_HOURS: int = 72  # Session valid for 3 days
    SESSION_ID_LENGTH: int = 32

    # AWS Transcribe
    TRANSCRIBE_LANGUAGE_CODE: str = "en-US"
    TRANSCRIBE_SAMPLE_RATE: int = 48000

    # Debug
    DEBUG: bool = True

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
