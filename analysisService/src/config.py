from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    gigachat_credentials: str = ""
    gigachat_scope: str = ""
    gigachat_model: str = ""

    class Config:
        env_file = str(_ENV_FILE)
        env_prefix = ""
        env_file_encoding = "utf-8"


settings = Settings()