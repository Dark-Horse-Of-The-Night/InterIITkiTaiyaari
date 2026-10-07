"""Turn errors from model APIs into plain-English PipelineErrors. Shared by every stage."""

import openai

from app.pipeline.errors import PipelineError
from app.pipeline.retry import RetriesExhausted, is_request_too_large, long_wait_seconds


def explain_api_error(
    error: openai.APIError | RetriesExhausted,
    stage: str,
    setting_prefix: str,
    model: str,
    bad_request_fix: str = "Try again. If it keeps happening, the input may be too long for this model.",
) -> PipelineError:
    """Build a user-facing error saying which stage failed and which setting to check.

    `setting_prefix` is the start of the .env names for this stage, e.g. "STT" or "REFINER".
    A RetriesExhausted error adds how many times we tried, e.g. "(tried 2 times)".
    """
    tried = ""
    if isinstance(error, RetriesExhausted):
        tried = f" (tried {error.attempts} times)" if error.attempts > 1 else ""
        error = error.error

    service = f"the {stage.lower()} service"
    if is_request_too_large(error):
        return PipelineError(
            stage,
            "this meeting is too long for the AI service's per-minute limit",
            "Try a shorter recording, or use a paid Groq plan (higher limits) for long meetings.",
        )
    wait = long_wait_seconds(error)
    if wait is not None:
        daily = "per day" in str(error).lower()
        limit = "daily usage limit" if daily else "usage limit"
        return PipelineError(
            stage,
            f"the AI service's {limit} for model '{model}' has been reached",
            f"Try again in about {_describe_wait(wait)}, set {setting_prefix}_MODEL in backend/.env to another model "
            "(each model has its own limit), or use a paid Groq plan.",
        )
    if isinstance(error, openai.AuthenticationError):
        return PipelineError(stage, "the API key was rejected", f"Check {setting_prefix}_API_KEY in backend/.env.")
    if isinstance(error, openai.RateLimitError):
        return PipelineError(stage, f"{service} is busy (rate limit reached){tried}", "Wait a minute and try again.")
    if isinstance(error, openai.NotFoundError):
        return PipelineError(stage, f"the model '{model}' was not found", f"Check {setting_prefix}_MODEL in backend/.env.")
    if isinstance(error, openai.BadRequestError):
        return PipelineError(stage, f"{service} could not process the request", bad_request_fix)
    if isinstance(error, openai.APITimeoutError):  # check before APIConnectionError: it's a subclass
        return PipelineError(
            stage, f"{service} did not respond in time{tried}", "Try again in a few minutes. The AI service may be busy."
        )
    if isinstance(error, openai.APIConnectionError):
        return PipelineError(
            stage,
            f"could not reach {service}{tried}",
            f"Check your internet connection and {setting_prefix}_BASE_URL, then try again.",
        )
    return PipelineError(stage, f"{service} returned an unexpected error{tried}", "Wait a moment and try again.")


def _describe_wait(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 2:
        return "a minute"
    if minutes < 90:
        return f"{minutes} minutes"
    return f"{round(minutes / 60)} hours"
