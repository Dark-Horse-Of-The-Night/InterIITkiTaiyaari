"""Application settings, loaded from backend/.env.

Every model choice and API key comes from here — never hardcode them elsewhere.
API keys are stored as SecretStr, so printing or logging the settings shows
'**********' instead of the real key.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, found relative to this file so it works from any directory.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

PLACEHOLDER_KEY = "your-groq-api-key-here"


class ConfigError(Exception):
    """Raised when backend/.env is missing settings or has invalid values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Stage 1: speech-to-text
    stt_base_url: str
    stt_api_key: SecretStr
    stt_model: str

    # Stage 2: refiner
    refiner_base_url: str
    refiner_api_key: SecretStr
    refiner_model: str

    # Stage 3: documenter
    documenter_base_url: str
    documenter_api_key: SecretStr
    documenter_model: str

    # Uploads
    max_upload_mb: int = 25

    @field_validator("stt_api_key", "refiner_api_key", "documenter_api_key")
    @classmethod
    def key_must_be_real(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret or secret == PLACEHOLDER_KEY:
            raise ValueError("is empty or still the placeholder value")
        return value


def load_settings(env_file: Path | None = ENV_FILE) -> Settings:
    """Load settings, turning validation errors into one plain-English message."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as error:
        problems = []
        for issue in error.errors():
            name = str(issue["loc"][0]).upper()
            if issue["type"] == "missing":
                problems.append(f"{name} is missing")
            else:
                problems.append(f"{name} {issue['msg'].removeprefix('Value error, ')}")
        raise ConfigError(
            "Configuration problem in backend/.env: "
            + "; ".join(problems)
            + ". Copy backend/.env.example to backend/.env and fill in these values."
        ) from None


@lru_cache
def get_settings() -> Settings:
    """Load settings once and reuse them (used as a FastAPI dependency)."""
    return load_settings()
