"""Give speaker labels real names where the recording makes them clear. Part of stage 2.

The model proposes names for labels like "Speaker 2", each with evidence. Code then
accepts a name only if the evidence holds up in the transcript:
- "introduced_themselves": the quote is in that speaker's own line and says
  "this is <name>", "I'm <name>", "my name is <name>"...
- "addressed_then_answered": someone else says the name ("Neha, can you...?") and the
  very next person to speak is that speaker.
Anything else stays "Speaker N". A wrong name would be invented information.
"""

import json
import logging
import re
from typing import Any, Literal

from app.pipeline.documenter import locate_quote, normalize
from app.pipeline.errors import STAGE_REFINER
from app.pipeline.llm_json import ReplyCutOff, estimate_tokens, only_required, request_structured
from app.pipeline.models import RecordModel, Segment, SpeakerName
from app.pipeline.render import format_time
from app.pipeline.retry import RetryCallback
from app.prompt_loader import load_prompt

logger = logging.getLogger("app.pipeline.speaker_names")

OUTPUT_TOKENS = 1500
LABEL_PATTERN = re.compile(r"^Speaker \d+$")
NAME_PATTERN = re.compile(r"^[A-Z][a-zA-Z'\-]{1,30}( [A-Z][a-zA-Z'\-]{1,30})?$")  # "Neha", "Mary-Jane", "Tom Lee"
NOT_A_NAME = {"Speaker", "Everyone", "Team", "Guys", "Folks", "Someone", "Nobody", "Okay", "Thanks", "Sure", "Hi", "Hello"}
# Capitalised words that often come before a comma but are not names (for the hints below).
COMMON_WORDS = NOT_A_NAME | {
    "Yes", "No", "Yeah", "Well", "So", "Good", "Great", "Right", "Alright", "Also", "And", "But", "Now", "Then",
    "First", "Second", "Third", "Next", "Finally", "Actually", "Anyway", "Last", "Quick", "Ok", "Oh", "Hey",
    "Morning", "Perfect", "Cool", "Fine", "Agreed", "Exactly", "Sorry", "Please", "Look", "Listen", "Thank",
}
HOW_TEXT = {
    "introduced_themselves": "introduced themselves",
    "addressed_then_answered": "was addressed by name and answered",
}


class NameGuess(RecordModel):
    speaker: str  # "Speaker 2"
    name: str
    evidence: Literal["introduced_themselves", "addressed_then_answered"]
    quote: str


class NameGuesses(RecordModel):
    guesses: list[NameGuess]


def name_speakers(
    segments: list[Segment],
    client: Any,
    model: str,
    max_request_tokens: int = 7500,
    on_retry: RetryCallback | None = None,
) -> tuple[list[Segment], list[SpeakerName], list[str]]:
    """Return (segments with names where proven, the names and their evidence, warnings)."""
    labels = {s.speaker for s in segments if s.speaker and LABEL_PATTERN.match(s.speaker)}
    if len(labels) == 0:
        return segments, [], []

    system_prompt = load_prompt("speaker_names")
    schema = only_required(NameGuesses.model_json_schema())
    room = max_request_tokens - OUTPUT_TOKENS - estimate_tokens(system_prompt + json.dumps(schema)) - 50
    guesses: list[NameGuess] = []
    for first, end in _parts(segments, max(room, 500)):
        text = "\n".join(f"[{i}] ({format_time(segments[i].start)}) {segments[i].speaker}: {segments[i].text}" for i in range(first, end))
        hints = addressed_name_hints(segments, first, end)
        if hints:
            text += "\n\nLines that may address someone by name (check each one; they are hints, not proof):\n" + "\n".join(hints)
        try:
            reply = request_structured(
                client, model, system_prompt, text, "speaker_names", schema, NameGuesses.model_validate_json,
                STAGE_REFINER, "REFINER", OUTPUT_TOKENS, on_retry, what="speaker names",
            )
        except ReplyCutOff:
            continue  # naming is a bonus: if this part's reply was cut off, its labels just stay unnamed
        guesses += reply.guesses

    accepted: dict[str, SpeakerName] = {}
    rejected_labels: set[str] = set()
    warnings: list[str] = []
    for guess in guesses:
        problem = check_guess(guess, segments, labels)
        if problem:
            logger.info("Rejected speaker name %s -> %s: %s", guess.speaker, guess.name, problem)
            continue
        existing = accepted.get(guess.speaker)
        if existing and existing.name != guess.name:
            rejected_labels.add(guess.speaker)  # two different names for one voice: trust neither
            continue
        if not existing:
            located = locate_quote(guess.quote, segments, preferred_ids=[])
            start = segments[located[0]].start if located else 0.0
            accepted[guess.speaker] = SpeakerName(
                label=guess.speaker, name=guess.name.strip(), how=HOW_TEXT[guess.evidence], quote=guess.quote, start=start,
            )

    # One name can't belong to two voices either.
    names_used: dict[str, list[str]] = {}
    for label, named in accepted.items():
        names_used.setdefault(named.name.lower(), []).append(label)
    for labels_with_name in names_used.values():
        if len(labels_with_name) > 1:
            rejected_labels.update(labels_with_name)
    for label in sorted(rejected_labels):
        if label in accepted:
            warnings.append(f"{label} was left unnamed because the evidence was contradictory.")
            del accepted[label]

    names = {label: named.name for label, named in accepted.items()}
    renamed = [s.model_copy(update={"speaker": names.get(s.speaker or "", s.speaker)}) for s in segments]
    ordered = sorted(accepted.values(), key=lambda n: int(n.label.split()[-1]))
    return renamed, ordered, warnings


