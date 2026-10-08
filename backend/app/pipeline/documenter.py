"""Stage 3: turn the refined transcript into a structured meeting record.

The model must back every decision, action item and open item with an exact quote.
Code then checks the record against the transcript:
- items whose quote isn't in the transcript are removed (likely invented);
- owners and deadlines not stated near the quote are set to None ("Unspecified").

Long meetings don't fit in one request under the free tier's per-minute token limit,
so they are documented in parts and combined (see merge.py). The checks above run
on the combined record against the whole transcript.
"""

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from app.config import Settings
from app.pipeline.errors import STAGE_DOCUMENTER, PipelineError
from app.pipeline.llm_json import ReplyCutOff, estimate_tokens, only_required, request_structured
from app.pipeline.merge import merge_parts
from app.pipeline.models import Evidence, MeetingRecord, Segment, Transcript
from app.pipeline.render import format_time
from app.pipeline.retry import DOCUMENTER_TIMEOUT, RetryCallback, llm_timeout
from app.prompt_loader import load_prompt

# Owners/deadlines may be stated a little before the quote ("Priya said... so she will..."),
# so we also look this many segments before and after the cited ones.
CONTEXT_BEFORE = 2
CONTEXT_AFTER = 1

# "Owners" that don't identify anyone. The transcript has no speaker labels.
NOT_A_NAME = {"i", "me", "we", "us", "you", "he", "she", "they", "them", "someone", "somebody",
              "anyone", "anybody", "nobody", "everyone", "everybody", "unspecified", "unknown", "tbd"}

# Half of each request's token budget is kept for the reply (the record plus the model's reasoning).
OUTPUT_SHARE = 0.5
MAX_OUTPUT_TOKENS = 8000
# If a part's reply is cut off, it is split in half and retried, down to this many segments.
MIN_PART_SEGMENTS = 8


def make_documenter_client(settings: Settings) -> OpenAI:
    """Create the API client for the documenter from settings."""
    return OpenAI(
        base_url=settings.documenter_base_url,
        api_key=settings.documenter_api_key.get_secret_value(),
        timeout=llm_timeout(DOCUMENTER_TIMEOUT),
        max_retries=0,  # retries are done (visibly) by call_with_retry
    )


def document(
    transcript: Transcript,
    client: Any,
    model: str,
    on_retry: RetryCallback | None = None,
    on_detail: Callable[[str], None] | None = None,
    max_request_tokens: int = 7500,
) -> MeetingRecord:
    """Generate the meeting record (in parts if the meeting is long), then check it against the transcript.

    `max_request_tokens` keeps each request under the service's per-minute token limit
    (Groq free tier: 8,000). Raise DOCUMENTER_MAX_REQUEST_TOKENS on a paid plan to use one request.
    """
    segments = transcript.segments
    max_output = min(MAX_OUTPUT_TOKENS, int(max_request_tokens * OUTPUT_SHARE))
    part_header_room = 100
    room_for_transcript = (
        max_request_tokens - max_output - part_header_room
        - estimate_tokens(load_prompt("documenter") + str(record_json_schema()))
    )
    if room_for_transcript < 200:
        raise PipelineError(
            STAGE_DOCUMENTER,
            f"DOCUMENTER_MAX_REQUEST_TOKENS ({max_request_tokens}) is too small to document anything",
            "Set it to at least 7500 in backend/.env.",
        )

    to_do = split_into_parts(segments, room_for_transcript)
    records: list[MeetingRecord] = []
    while to_do:
        first, end = to_do.pop(0)
        total = len(records) + 1 + len(to_do)
        if on_detail and total > 1:
            on_detail(f"Part {len(records) + 1} of {total}")
        header = "" if total == 1 else (
            f"This transcript is part {len(records) + 1} of {total} of one meeting (lines [{first}] to [{end - 1}]). "
            "Document only what happens in this part; the other parts are documented separately and "
            "combined afterwards.\n\n"
        )
        try:
            records.append(_request_record(client, model, header + format_lines(segments, first, end), max_output, on_retry))
        except ReplyCutOff:
            if end - first < 2 * MIN_PART_SEGMENTS:
                raise PipelineError(
                    STAGE_DOCUMENTER,
                    "the model's reply was too long for the output limit, even for a small part of the meeting",
                    "Try again, or raise DOCUMENTER_MAX_REQUEST_TOKENS if you are on a paid plan.",
                ) from None
            middle = (first + end) // 2
            to_do[0:0] = [(first, middle), (middle, end)]  # document the two halves instead

    if len(records) == 1:
        draft = records[0]
    else:
        if on_detail:
            on_detail("Cross-checking the parts")
        draft = merge_parts(records, client, model, max_request_tokens, on_retry)
    return verify_record(draft, segments)


def split_into_parts(segments: list[Segment], max_tokens: int) -> list[tuple[int, int]]:
    """Split segment indexes into (first, end) ranges of similar size, each fitting in `max_tokens`."""
    sizes = [estimate_tokens(format_line(i, segment)) + 1 for i, segment in enumerate(segments)]
    part_count = max(1, math.ceil(sum(sizes) / max_tokens))
    target = sum(sizes) / part_count  # aim for equal parts rather than a tiny last one

    parts: list[tuple[int, int]] = []
    first, size = 0, 0
    for i, line_size in enumerate(sizes):
        if i > first and (size + line_size > max_tokens or (size >= target and len(parts) < part_count - 1)):
            parts.append((first, i))
            first, size = i, 0
        size += line_size
    parts.append((first, len(segments)))
    return parts


