"""Stage 1: speech-to-text with Whisper through an OpenAI-compatible API (Groq by default)."""

import tempfile
from pathlib import Path
from typing import Any

import openai
from openai import OpenAI

from app.config import Settings
from app.pipeline.api_errors import explain_api_error
from app.pipeline.audio import prepare_for_stt, validate_audio_file
from app.pipeline.errors import STAGE_STT, PipelineError
from app.pipeline.models import Segment, Transcript


def make_stt_client(settings: Settings) -> OpenAI:
    """Create the API client for speech-to-text from settings."""
    return OpenAI(
        base_url=settings.stt_base_url,
        api_key=settings.stt_api_key.get_secret_value(),
        timeout=300,
        max_retries=2,
    )


def transcribe_file(upload_path: Path, client: Any, model: str, max_upload_mb: int) -> Transcript:
    """Full stage 1: check the upload, convert it, and transcribe it."""
    validate_audio_file(upload_path, max_upload_mb)
    with tempfile.TemporaryDirectory() as work_dir:
        prepared_path = prepare_for_stt(upload_path, Path(work_dir))
        return transcribe(prepared_path, client, model)


def transcribe(audio_path: Path, client: Any, model: str) -> Transcript:
    """Send audio to Whisper and return timestamped segments.

    `client` is an OpenAI client (or a fake one in tests).
    """
    try:
        with audio_path.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=model,
                file=audio_file,
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                temperature=0,
            )
    except openai.APIError as error:
        raise explain_api_error(
            error, STAGE_STT, "STT", model,
            bad_request_fix="Try exporting the recording as .mp3 or .wav and upload it again.",
        ) from None

    segments = [
        Segment(start=float(seg.start), end=float(seg.end), text=seg.text.strip())
        for seg in (getattr(response, "segments", None) or [])
        if seg.text and seg.text.strip()
    ]
    if not segments:
        raise PipelineError(
            STAGE_STT,
            "no speech was detected in the recording",
            "Check that the recording contains people talking and is not silent.",
        )
    return Transcript(segments=segments)