def check_guess(guess: NameGuess, segments: list[Segment], labels: set[str]) -> str | None:
    """Return why the evidence doesn't hold up, or None if the name is proven."""
    name = guess.name.strip()
    if guess.speaker not in labels:
        return "unknown speaker label"
    if not NAME_PATTERN.match(name) or name.split()[0] in NOT_A_NAME:
        return "not a person's name"
    located = locate_quote(guess.quote, segments, preferred_ids=[])
    if located is None:
        return "quote not in the transcript"
    if not re.search(rf"\b{re.escape(normalize(name))}\b", normalize(guess.quote)):
        return "the quote doesn't contain the name"
    quote_speaker = segments[located[0]].speaker

    if guess.evidence == "introduced_themselves":
        if quote_speaker != guess.speaker:
            return "the introduction was said by someone else"
        # normalize() turns "I'm Tom" into "i m tom" and "it's" into "it s".
        introduction = rf"\b(this is|i m|im|i am|my name is|it s|its|here is|here s)\s+{re.escape(normalize(name))}\b"
        return None if re.search(introduction, normalize(guess.quote)) else "the quote isn't an introduction"

    # addressed_then_answered: someone else says the name TO someone ("Neha, can you…?",
    # "…take a look, Neha?"), and the next different voice is this speaker.
    if quote_speaker == guess.speaker:
        return "a speaker can't be addressed by their own line"
    said_to = rf"(\b{re.escape(name)}\s*[,?!])|(,\s*{re.escape(name)}\s*[.?!]?\s*$)"
    if not re.search(said_to, guess.quote.strip()):
        return "the name is only mentioned, not said to someone"
    for segment in segments[located[-1] + 1 :]:
        if segment.speaker != quote_speaker:
            return None if segment.speaker == guess.speaker else "someone else answered"
    return "nobody answered"


def addressed_name_hints(segments: list[Segment], first: int, end: int) -> list[str]:
    """Lines where a capitalised word is followed by a comma or question mark, e.g. "Priya, how did…".

    Only a hint for the model (which still has to give evidence, which code still checks).
    """
    hints = []
    for i in range(first, end):
        candidates = re.findall(r"(?:^|[.!?]\s+|,\s*)([A-Z][a-z]{1,30})\s*[,?!]", segments[i].text)
        names = [c for c in candidates if c not in COMMON_WORDS]
        if names:
            hints.append(f"[{i}] {', '.join(dict.fromkeys(names))}")
    return hints


def _parts(segments: list[Segment], max_tokens: int) -> list[tuple[int, int]]:
    parts, first, size = [], 0, 0
    for i, segment in enumerate(segments):
        line = estimate_tokens(f"[{i}] (00:00) {segment.speaker}: {segment.text}") + 1
        if i > first and size + line > max_tokens:
            parts.append((first, i))
            first, size = i, 0
        size += line
    parts.append((first, len(segments)))
    return parts
