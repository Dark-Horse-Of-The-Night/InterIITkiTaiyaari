"""API tests: real FastAPI app and real ffmpeg, but fake AI clients and fake settings."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings, load_settings
from app.jobs import JobStore
from app.main import app, get_clients, get_job_store, safe_filename
from app.pipeline.run import PipelineClients
from tests.conftest import FAKE_ENV, write_env
from tests.test_audio import make_tone_wav
from tests.test_documenter import TRANSCRIPT, make_record
from tests.test_documenter import FakeChatClient as FakeDocumenterClient
from tests.test_refiner import FakeChatClient as FakeRefinerClient
from tests.test_stt import FakeWhisperClient

WHISPER_SEGMENTS = [{"start": s.start, "end": s.end, "text": s.text} for s in TRANSCRIPT.segments]


class Setup:
    """Holds the fakes for one test; change them before calling the API."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.env = dict(FAKE_ENV)
        self.jobs = JobStore()
        self.clients = PipelineClients(
            stt=FakeWhisperClient(segments=WHISPER_SEGMENTS),
            refiner=FakeRefinerClient(),
            documenter=FakeDocumenterClient(make_record()),
        )
        self.client = TestClient(app, raise_server_exceptions=False)

    def upload(self, path: Path | None, glossary: str = "") -> httpx.Response:
        files = {"file": (path.name, path.read_bytes())} if path else None
        return self.client.post("/api/meetings", files=files, data={"glossary": glossary})

    def wav(self, name: str = "meeting.wav") -> Path:
        return make_tone_wav(self.tmp_path / name)


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[Setup]:
    s = Setup(tmp_path)
    app.dependency_overrides[get_settings] = lambda: load_settings(write_env(tmp_path, s.env))
    app.dependency_overrides[get_clients] = lambda: s.clients
    app.dependency_overrides[get_job_store] = lambda: s.jobs
    yield s
    app.dependency_overrides.clear()


def test_upload_runs_all_stages_and_returns_everything(setup: Setup) -> None:
    started = setup.upload(setup.wav(), glossary="Zephyr, KubeFlow")
    assert started.status_code == 202
    job_id = started.json()["job_id"]

    # TestClient runs the background task before returning, so the job is already finished.
    job = setup.client.get(f"/api/meetings/{job_id}").json()

    assert job["status"] == "done"
    assert job["filename"] == "meeting.wav"
    assert [s["state"] for s in job["stages"]] == ["done", "done", "done"]
    result = job["result"]
    assert len(result["raw_transcript"]["segments"]) == len(TRANSCRIPT.segments)
    assert result["record"]["action_items"][0]["owner"] == "Priya"
    assert "| Priya | by Friday |" in result["markdown"]  # Markdown built from the same record
    assert set(result["timings_seconds"]) == {"Speech-to-text", "Refiner", "Documenter"}
    assert "Zephyr, KubeFlow" in setup.clients.refiner.calls[0]["messages"][0]["content"]


def test_new_job_starts_queued_with_pending_stages(setup: Setup) -> None:
    job = setup.jobs.create("x.mp3")

    assert job.status == "queued"
    assert [s.state for s in job.stages] == ["pending", "pending", "pending"]


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("notes.pdf", b"%PDF-1.4", "'.pdf' files are not supported"),
        ("empty.mp3", b"", "the file is empty"),
        ("fake.mp3", b"just some text", "could not be read as audio"),
    ],
)
def test_bad_files_are_rejected_immediately(setup: Setup, filename: str, content: bytes, expected: str) -> None:
    path = setup.tmp_path / filename
    path.write_bytes(content)

    response = setup.upload(path)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["stage"] == "File check"
    assert expected in error["message"]
    assert error["fix"]
    assert setup.clients.stt.calls == []  # never reached the AI


def test_missing_file_gives_plain_english_error(setup: Setup) -> None:
    response = setup.upload(None)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "File check failed: no file was uploaded."


def test_oversized_file_is_rejected_while_saving(setup: Setup) -> None:
    setup.env["MAX_UPLOAD_MB"] = "1"
    big = setup.tmp_path / "big.wav"
    big.write_bytes(b"\0" * (1536 * 1024))  # 1.5 MB: under the header check (limit + 1 MB slack), so save_upload catches it

    response = setup.upload(big)

    assert response.status_code == 413
    assert "above the 1 MB limit" in response.json()["error"]["message"]


def test_oversized_file_is_rejected_from_its_header(setup: Setup) -> None:
    setup.env["MAX_UPLOAD_MB"] = "1"
    huge = setup.tmp_path / "huge.wav"
    huge.write_bytes(b"\0" * (3 * 1024 * 1024))

    response = setup.upload(huge)

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("stage_client", "error", "stage", "expected"),
    [
        ("stt", openai.AuthenticationError("no", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None),
         "Speech-to-text", "Check STT_API_KEY"),
        ("refiner", openai.RateLimitError("busy", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None),
         "Refiner", "Wait a minute"),
        ("documenter", openai.APIConnectionError(request=httpx.Request("POST", "https://x")),
         "Documenter", "Check your internet connection"),
    ],
)
def test_ai_stage_failure_names_the_stage(setup: Setup, stage_client: str, error: Exception, stage: str, expected: str) -> None:
    fake = {"stt": FakeWhisperClient(error=error), "refiner": FakeRefinerClient(replies=[error]),
            "documenter": FakeDocumenterClient(error)}[stage_client]
    setattr(setup.clients, stage_client, fake)

    job_id = setup.upload(setup.wav()).json()["job_id"]
    job = setup.client.get(f"/api/meetings/{job_id}").json()

    assert job["status"] == "failed"
    assert job["error"]["stage"] == stage
    assert expected in job["error"]["fix"]
    states = {s["name"]: s["state"] for s in job["stages"]}
    assert states[stage] == "failed"


def test_unexpected_crash_gives_generic_message_without_details(setup: Setup) -> None:
    setup.clients.documenter = FakeDocumenterClient(RuntimeError("secret internal detail"))

    job_id = setup.upload(setup.wav()).json()["job_id"]
    job = setup.client.get(f"/api/meetings/{job_id}").json()

    assert job["status"] == "failed"
    assert job["error"]["message"].startswith("Something went wrong on the server")
    assert "secret internal detail" not in str(job)


def test_unknown_job_id_gives_404(setup: Setup) -> None:
    response = setup.client.get("/api/meetings/does-not-exist")

    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"]


def test_temporary_files_are_deleted(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Path] = []
    real_mkdtemp = __import__("tempfile").mkdtemp

    def tracking_mkdtemp(**kwargs: Any) -> str:
        path = real_mkdtemp(**kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr("app.main.tempfile.mkdtemp", tracking_mkdtemp)
    bad = setup.tmp_path / "fake.mp3"
    bad.write_text("not audio")

    setup.upload(setup.wav())  # success path
    setup.upload(bad)  # failure path

    assert len(created) == 2
    assert not any(path.exists() for path in created)


def test_safe_filename() -> None:
    assert safe_filename("../../etc/a b?.MP3") == "a_b_.MP3"
    assert safe_filename("meeting.mp3") == "meeting.mp3"
