"""Stage 1: speech-to-text with Whisper through an OpenAI-compatible API (Groq by default)."""

import logging
import math
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openai
from openai import OpenAI

from app.config import Settings
from app.pipeline.api_errors import explain_api_error
from app.pipeline.audio import FULL_WAV_NAME, prepare_chunks, validate_audio_file
from app.pipeline.errors import STAGE_STT, PipelineError
from app.pipeline.models import Segment, Transcript
from app.pipeline.retry import RetriesExhausted, RetryCallback, call_with_retry, llm_timeout, stt_timeout

# Called with progress details like "Part 2 of 6".
DetailCallback = Callable[[str], None]

logger = logging.getLogger("app.pipeline.stt")

# Glossary hint for Whisper: it only reads the last ~224 tokens of a prompt.
MAX_HINT_CHARS = 600
# A stretch is "unclear" (worth a listen) when Whisper's own scores say it was unsure.
# Tuned on our samples: clean speech never went below -0.32; heavy noise that dropped a sentence scored -0.59.
UNCLEAR_LOGPROB = -0.4
UNCLEAR_NO_SPEECH = 0.6  # probably not speech, so any words there may be invented
UNCLEAR_COMPRESSION = 2.4  # Whisper's standard sign of repeating itself


def make_stt_client(settings: Settings) -> OpenAI:
    """Create the API client for speech-to-text from settings."""
    return OpenAI(
        base_url=settings.stt_base_url,
        api_key=settings.stt_api_key.get_secret_value(),
        timeout=llm_timeout(300),  # replaced per call by stt_timeout(), sized to the audio
        max_retries=0,  # retries are done (visibly) by call_with_retry
    )


def transcribe_file(
    upload_path: Path,
    client: Any,
    model: str,
    max_upload_mb: int,
    on_retry: RetryCallback | None = None,
    max_audio_minutes: int | None = None,
    on_detail: DetailCallback | None = None,
    speaker_embedder: Any = None,
    glossary: list[str] | None = None,
) -> Transcript:
    """Full stage 1: check the upload, convert and split it, transcribe each part in order,
    then (if a speaker model is available) label who spoke each segment.

    `glossary` terms are given to Whisper as a hint, so they are spelled right from the start."""
    duration = validate_audio_file(upload_path, max_upload_mb, max_audio_minutes)
    with tempfile.TemporaryDirectory() as work_dir:
        if on_detail:
            on_detail("Preparing the audio")
        chunks = prepare_chunks(upload_path, duration, Path(work_dir), keep_wav=speaker_embedder is not None)
        segments: list[Segment] = []
        for number, chunk in enumerate(chunks, start=1):
            if on_detail and len(chunks) > 1:
                on_detail(f"Part {number} of {len(chunks)}")
            part = transcribe(
                chunk.path, client, model, chunk.end - chunk.start, on_retry, allow_silence=len(chunks) > 1, glossary=glossary
            )
            # Shift the part's timestamps so they count from the start of the whole recording.
            segments += [
                s.model_copy(update={"start": s.start + chunk.start, "end": s.end + chunk.start}) for s in part.segments
            ]
        if speaker_embedder is not None and segments:
            if on_detail:
                on_detail("Identifying who is speaking")
            segments = _label_speakers(segments, Path(work_dir) / FULL_WAV_NAME, speaker_embedder)
    if not segments:
        raise PipelineError(
            STAGE_STT,
            "no speech was detected in the recording",
            "Check that the recording contains people talking and is not silent.",
        )
    return Transcript(segments=segments)


def transcribe(
    audio_path: Path,
    client: Any,
    model: str,
    audio_seconds: float = 0,
    on_retry: RetryCallback | None = None,
    allow_silence: bool = False,
    glossary: list[str] | None = None,
) -> Transcript:
    """Send audio to Whisper and return timestamped segments.

    `client` is an OpenAI client (or a fake one in tests). `allow_silence` lets one
    silent part of a long recording through (the whole recording is checked instead).
    """
    hint = glossary_hint(glossary)

    def send() -> Any:
        with audio_path.open("rb") as audio_file:  # reopened on each retry
            return client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                temperature=0,
                timeout=stt_timeout(audio_seconds),
                **({"prompt": hint} if hint else {}),
            )

    try:
        response = call_with_retry(send, STAGE_STT, on_retry)
    except (openai.APIError, RetriesExhausted) as error:
        raise explain_api_error(
            error, STAGE_STT, "STT", model,
            bad_request_fix="Try exporting the recording as .mp3 or .wav and upload it again.",
        ) from None

    segments = [
        Segment(start=float(seg.start), end=float(seg.end), text=seg.text.strip(), **confidence_fields(seg))
        for seg in (getattr(response, "segments", None) or [])
        if seg.text and seg.text.strip()
    ]
    if not segments and not allow_silence:
        raise PipelineError(
            STAGE_STT,
            "no speech was detected in the recording",
            "Check that the recording contains people talking and is not silent.",
        )
    return Transcript(segments=segments)


def glossary_hint(glossary: list[str] | None) -> str | None:
    """Turn the user's terms into a short Whisper prompt, or None if there are none.

    Whisper reads only the last ~224 tokens of a prompt, so the list is cut to fit.
    """
    terms = [term.strip() for term in glossary or [] if term.strip()]
    kept: list[str] = []
    for term in terms:
        if len(", ".join(kept + [term])) > MAX_HINT_CHARS:
            break
        kept.append(term)
    return f"Terms used in this meeting: {', '.join(kept)}." if kept else None


def confidence_fields(whisper_segment: Any) -> dict[str, Any]:
    """Read Whisper's own confidence for a segment and decide if it is worth a listen.

    avg_logprob: average log-probability of the words (0 = certain). Clean speech scores about
    -0.1 to -0.32; garbled or noisy stretches drop lower. no_speech_prob: chance it was not speech
    (text there may be invented). compression_ratio: high when Whisper repeats itself.
    """
    avg_logprob = getattr(whisper_segment, "avg_logprob", None)
    if avg_logprob is None:
        return {}  # this provider doesn't report confidence
    no_speech = getattr(whisper_segment, "no_speech_prob", None) or 0.0
    compression = getattr(whisper_segment, "compression_ratio", None) or 0.0
    unclear = (
        avg_logprob < UNCLEAR_LOGPROB
        or no_speech > UNCLEAR_NO_SPEECH
        or compression > UNCLEAR_COMPRESSION
    )
    return {"confidence": round(math.exp(avg_logprob), 2), "unclear": unclear}


def _label_speakers(segments: list[Segment], wav_path: Path, embedder: Any) -> list[Segment]:
    """Speaker labels are a bonus: if labelling fails, keep the transcript without them."""
    from app.pipeline.speakers import label_speakers

    try:
        return label_speakers(segments, wav_path, embedder)
    except Exception:
        logger.exception("Speaker labelling failed; continuing without speaker labels")
        return segments
