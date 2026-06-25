from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ─── Telegram ───────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str

    # ─── Owner ──────────────────────────────────────────────────
    OWNER_TELEGRAM_ID: int          # твой Telegram ID (число)
    OWNER_PIN: str                  # PIN для входа в настройки

    # ─── Anthropic ──────────────────────────────────────────────
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-opus-4-8"

    # ─── OpenAI ─────────────────────────────────────────────────
    OPENAI_API_KEY: str
    WHISPER_MODEL: str = "whisper-1"
    IMAGE_MODEL: str = "gpt-image-1"

    # ─── Database ───────────────────────────────────────────────
    DATABASE_URL: str               # postgresql+asyncpg://user:pass@host/dbname

    # ─── App ────────────────────────────────────────────────────
    TIMEZONE: str = "Europe/Moscow"
    MORNING_REPORT_TIME: str = "07:30"  # HH:MM

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
