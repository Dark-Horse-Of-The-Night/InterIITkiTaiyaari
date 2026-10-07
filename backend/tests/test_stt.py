from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.pipeline.errors import PipelineError
from app.pipeline.stt import transcribe, transcribe_file
from tests.test_audio import make_tone_wav

FAKE_REQUEST = httpx.Request("POST", "https://example.test/v1/audio/transcriptions")


class FakeWhisperClient:
    """Stands in for the OpenAI client: returns a fixed response or raises an error."""

    def __init__(self, segments: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.segments = segments or []
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(segments=[SimpleNamespace(**seg) for seg in self.segments])


def api_error(error_class: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    return error_class("error", response=httpx.Response(status, request=FAKE_REQUEST), body=None)


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "audio.flac"
    path.write_bytes(b"fake audio bytes")  # transcribe() only passes bytes to the client
    return path


def test_segments_are_parsed_and_trimmed(audio: Path) -> None:
    client = FakeWhisperClient(segments=[
        {"start": 0.0, "end": 2.5, "text": " We deploy on Kubernetes. "},
        {"start": 2.5, "end": 5.0, "text": "Ravi owns the migration."},
    ])

    transcript = transcribe(audio, client, model="fake-whisper")

    assert [s.text for s in transcript.segments] == ["We deploy on Kubernetes.", "Ravi owns the migration."]
    assert transcript.segments[1].start == 2.5
    assert transcript.text == "We deploy on Kubernetes. Ravi owns the migration."


def test_requests_english_segments_at_temperature_zero(audio: Path) -> None:
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "Hello."}])

    transcribe(audio, client, model="fake-whisper")

    call = client.calls[0]
    assert call["model"] == "fake-whisper"
    assert call["language"] == "en"
    assert call["response_format"] == "verbose_json"
    assert call["temperature"] == 0


def test_blank_segments_are_dropped(audio: Path) -> None:
    client = FakeWhisperClient(segments=[
        {"start": 0, "end": 1, "text": "   "},
        {"start": 1, "end": 2, "text": "Real speech."},
    ])

    assert [s.text for s in transcribe(audio, client, "m").segments] == ["Real speech."]


def test_no_speech_gives_clear_error(audio: Path) -> None:
    with pytest.raises(PipelineError, match="no speech was detected"):
        transcribe(audio, FakeWhisperClient(segments=[]), "m")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (api_error(openai.AuthenticationError, 401), "Check STT_API_KEY"),
        (api_error(openai.RateLimitError, 429), "Wait a minute"),
        (api_error(openai.NotFoundError, 404), "Check STT_MODEL"),
        (api_error(openai.BadRequestError, 400), "exporting the recording as .mp3"),
        (api_error(openai.InternalServerError, 500), "unexpected error"),
        (openai.APIConnectionError(request=FAKE_REQUEST), "Check your internet connection"),
        (openai.APITimeoutError(request=FAKE_REQUEST), "did not respond in time (tried 2 times)"),
    ],
)
def test_api_errors_become_plain_english(audio: Path, error: Exception, expected: str) -> None:
    with pytest.raises(PipelineError) as raised:
        transcribe(audio, FakeWhisperClient(error=error), "m")

    message = str(raised.value)
    assert message.startswith("Speech-to-text failed:")
    assert expected in message


def test_transcribe_file_validates_converts_and_transcribes(tmp_path: Path) -> None:
    upload = make_tone_wav(tmp_path / "meeting.wav")
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "Hello."}])

    transcript = transcribe_file(upload, client, model="m", max_upload_mb=25)

    assert transcript.text == "Hello."
    assert client.calls[0]["file"].name.endswith("_16k_mono.flac")  # converted before sending


def test_transcribe_file_rejects_bad_upload_before_calling_api(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio")
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "x"}])

    with pytest.raises(PipelineError, match="File check failed"):
        transcribe_file(bad, client, model="m", max_upload_mb=25)
    assert client.calls == []
