from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    google_ai_key: str = ""
    google_maps_key: str = ""
    agent_model: str = "gemini-2.5-flash"
    admin_password: str = "admin123"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()