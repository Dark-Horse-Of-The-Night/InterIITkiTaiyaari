"""Turn errors from model APIs into plain-English PipelineErrors. Shared by every stage."""

import openai

from app.pipeline.errors import PipelineError


def explain_api_error(
    error: openai.APIError,
    stage: str,
    setting_prefix: str,
    model: str,
    bad_request_fix: str = "Try again. If it keeps happening, the input may be too long for this model.",
) -> PipelineError:
    """Build a user-facing error saying which stage failed and which setting to check.

    `setting_prefix` is the start of the .env names for this stage, e.g. "STT" or "REFINER".
    """
    service = f"the {stage.lower()} service"
    if isinstance(error, openai.AuthenticationError):
        return PipelineError(stage, "the API key was rejected", f"Check {setting_prefix}_API_KEY in backend/.env.")
    if isinstance(error, openai.RateLimitError):
        return PipelineError(stage, f"{service} is busy (rate limit reached)", "Wait a minute and try again.")
    if isinstance(error, openai.NotFoundError):
        return PipelineError(stage, f"the model '{model}' was not found", f"Check {setting_prefix}_MODEL in backend/.env.")
    if isinstance(error, openai.BadRequestError):
        return PipelineError(stage, f"{service} could not process the request", bad_request_fix)
    if isinstance(error, openai.APIConnectionError):  # also covers timeouts
        return PipelineError(
            stage,
            f"could not reach {service}",
            f"Check your internet connection and {setting_prefix}_BASE_URL, then try again.",
        )
    return PipelineError(stage, f"{service} returned an unexpected error", "Wait a moment and try again.")
