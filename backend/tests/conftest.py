"""Shared test fixtures. Tests use fake values and never read the real backend/.env."""

from pathlib import Path

import pytest

FAKE_KEY = "gsk_fake_test_key_1234567890"

FAKE_ENV = {
    "STT_BASE_URL": "https://example.test/v1",
    "STT_API_KEY": FAKE_KEY,
    "STT_MODEL": "fake-whisper",
    "REFINER_BASE_URL": "https://example.test/v1",
    "REFINER_API_KEY": FAKE_KEY,
    "REFINER_MODEL": "fake-refiner",
    "DOCUMENTER_BASE_URL": "https://example.test/v1",
    "DOCUMENTER_API_KEY": FAKE_KEY,
    "DOCUMENTER_MODEL": "fake-documenter",
}


@pytest.fixture(autouse=True)
def clear_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any real settings from the shell environment so tests stay isolated."""
    for name in [*FAKE_ENV, "MAX_UPLOAD_MB"]:
        monkeypatch.delenv(name, raising=False)


def write_env(tmp_path: Path, values: dict[str, str]) -> Path:
    """Write a temporary .env file and return its path."""
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    return env_file
