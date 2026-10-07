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
) -> MeetingResult:
    """Run all three stages on one audio file. Raises PipelineError if a stage fails."""
    timings: dict[str, float] = {}

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
        lambda: transcribe_file(audio_path, clients.stt, settings.stt_model, settings.max_upload_mb),
    )
    refined = run_stage(STAGE_REFINER, lambda: refine(raw, clients.refiner, settings.refiner_model, glossary))
    record = run_stage(STAGE_DOCUMENTER, lambda: document(refined, clients.documenter, settings.documenter_model))

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
