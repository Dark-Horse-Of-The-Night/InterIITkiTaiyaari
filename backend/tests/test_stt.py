from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.pipeline.errors import PipelineError
from app.pipeline.stt import MAX_HINT_CHARS, confidence_fields, glossary_hint, transcribe, transcribe_file
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
    assert client.calls[0]["file"].name.endswith("part_01.ogg")  # converted before sending


def test_transcribe_file_rejects_bad_upload_before_calling_api(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio")
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "x"}])

    with pytest.raises(PipelineError, match="File check failed"):
        transcribe_file(bad, client, model="m", max_upload_mb=25)
    assert client.calls == []


def test_long_recording_parts_become_one_continuous_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.pipeline.audio as audio_module
    from tests.test_audio import make_wav_with_pauses

    monkeypatch.setattr(audio_module, "CHUNK_SECONDS", 10)
    monkeypatch.setattr(audio_module, "CUT_SEARCH_SECONDS", 4)
    upload = make_wav_with_pauses(tmp_path / "long.wav", [("tone", 7.0), ("silence", 1.0), ("tone", 9.0), ("silence", 1.0), ("tone", 7.0)])
    client = FakeWhisperClient(segments=[{"start": 1.0, "end": 2.0, "text": "Hello."}])  # same reply for every part
    details: list[str] = []

    transcript = transcribe_file(upload, client, model="m", max_upload_mb=25, on_detail=details.append)

    assert len(client.calls) == 3
    starts = [s.start for s in transcript.segments]
    assert starts == [1.0, pytest.approx(8.5, abs=0.15), pytest.approx(18.5, abs=0.15)]  # shifted by each part's start
    assert details == ["Preparing the audio", "Part 1 of 3", "Part 2 of 3", "Part 3 of 3"]


def test_one_silent_part_of_a_long_recording_is_fine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.pipeline.audio as audio_module
    from tests.test_audio import make_wav_with_pauses

    monkeypatch.setattr(audio_module, "CHUNK_SECONDS", 10)
    upload = make_wav_with_pauses(tmp_path / "long.wav", [("tone", 25.0)])
    replies = iter([[{"start": 0, "end": 1, "text": "Hi."}], [], [{"start": 0, "end": 1, "text": "Bye."}]])
    client = FakeWhisperClient()
    client.audio.transcriptions.create = lambda **kw: SimpleNamespace(segments=[SimpleNamespace(**x) for x in next(replies)])

    transcript = transcribe_file(upload, client, model="m", max_upload_mb=25)

    assert transcript.text == "Hi. Bye."


# --- Glossary hint for Whisper ---


def test_glossary_is_sent_to_whisper_as_a_hint(tmp_path: Path) -> None:
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"fake")
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "Hello."}])

    transcribe(audio, client, "m", glossary=["Kubernetes", " Priya ", ""])

    assert client.calls[0]["prompt"] == "Terms used in this meeting: Kubernetes, Priya."


def test_no_glossary_means_no_hint(tmp_path: Path) -> None:
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"fake")
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "Hello."}])

    transcribe(audio, client, "m")

    assert "prompt" not in client.calls[0]


def test_long_glossary_is_cut_to_whisper_prompt_size() -> None:
    hint = glossary_hint([f"term{i}" for i in range(500)])

    assert hint is not None and len(hint) < MAX_HINT_CHARS + 40
    assert hint.endswith(".") and "term0" in hint and "term499" not in hint


def test_glossary_reaches_every_part_of_a_long_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.pipeline.audio as audio_module
    from tests.test_audio import make_wav_with_pauses

    monkeypatch.setattr(audio_module, "CHUNK_SECONDS", 10)
    upload = make_wav_with_pauses(tmp_path / "long.wav", [("tone", 25.0)])
    client = FakeWhisperClient(segments=[{"start": 0, "end": 1, "text": "Hi."}])

    transcribe_file(upload, client, model="m", max_upload_mb=25, glossary=["ONNX"])

    assert len(client.calls) > 1
    assert all(call["prompt"] == "Terms used in this meeting: ONNX." for call in client.calls)


# --- Whisper confidence ("unclear audio") ---


def whisper_segment(avg_logprob: float | None, no_speech: float = 0.01, compression: float = 1.5) -> SimpleNamespace:
    return SimpleNamespace(avg_logprob=avg_logprob, no_speech_prob=no_speech, compression_ratio=compression)


@pytest.mark.parametrize(
    ("segment", "unclear"),
    [
        (whisper_segment(-0.15), False),  # clean speech
        (whisper_segment(-0.33), False),  # short clean ending, still fine
        (whisper_segment(-0.59), True),  # heavy noise, words dropped
        (whisper_segment(-0.1, no_speech=0.8), True),  # probably not speech
        (whisper_segment(-0.1, compression=3.0), True),  # repeating itself
    ],
)
def test_unclear_audio_is_flagged_from_whispers_own_scores(segment: SimpleNamespace, unclear: bool) -> None:
    assert confidence_fields(segment)["unclear"] is unclear


def test_confidence_is_a_probability() -> None:
    assert confidence_fields(whisper_segment(-0.15))["confidence"] == 0.86


def test_providers_without_scores_leave_confidence_empty() -> None:
    assert confidence_fields(SimpleNamespace(text="hi")) == {}


def test_confidence_survives_long_recording_time_shift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.pipeline.audio as audio_module
    from tests.test_audio import make_wav_with_pauses

    monkeypatch.setattr(audio_module, "CHUNK_SECONDS", 10)
    upload = make_wav_with_pauses(tmp_path / "long.wav", [("tone", 25.0)])
    client = FakeWhisperClient(segments=[{"start": 1, "end": 2, "text": "Hi.", "avg_logprob": -0.7, "no_speech_prob": 0.0, "compression_ratio": 1.2}])

    transcript = transcribe_file(upload, client, model="m", max_upload_mb=25)

    assert all(s.unclear and s.confidence == 0.5 for s in transcript.segments)
    assert transcript.segments[-1].start > 10  # shifted, and the scores kept
