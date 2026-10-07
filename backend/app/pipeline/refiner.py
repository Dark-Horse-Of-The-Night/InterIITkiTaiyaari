"""Stage 2: refine the transcript — fix misrecognised technical terms, nothing else.

The LLM proposes corrected text for each segment, then code checks every edit
(numbers, negation, commitment words, edit size). Edits that fail a check are
discarded and the original wording is kept, with a warning. Names cannot be fully
checked in code (fixing "cooper netties" legitimately removes capitalised words),
so they are protected by the prompt and the edit-size check.
"""

import difflib
import json
import re
from collections import Counter
from typing import Any

import openai
from openai import OpenAI

from app.config import Settings
from app.pipeline.api_errors import explain_api_error
from app.pipeline.errors import STAGE_REFINER, PipelineError
from app.pipeline.models import Correction, RefinedTranscript, Segment, Transcript
from app.pipeline.render import format_time
from app.prompt_loader import load_prompt

BATCH_SIZE = 40  # segments per request, so long meetings don't hit output limits
MAX_ATTEMPTS = 2  # one retry if the model returns badly formatted output

# An edit counts as a rewrite if it changes more than this many words (or this
# fraction of them) AND the text no longer looks similar letter by letter.
# Term fixes like "jason web tokens" -> "JSON Web Tokens" stay similar; rewrites don't.
MAX_CHANGED_WORDS = 3
MAX_CHANGED_FRACTION = 0.4
MIN_SIMILARITY = 0.85

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000",
    "million": "1000000", "billion": "1000000000",
}
NEGATION_WORDS = {"not", "no", "never", "nobody", "none", "nothing", "nowhere", "neither", "nor", "cannot", "without"}
# Words that carry commitment or certainty; changing them changes who promised what.
COMMITMENT_WORDS = {
    "will", "would", "shall", "should", "must", "might", "may", "can", "could",
    "maybe", "perhaps", "probably", "definitely", "decided", "agreed", "approved",
    "proposed", "suggested", "promised", "committed",
}


class BadModelOutput(Exception):
    """The model's reply was not the JSON shape we asked for."""


def make_refiner_client(settings: Settings) -> OpenAI:
    """Create the API client for the refiner from settings."""
    return OpenAI(
        base_url=settings.refiner_base_url,
        api_key=settings.refiner_api_key.get_secret_value(),
        timeout=120,
        max_retries=2,
    )


def refine(transcript: Transcript, client: Any, model: str, glossary: list[str] | None = None) -> RefinedTranscript:
    """Correct misrecognised terms in every segment, keeping timestamps and meaning."""
    system_prompt = build_system_prompt(glossary)
    segments = transcript.segments
    refined_texts: list[str] = []
    corrections: list[Correction] = []
    warnings: list[str] = []

    for batch_start in range(0, len(segments), BATCH_SIZE):
        batch = segments[batch_start : batch_start + BATCH_SIZE]
        ids = list(range(batch_start, batch_start + len(batch)))
        proposed = _request_batch(client, model, system_prompt, ids, batch)

        for segment_id, segment in zip(ids, batch):
            new_text = proposed[segment_id]
            problem = check_edit(segment.text, new_text)
            if problem:
                warnings.append(
                    f"Segment {segment_id + 1} ({format_time(segment.start)}): kept the original wording "
                    f"because the suggested edit {problem}."
                )
                new_text = segment.text
            refined_texts.append(new_text)
            corrections.extend(find_corrections(segment_id, segment.text, new_text))

    refined_segments = [
        Segment(start=seg.start, end=seg.end, text=text) for seg, text in zip(segments, refined_texts)
    ]
    return RefinedTranscript(segments=refined_segments, corrections=corrections, warnings=warnings)


def build_system_prompt(glossary: list[str] | None) -> str:
    """Fill the glossary slot in the refiner prompt."""
    terms = [term.strip() for term in (glossary or []) if term.strip()]
    glossary_text = ", ".join(terms) if terms else "(none provided)"
    return load_prompt("refiner").replace("{{GLOSSARY}}", glossary_text)