def format_transcript(transcript: Transcript) -> str:
    """Numbered lines for the prompt: "[3] (00:13) Arjun proposed..."."""
    return format_lines(transcript.segments, 0, len(transcript.segments))


def format_lines(segments: list[Segment], first: int, end: int) -> str:
    """Lines first..end-1, numbered with their position in the WHOLE transcript (so evidence ids stay valid)."""
    return "\n".join(format_line(i, segments[i]) for i in range(first, end))


def format_line(index: int, segment: Segment) -> str:
    speaker = f"{segment.speaker}: " if segment.speaker else ""
    return f"[{index}] ({format_time(segment.start)}) {speaker}{segment.text}"


def record_json_schema() -> dict[str, Any]:
    """The JSON schema the model must follow. Fields with defaults are filled by code, so left out."""
    return only_required(MeetingRecord.model_json_schema())


def _request_record(
    client: Any, model: str, transcript_text: str, max_output: int, on_retry: RetryCallback | None
) -> MeetingRecord:
    return request_structured(
        client, model, load_prompt("documenter"), transcript_text, "meeting_record", record_json_schema(),
        MeetingRecord.model_validate_json, STAGE_DOCUMENTER, "DOCUMENTER", max_output, on_retry, what="a record",
    )


# --- Checking the record against the transcript ---


def verify_record(record: MeetingRecord, segments: list[Segment]) -> MeetingRecord:
    """Remove unsupported items and unstated owners/deadlines. Adds a warning for each fix."""
    fixes = Fixes()
    valid_ids = set(range(len(segments)))

    decisions = [d for d in record.decisions if _check_evidence(d.evidence, segments, f"decision '{d.text}'", fixes)]

    action_items = []
    for item in record.action_items:
        label = f"action item '{item.task}'"
        if not _check_evidence(item.evidence, segments, label, fixes):
            continue
        context = _context_text(item.evidence.segment_ids, segments)
        item.owner = _check_name(item.owner, context, "owner", label, fixes)
        item.deadline = _check_phrase(item.deadline, context, "deadline", label, fixes)
        action_items.append(item)

    open_items = []
    for item in record.open_items:
        label = f"{item.kind} '{item.text}'"
        if not _check_evidence(item.evidence, segments, label, fixes):
            continue
        context = _context_text(item.evidence.segment_ids, segments)
        item.raised_by = _check_name(item.raised_by, context, "'raised by' name", label, fixes)
        open_items.append(item)

    for topic in record.minutes:
        topic.segment_ids = [i for i in topic.segment_ids if i in valid_ids]

    counts = dict(record.fix_counts)
    for kind, number in fixes.counts.items():
        counts[kind] = counts.get(kind, 0) + number
    return record.model_copy(update={
        "decisions": decisions,
        "action_items": action_items,
        "open_items": open_items,
        "warnings": record.warnings + fixes.warnings,
        "fix_counts": counts,
    })


class Fixes:
    """The adjustments verify_record makes: a plain-English note for each, and a count per kind."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.counts: Counter[str] = Counter()

    def add(self, kind: str, warning: str) -> None:
        self.warnings.append(warning)
        self.counts[kind] += 1


def _check_evidence(evidence: Evidence, segments: list[Segment], label: str, fixes: Fixes) -> bool:
    """Find the quote in the transcript and set the evidence's segment ids and time from where it really is."""
    located = locate_quote(evidence.quote, segments, preferred_ids=evidence.segment_ids)
    if located is None:
        fixes.add("unsupported_item", f"Removed {label}: its supporting quote was not found in the transcript.")
        return False
    evidence.segment_ids = located
    evidence.start = segments[located[0]].start
    evidence.unclear = any(segments[i].unclear for i in located)
    return True


def _check_name(name: str | None, context: str, field: str, label: str, fixes: Fixes) -> str | None:
    """Keep a name only if every word of it is stated near the evidence."""
    if name is None:
        return None
    words = normalize(name).split()
    if not words or " ".join(words) in NOT_A_NAME or re.fullmatch(r"speaker \d+", " ".join(words)):
        return None  # "I", "we", "someone", "Speaker 2"... are not names; no warning needed
    context_words = set(context.split())
    if all(word in context_words for word in words):
        return name
    fixes.add("unstated_detail", f"Removed {field} '{name}' from {label}: not stated in the recording near that point.")
    return None


def _check_phrase(phrase: str | None, context: str, field: str, label: str, fixes: Fixes) -> str | None:
    """Keep a phrase (e.g. a deadline) only if it appears word for word near the evidence."""
    if phrase is None:
        return None
    normalized = normalize(phrase)
    if normalized and f" {normalized} " in f" {context} ":
        return phrase
    fixes.add("unstated_detail", f"Removed {field} '{phrase}' from {label}: not stated in the recording near that point.")
    return None


def _context_text(segment_ids: list[int], segments: list[Segment]) -> str:
    """Normalized text of the cited segments plus a few around them, including who spoke them
    (a speaker identified by name counts as stated, so "I'll do it" by Neha can be Neha's)."""
    first = max(min(segment_ids) - CONTEXT_BEFORE, 0)
    last = min(max(segment_ids) + CONTEXT_AFTER, len(segments) - 1)
    return " ".join(normalize(f"{seg.speaker or ''} {seg.text}") for seg in segments[first : last + 1])


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
