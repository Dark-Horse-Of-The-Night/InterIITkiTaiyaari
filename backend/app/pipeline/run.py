"""Run the three stages in order: speech-to-text -> refiner -> documenter.

This is the only place the stage order is defined. The web layer and the
scripts both call run_pipeline().
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.pipeline.documenter import document, make_documenter_client
from app.pipeline.errors import STAGE_DOCUMENTER, STAGE_REFINER, STAGE_STT
from app.pipeline.models import MeetingRecord, RefinedTranscript, Transcript
from app.pipeline.refiner import make_refiner_client, refine
from app.pipeline.render import record_to_markdown
from app.pipeline.stt import make_stt_client, transcribe_file

STAGES = [STAGE_STT, STAGE_REFINER, STAGE_DOCUMENTER]

# Called as on_progress(stage, "running", None) and on_progress(stage, "done", seconds).
ProgressCallback = Callable[[str, Literal["running", "done"], float | None], None]
# Called as on_note(stage, "Slow response from the service. Retrying (attempt 2 of 2)…").
NoteCallback = Callable[[str, str], None]
# Called as on_detail(stage, "Part 2 of 6") to show where a long stage has got to.
DetailCallback = Callable[[str, str], None]

T = TypeVar("T")


@dataclass
class PipelineClients:
    """The API client for each stage (fakes in tests)."""

    stt: Any
    refiner: Any
    documenter: Any

    @classmethod
    def from_settings(cls, settings: Settings) -> "PipelineClients":
        return cls(
            stt=make_stt_client(settings),
            refiner=make_refiner_client(settings),
            documenter=make_documenter_client(settings),
        )


class MeetingResult(BaseModel):
    """Everything the pipeline produces for one recording."""

    raw_transcript: Transcript
    refined_transcript: RefinedTranscript
    record: MeetingRecord
    markdown: str  # generated from `record`, so it always matches the JSON
    models: dict[str, str]
    timings_seconds: dict[str, float]


def run_pipeline(
    audio_path: Path,
    settings: Settings,
    clients: PipelineClients,
    glossary: list[str] | None = None,
    on_progress: ProgressCallback | None = None,
    on_note: NoteCallback | None = None,
    on_detail: DetailCallback | None = None,
) -> MeetingResult:
    """Run all three stages on one audio file. Raises PipelineError if a stage fails."""
    timings: dict[str, float] = {}

    def notes_for(stage: str) -> Callable[[str], None] | None:
        return (lambda note: on_note(stage, note)) if on_note else None

    def details_for(stage: str) -> Callable[[str], None] | None:
        return (lambda detail: on_detail(stage, detail)) if on_detail else None

    def run_stage(stage: str, work: Callable[[], T]) -> T:
        if on_progress:
            on_progress(stage, "running", None)
        started = time.monotonic()
        result = work()
        timings[stage] = round(time.monotonic() - started, 1)
        if on_progress:
            on_progress(stage, "done", timings[stage])
        return result

    raw = run_stage(
        STAGE_STT,
        lambda: transcribe_file(
            audio_path, clients.stt, settings.stt_model, settings.max_upload_mb, notes_for(STAGE_STT),
            settings.max_audio_minutes, details_for(STAGE_STT),
        ),
    )
    refined = run_stage(
        STAGE_REFINER,
        lambda: refine(
            raw, clients.refiner, settings.refiner_model, glossary, notes_for(STAGE_REFINER), details_for(STAGE_REFINER)
        ),
    )
    record = run_stage(
        STAGE_DOCUMENTER,
        lambda: document(refined, clients.documenter, settings.documenter_model, notes_for(STAGE_DOCUMENTER)),
    )

    return MeetingResult(
        raw_transcript=raw,
        refined_transcript=refined,
        record=record,
        markdown=record_to_markdown(record),
        models={
            STAGE_STT: settings.stt_model,
            STAGE_REFINER: settings.refiner_model,
            STAGE_DOCUMENTER: settings.documenter_model,
        },
        timings_seconds=timings,
    )