def _request_batch(
    client: Any, model: str, system_prompt: str, ids: list[int], batch: list[Segment]
) -> dict[int, str]:
    """Ask the model to refine one batch. Returns {segment id: proposed text}."""
    user_message = json.dumps(
        {"segments": [{"id": i, "text": seg.text} for i, seg in zip(ids, batch)]}, ensure_ascii=False
    )
    for _ in range(MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            return parse_reply(response.choices[0].message.content, ids)
        except BadModelOutput:
            continue
        except openai.BadRequestError as error:
            if error.code == "json_validate_failed":  # Groq: the model produced invalid JSON
                continue
            raise explain_api_error(error, STAGE_REFINER, "REFINER", model) from None
        except openai.APIError as error:
            raise explain_api_error(error, STAGE_REFINER, "REFINER", model) from None

    raise PipelineError(
        STAGE_REFINER,
        "the model returned an unexpected format twice in a row",
        "Try again. If it keeps happening, try a different REFINER_MODEL in backend/.env.",
    )


def parse_reply(content: str | None, expected_ids: list[int]) -> dict[int, str]:
    """Check the reply has exactly the segment ids we sent, each with text."""
    try:
        data = json.loads(content or "")
        result = {int(item["id"]): str(item["text"]) for item in data["segments"]}
    except (ValueError, KeyError, TypeError) as error:
        raise BadModelOutput(str(error)) from None
    if sorted(result) != sorted(expected_ids) or len(data["segments"]) != len(expected_ids):
        raise BadModelOutput("segment ids do not match")
    return result


def check_edit(original: str, refined: str) -> str | None:
    """Return a reason the edit is unsafe, or None if it is fine."""
    if not refined.strip():
        return "was empty"
    if number_tokens(original) != number_tokens(refined):
        return "changed a number"
    if negation_tokens(original) != negation_tokens(refined):
        return "changed a negation"
    if commitment_tokens(original) != commitment_tokens(refined):
        return "changed a commitment word (such as will, should or decided)"
    changed = count_changed_words(original, refined)
    many_words_changed = changed > max(MAX_CHANGED_WORDS, MAX_CHANGED_FRACTION * len(original.split()))
    if many_words_changed and letter_similarity(original, refined) < MIN_SIMILARITY:
        return "rewrote too much of the segment"
    return None


def number_tokens(text: str) -> Counter[str]:
    """All numbers in the text, with number words converted to digits ("five" -> "5")."""
    words = re.findall(r"[a-z]+|\d+", text.lower())
    return Counter(NUMBER_WORDS.get(word, word) for word in words if word.isdigit() or word in NUMBER_WORDS)


def negation_tokens(text: str) -> Counter[str]:
    """All negation words in the text, including contractions like "haven't"."""
    words = _lowercase_words(text)
    return Counter("n't" if word.endswith("n't") else word for word in words if word.endswith("n't") or word in NEGATION_WORDS)


def commitment_tokens(text: str) -> Counter[str]:
    """All commitment/certainty words, with "we'll" counted as "will"."""
    words = _lowercase_words(text)
    return Counter("will" if word.endswith("'ll") else word for word in words if word.endswith("'ll") or word in COMMITMENT_WORDS)


def _lowercase_words(text: str) -> list[str]:
    """Lowercase words, keeping apostrophes (curly or straight) so "haven't" stays one word."""
    return re.findall(r"[a-z']+", text.lower().replace("\u2019", "'"))


def letter_similarity(original: str, refined: str) -> float:
    """0-1 similarity of the letters, ignoring case and spaces ("oh auth" ~ "OAuth")."""
    original_letters = "".join(original.lower().split())
    refined_letters = "".join(refined.lower().split())
    return difflib.SequenceMatcher(a=original_letters, b=refined_letters, autojunk=False).ratio()


def count_changed_words(original: str, refined: str) -> int:
    """How many words were replaced, removed or added."""
    matcher = difflib.SequenceMatcher(a=original.split(), b=refined.split(), autojunk=False)
    return sum(
        max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
    )


def find_corrections(segment_id: int, original: str, refined: str) -> list[Correction]:
    """List each changed span of words, e.g. "CICD" -> "CI/CD"."""
    old_words, new_words = original.split(), refined.split()
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    return [
        Correction(segment_id=segment_id, before=" ".join(old_words[i1:i2]), after=" ".join(new_words[j1:j2]))
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]
