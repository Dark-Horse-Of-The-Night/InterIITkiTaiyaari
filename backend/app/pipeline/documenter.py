"""Stage 3: turn the refined transcript into a structured meeting record.

The model must back every decision, action item and open item with an exact quote.
Code then checks the record against the transcript:
- items whose quote isn't in the transcript are removed (likely invented);
- owners and deadlines not stated near the quote are set to None ("Unspecified").
"""

import re
from typing import Any

import openai
from openai import OpenAI
from pydantic import ValidationError

from app.config import Settings
from app.pipeline.api_errors import explain_api_error
from app.pipeline.errors import STAGE_DOCUMENTER, PipelineError
from app.pipeline.models import Evidence, MeetingRecord, Segment, Transcript
from app.pipeline.render import format_time
from app.prompt_loader import load_prompt

MAX_ATTEMPTS = 2  # one retry if the model returns output that doesn't match the schema

# Owners/deadlines may be stated a little before the quote ("Priya said... so she will..."),
# so we also look this many segments before and after the cited ones.
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1

# "Owners" that don't identify anyone. The transcript has no speaker labels.
NOT_A_NAME = {"i", "me", "we", "us", "you", "he", "she", "they", "them", "someone", "somebody",
              "anyone", "anybody", "nobody", "everyone", "everybody", "unspecified", "unknown", "tbd"}


def make_documenter_client(settings: Settings) -> OpenAI:
    """Create the API client for the documenter from settings."""
    return OpenAI(
        base_url=settings.documenter_base_url,
        api_key=settings.documenter_api_key.get_secret_value(),
        timeout=180,
        max_retries=2,
    )


def document(transcript: Transcript, client: Any, model: str) -> MeetingRecord:
    """Generate the meeting record, then check it against the transcript."""
    draft = _request_record(client, model, format_transcript(transcript))
    return verify_record(draft, transcript.segments)


def format_transcript(transcript: Transcript) -> str:
    """Numbered lines for the prompt: "[3] (00:13) Arjun proposed..."."""
    return "\n".join(
        f"[{i}] ({format_time(seg.start)}) {seg.text}" for i, seg in enumerate(transcript.segments)
    )


def record_json_schema() -> dict[str, Any]:
    """The JSON schema the model must follow. Fields with defaults are filled by code, so left out."""
    return _only_required(MeetingRecord.model_json_schema())


def _only_required(schema: Any) -> Any:
    """Recursively drop optional properties (strict structured output needs every property required)."""
    if isinstance(schema, dict):
        cleaned = {key: _only_required(value) for key, value in schema.items()}
        if "properties" in cleaned:
            required = cleaned.get("required", [])
            cleaned["properties"] = {k: v for k, v in cleaned["properties"].items() if k in required}
        return cleaned
    if isinstance(schema, list):
        return [_only_required(item) for item in schema]
    return schema


def _request_record(client: Any, model: str, transcript_text: str) -> MeetingRecord:
    """Ask the model for the record, retrying once if the output doesn't match the schema."""
    for _ in range(MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": load_prompt("documenter")},
                    {"role": "user", "content": transcript_text},
                ],
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "meeting_record", "strict": True, "schema": record_json_schema()},
                },
            )
            return MeetingRecord.model_validate_json(response.choices[0].message.content or "")
        except ValidationError:
            continue
        except openai.BadRequestError as error:
            if error.code == "json_validate_failed":  # Groq: the model's output broke the schema
                continue
            raise explain_api_error(error, STAGE_DOCUMENTER, "DOCUMENTER", model) from None
        except openai.APIError as error:
            raise explain_api_error(error, STAGE_DOCUMENTER, "DOCUMENTER", model) from None

    raise PipelineError(
        STAGE_DOCUMENTER,
        "the model returned a record in an unexpected format twice in a row",
        "Try again. If it keeps happening, try a different DOCUMENTER_MODEL in backend/.env.",
    )


# --- Checking the record against the transcript ---


