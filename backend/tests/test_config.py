from pathlib import Path

import pytest

from app.config import ConfigError, load_settings
from tests.conftest import FAKE_ENV, FAKE_KEY, write_env


def test_loads_all_settings(tmp_path: Path) -> None:
    settings = load_settings(write_env(tmp_path, FAKE_ENV))

    assert settings.stt_model == "fake-whisper"
    assert settings.refiner_model == "fake-refiner"
    assert settings.documenter_model == "fake-documenter"
    assert settings.stt_api_key.get_secret_value() == FAKE_KEY
    assert settings.max_upload_mb == 200  # defaults when not set
    assert settings.max_audio_minutes == 120


def test_missing_key_gives_clear_error(tmp_path: Path) -> None:
    values = {k: v for k, v in FAKE_ENV.items() if k != "STT_API_KEY"}

    with pytest.raises(ConfigError) as error:
        load_settings(write_env(tmp_path, values))

    message = str(error.value)
    assert "STT_API_KEY is missing" in message
    assert ".env.example" in message


def test_placeholder_key_is_rejected(tmp_path: Path) -> None:
    values = {**FAKE_ENV, "REFINER_API_KEY": "your-groq-api-key-here"}

    with pytest.raises(ConfigError, match="REFINER_API_KEY is empty or still the placeholder"):
        load_settings(write_env(tmp_path, values))


def test_keys_are_hidden_when_printed(tmp_path: Path) -> None:
    settings = load_settings(write_env(tmp_path, FAKE_ENV))

    assert FAKE_KEY not in str(settings)
    assert FAKE_KEY not in repr(settings)
