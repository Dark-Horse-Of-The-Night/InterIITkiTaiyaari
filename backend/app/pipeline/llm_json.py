"""Ask a model for JSON that follows a schema, with retries for malformed or cut-off replies."""

import logging
import math
from collections.abc import Callable
from typing import Any, TypeVar

import openai
from pydantic import ValidationError

from app.pipeline.api_errors import explain_api_error
from app.pipeline.errors import PipelineError
from app.pipeline.retry import RetriesExhausted, RetryCallback, call_with_retry

logger = logging.getLogger("app.pipeline.llm_json")

MAX_ATTEMPTS = 2  # one retry if the reply doesn't match the schema
CHARS_PER_TOKEN = 3.5  # rough and slightly cautious for English text and JSON

T = TypeVar("T")


class ReplyCutOff(Exception):
    """The reply hit the output-token limit before it was complete. The caller can retry with less input."""


def estimate_tokens(text: str) -> int:
    """A quick token estimate, good enough to keep requests under a size limit."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def request_structured(
    client: Any,
    model: str,
    system_prompt: str,
    user_message: str,
    schema_name: str,
    schema: dict[str, Any],
    parse: Callable[[str], T],
    stage: str,
    setting_prefix: str,
    max_output_tokens: int,
    on_retry: RetryCallback | None = None,
    what: str = "output",
) -> T:
    """Call the model with strict structured output and return `parse(reply)`.

    Raises PipelineError (plain English) if the API fails or the reply is malformed twice.
    """
    for _ in range(MAX_ATTEMPTS):
        try:
            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0,
                    max_completion_tokens=max_output_tokens,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                    },
                ),
                stage,
                on_retry,
            )
            choice = response.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                logger.warning("%s: reply cut off at the %d-token limit", stage, max_output_tokens)
                raise ReplyCutOff()  # the same request would be cut off again
            return parse(choice.message.content or "")
        except ValidationError as error:
            logger.warning("%s: reply didn't match the schema: %s", stage, str(error)[:300])
            continue
        except openai.BadRequestError as error:
            if error.code == "json_validate_failed":  # Groq: the model's output broke the schema
                if "max completion tokens" in str(error).lower():  # Groq's wording for a cut-off reply
                    logger.warning("%s: reply cut off at the %d-token limit", stage, max_output_tokens)
                    raise ReplyCutOff() from None
                logger.warning("%s: Groq rejected the reply as invalid JSON", stage)
                continue
            raise explain_api_error(error, stage, setting_prefix, model) from None
        except (openai.APIError, RetriesExhausted) as error:
            raise explain_api_error(error, stage, setting_prefix, model) from None

    raise PipelineError(
        stage,
        f"the model returned {what} in an unexpected format twice in a row",
        f"Try again. If it keeps happening, try a different {setting_prefix}_MODEL in backend/.env.",
    )


def only_required(schema: Any) -> Any:
    """Recursively drop optional properties (strict structured output needs every property required).

    Fields with defaults are filled in by code, never by the model.
    """
    if isinstance(schema, dict):
        cleaned = {key: only_required(value) for key, value in schema.items()}
        if "properties" in cleaned:
            required = cleaned.get("required", [])
            cleaned["properties"] = {k: v for k, v in cleaned["properties"].items() if k in required}
        return cleaned
    if isinstance(schema, list):
        return [only_required(item) for item in schema]
    return schema
