"""Timeouts and visible retries for every call to an AI service.

The OpenAI SDK's own retries are turned off (max_retries=0) because they are
silent. Instead, call_with_retry() retries temporary problems, logs each retry,
and reports it through `on_retry` so the app can show "Retrying...".
"""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
import openai

logger = logging.getLogger("app.pipeline.retry")

# --- Timeouts (seconds) ---
CONNECT_TIMEOUT = 10.0  # reaching the service at all; an unreachable server fails fast
STT_BASE_TIMEOUT = 60.0  # waiting for Whisper's answer...
STT_SECONDS_PER_AUDIO_MINUTE = 2.0  # ...plus this much per minute of audio
REFINER_TIMEOUT = 60.0  # per batch of segments (usually ~2 s)
DOCUMENTER_TIMEOUT = 90.0  # whole record (usually 6-10 s)

# --- Retries ---
MAX_RETRIES_AFTER_TIMEOUT = 1  # we already waited a long time
MAX_RETRIES_AFTER_QUICK_FAILURE = 2  # connection refused, server error, rate limit
RETRY_DELAYS = [2.0, 5.0]  # wait before the 1st and 2nd retry
MAX_RETRY_AFTER_SECONDS = 20.0  # cap on a rate limit's "Retry-After" wait

# How to wait between retries. Tests replace this so they don't really wait.
sleep: Callable[[float], None] = time.sleep

T = TypeVar("T")
RetryCallback = Callable[[str], None]  # receives a note like "Slow response... Retrying (attempt 2 of 2)..."


class RetriesExhausted(Exception):
    """A temporary problem that kept happening after all retries."""

    def __init__(self, error: openai.APIError, attempts: int) -> None:
        super().__init__(str(error))
        self.error = error
        self.attempts = attempts


def stt_timeout(audio_seconds: float) -> httpx.Timeout:
    """Longer recordings get a longer wait for Whisper's answer."""
    read = STT_BASE_TIMEOUT + STT_SECONDS_PER_AUDIO_MINUTE * audio_seconds / 60
    return httpx.Timeout(round(read, 1), connect=CONNECT_TIMEOUT)


def llm_timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds, connect=CONNECT_TIMEOUT)


def call_with_retry(call: Callable[[], T], stage: str, on_retry: RetryCallback | None = None) -> T:
    """Run `call`, retrying temporary failures. Permanent failures (bad key, bad request) are raised at once.

    Raises RetriesExhausted if a temporary failure keeps happening.
    """
    retries = 0
    while True:
        try:
            return call()
        except openai.APIError as error:
            problem = _temporary_problem(error)
            if problem is None:
                raise  # permanent: retrying can't help
            reason, max_retries = problem
            if retries >= max_retries:
                raise RetriesExhausted(error, attempts=retries + 1) from None

            retries += 1
            wait = _wait_before_retry(error, retries)
            note = f"{reason}. Retrying (attempt {retries + 1} of {max_retries + 1})…"
            logger.warning("%s: %s; retrying in %.0fs (attempt %d of %d)", stage, reason, wait, retries + 1, max_retries + 1)
            if on_retry:
                on_retry(note)
            sleep(wait)


def _temporary_problem(error: openai.APIError) -> tuple[str, int] | None:
    """(reason shown to the user, how many retries allowed), or None if not worth retrying."""
    if isinstance(error, openai.APITimeoutError):  # check before APIConnectionError: it's a subclass
        return "Slow response from the service", MAX_RETRIES_AFTER_TIMEOUT
    if isinstance(error, openai.APIConnectionError):
        return "Could not connect to the service", MAX_RETRIES_AFTER_QUICK_FAILURE
    if isinstance(error, openai.RateLimitError):
        return "The service is busy (rate limit)", MAX_RETRIES_AFTER_QUICK_FAILURE
    if isinstance(error, openai.InternalServerError):  # any 5xx
        return "The service had a temporary error", MAX_RETRIES_AFTER_QUICK_FAILURE
    return None


def _wait_before_retry(error: openai.APIError, retry_number: int) -> float:
    """Use the service's Retry-After for rate limits (capped); otherwise our fixed delays."""
    if isinstance(error, openai.RateLimitError):
        try:
            return min(float(error.response.headers.get("retry-after", "")), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass
    return RETRY_DELAYS[min(retry_number, len(RETRY_DELAYS)) - 1]