def verify_record(record: MeetingRecord, segments: list[Segment]) -> MeetingRecord:
    """Remove unsupported items and unstated owners/deadlines. Adds a warning for each fix."""
    warnings: list[str] = []
    valid_ids = set(range(len(segments)))

    decisions = [d for d in record.decisions if _check_evidence(d.evidence, segments, f"decision '{d.text}'", warnings)]

    action_items = []
    for item in record.action_items:
        label = f"action item '{item.task}'"
        if not _check_evidence(item.evidence, segments, label, warnings):
            continue
        context = _context_text(item.evidence.segment_ids, segments)
        item.owner = _check_name(item.owner, context, "owner", label, warnings)
        item.deadline = _check_phrase(item.deadline, context, "deadline", label, warnings)
        action_items.append(item)

    open_items = []
    for item in record.open_items:
        label = f"{item.kind} '{item.text}'"
        if not _check_evidence(item.evidence, segments, label, warnings):
            continue
        context = _context_text(item.evidence.segment_ids, segments)
        item.raised_by = _check_name(item.raised_by, context, "'raised by' name", label, warnings)
        open_items.append(item)

    for topic in record.minutes:
        topic.segment_ids = [i for i in topic.segment_ids if i in valid_ids]

    return record.model_copy(update={
        "decisions": decisions,
        "action_items": action_items,
        "open_items": open_items,
        "warnings": record.warnings + warnings,
    })


def _check_evidence(evidence: Evidence, segments: list[Segment], label: str, warnings: list[str]) -> bool:
    """Find the quote in the transcript and set the evidence's segment ids and time from where it really is."""
    located = locate_quote(evidence.quote, segments, preferred_ids=evidence.segment_ids)
    if located is None:
        warnings.append(f"Removed {label}: its supporting quote was not found in the transcript.")
        return False
    evidence.segment_ids = located
    evidence.start = segments[located[0]].start
    return True


def _check_name(name: str | None, context: str, field: str, label: str, warnings: list[str]) -> str | None:
    """Keep a name only if every word of it is stated near the evidence."""
    if name is None:
        return None
    words = normalize(name).split()
    if not words or " ".join(words) in NOT_A_NAME:
        return None  # "I", "we", "someone"... are not names; no warning needed
    context_words = set(context.split())
    if all(word in context_words for word in words):
        return name
    warnings.append(f"Removed {field} '{name}' from {label}: not stated in the recording near that point.")
    return None


def _check_phrase(phrase: str | None, context: str, field: str, label: str, warnings: list[str]) -> str | None:
    """Keep a phrase (e.g. a deadline) only if it appears word for word near the evidence."""
    if phrase is None:
        return None
    normalized = normalize(phrase)
    if normalized and f" {normalized} " in f" {context} ":
        return phrase
    warnings.append(f"Removed {field} '{phrase}' from {label}: not stated in the recording near that point.")
    return None


def _context_text(segment_ids: list[int], segments: list[Segment]) -> str:
    """Normalized text of the cited segments plus a few around them."""
    first = max(min(segment_ids) - CONTEXT_BEFORE, 0)
    last = min(max(segment_ids) + CONTEXT_AFTER, len(segments) - 1)
    return " ".join(normalize(seg.text) for seg in segments[first : last + 1])


def locate_quote(quote: str, segments: list[Segment], preferred_ids: list[int]) -> list[int] | None:
    """Return the ids of the segments containing the quote, or None if it isn't in the transcript.

    Matching ignores case and punctuation. A quote may span neighbouring segments.
    If the quote appears more than once, an occurrence in `preferred_ids` wins.
    """
    target = normalize(quote)
    if not target:
        return None

    # Join all segments into one string, remembering where each segment starts.
    starts, parts, position = [], [], 0
    for seg in segments:
        text = normalize(seg.text)
        starts.append(position)
        parts.append(text)
        position += len(text) + 1  # +1 for the joining space
    joined = " ".join(parts)

    matches = []
    index = joined.find(target)
    while index != -1:
        end = index + len(target)
        matches.append([i for i, s in enumerate(starts) if s < end and s + len(parts[i]) > index])
        index = joined.find(target, index + 1)

    if not matches:
        return None
    preferred = set(preferred_ids)
    return next((ids for ids in matches if preferred & set(ids)), matches[0])


def normalize(text: str) -> str:
    """Lowercase, punctuation to spaces, single spaces: "CI/CD, by Friday!" -> "ci cd by friday"."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", "", text)  # "Priya's" -> "priya"
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
