"""Turn errors from model APIs into plain-English PipelineErrors. Shared by every stage."""

import openai

from app.pipeline.errors import PipelineError
from app.pipeline.retry import RetriesExhausted


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
