from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings, load_settings
from app.main import app
from tests.conftest import FAKE_ENV, FAKE_KEY, write_env


def test_health_reports_models_without_keys(tmp_path: Path) -> None:
    fake_settings = load_settings(write_env(tmp_path, FAKE_ENV))
    app.dependency_overrides[get_settings] = lambda: fake_settings
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "models": {
            "stt": "fake-whisper",
            "refiner": "fake-refiner",
            "documenter": "fake-documenter",
        },
    }
    assert FAKE_KEY not in response.text
