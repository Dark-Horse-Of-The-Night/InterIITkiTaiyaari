from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.config import load_settings
from app.pipeline.api_errors import explain_api_error
from app.pipeline.documenter import make_documenter_client
from app.pipeline.refiner import make_refiner_client
from app.pipeline.retry import RetriesExhausted, call_with_retry, stt_timeout
from app.pipeline.stt import make_stt_client, transcribe
from tests.conftest import FAKE_ENV, write_env

REQUEST = httpx.Request("POST", "https://example.test/v1")


def status_error(cls: type[openai.APIStatusError], status: int, headers: dict[str, str] | None = None) -> openai.APIStatusError:
    return cls("error", response=httpx.Response(status, request=REQUEST, headers=headers), body=None)


def timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=REQUEST)


def connection() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=REQUEST)


class Flaky:
    """A call that raises the given errors in order, then returns "ok"."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def test_success_needs_no_retry(no_real_waiting: list[float]) -> None:
    call = Flaky()
    assert call_with_retry(call, "Refiner") == "ok"
    assert call.calls == 1
    assert no_real_waiting == []


@pytest.mark.parametrize(
    "error",
    [connection(), status_error(openai.InternalServerError, 503), status_error(openai.RateLimitError, 429)],
)
def test_quick_failures_are_retried_up_to_twice(error: Exception, no_real_waiting: list[float]) -> None:
    notes: list[str] = []
    call = Flaky(error, error)

    assert call_with_retry(call, "Refiner", notes.append) == "ok"
    assert call.calls == 3
    assert no_real_waiting == [2.0, 5.0]
    assert notes[0].endswith("Retrying (attempt 2 of 3)…")
    assert notes[1].endswith("Retrying (attempt 3 of 3)…")


def test_quick_failure_gives_up_after_three_attempts() -> None:
    call = Flaky(connection(), connection(), connection(), connection())

    with pytest.raises(RetriesExhausted) as raised:
        call_with_retry(call, "Refiner")
    assert raised.value.attempts == 3
    assert call.calls == 3


def test_timeout_is_retried_only_once() -> None:
    notes: list[str] = []
    call = Flaky(timeout(), timeout(), timeout())

    with pytest.raises(RetriesExhausted) as raised:
        call_with_retry(call, "Speech-to-text", notes.append)
    assert raised.value.attempts == 2
    assert notes == ["Slow response from the service. Retrying (attempt 2 of 2)…"]


@pytest.mark.parametrize(
    "error",
    [
        status_error(openai.AuthenticationError, 401),
        status_error(openai.NotFoundError, 404),
        status_error(openai.BadRequestError, 400),
    ],
)
def test_permanent_errors_are_not_retried(error: Exception, no_real_waiting: list[float]) -> None:
    call = Flaky(error)

    with pytest.raises(type(error)):
        call_with_retry(call, "Refiner")
    assert call.calls == 1
    assert no_real_waiting == []


def test_rate_limit_retry_after_is_respected_and_capped(no_real_waiting: list[float]) -> None:
    call = Flaky(
        status_error(openai.RateLimitError, 429, {"retry-after": "7"}),
        status_error(openai.RateLimitError, 429, {"retry-after": "120"}),
    )

    call_with_retry(call, "Refiner")
    assert no_real_waiting == [7.0, 20.0]


def test_timeout_message_says_how_many_tries() -> None:
    error = explain_api_error(RetriesExhausted(timeout(), attempts=2), "Speech-to-text", "STT", "m")

    assert str(error) == (
        "Speech-to-text failed: the speech-to-text service did not respond in time (tried 2 times). "
        "Try again in a few minutes. The AI service may be busy."
    )


def test_stt_timeout_grows_with_audio_length() -> None:
    assert stt_timeout(60).read == 62.0  # 1-minute meeting
    assert stt_timeout(25 * 60).read == 110.0  # 25-minute meeting
    assert stt_timeout(25 * 60).connect == 10.0


def test_transcribe_passes_sized_timeout_and_reopens_file_on_retry(tmp_path: Any) -> None:
    audio = tmp_path / "a.flac"
    audio.write_bytes(b"audio")
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        assert kwargs["file"].read() == b"audio"  # a fresh, unread file each attempt
        if len(calls) == 1:
            raise connection()
        return SimpleNamespace(segments=[SimpleNamespace(start=0, end=1, text="Hi.")])

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    transcript = transcribe(audio, client, "m", audio_seconds=120)

    assert transcript.text == "Hi."
    assert len(calls) == 2
    assert calls[0]["timeout"].read == 64.0


def test_sdk_clients_have_their_own_retries_turned_off(tmp_path: Any) -> None:
    settings = load_settings(write_env(tmp_path, FAKE_ENV))

    for client in (make_stt_client(settings), make_refiner_client(settings), make_documenter_client(settings)):
        assert client.max_retries == 0
        assert client.timeout.connect == 10.0
    assert make_refiner_client(settings).timeout.read == 60.0
    assert make_documenter_client(settings).timeout.read == 90.0
