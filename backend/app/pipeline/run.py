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
from app.pipeline.models import MeetingRecord, RefinedTranscript, SpeakingStats, Transcript, TrustReport
from app.pipeline.refiner import make_refiner_client, refine
from app.pipeline.speaker_names import name_speakers
from app.pipeline.speakers import load_embedder
from app.pipeline.stats import build_speaking_stats
from app.pipeline.render import record_to_json, record_to_markdown
from app.pipeline.stt import make_stt_client, transcribe_file
from app.pipeline.trust import build_trust_report

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
    speakers: Any = None  # voice model for speaker labels (None = no labels)

    @classmethod
    def from_settings(cls, settings: Settings) -> "PipelineClients":
        return cls(
            stt=make_stt_client(settings),
            refiner=make_refiner_client(settings),
            documenter=make_documenter_client(settings),
            speakers=load_embedder(settings.speaker_model_dir) if settings.speaker_labels else None,
        )


class MeetingResult(BaseModel):
    """Everything the pipeline produces for one recording."""

    raw_transcript: Transcript
    refined_transcript: RefinedTranscript
    record: MeetingRecord
    trust: TrustReport  # what the automatic checks verified, removed or blocked (code only)
    speaking: SpeakingStats | None  # who spoke how much; None without speaker labels (code only)
    markdown: str  # generated from the same data as `record_json`, so the two always match
    record_json: str
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
    on_refined: Callable[[RefinedTranscript], None] | None = None,
) -> MeetingResult:
    """Run all three stages on one audio file. Raises PipelineError if a stage fails.

    `on_refined` receives the refined transcript as soon as stage 2 finishes, so the app can
    show the corrections while the documenter is still working.
    """
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
            settings.max_audio_minutes, details_for(STAGE_STT), clients.speakers, glossary,
        ),
    )
    def refine_stage() -> RefinedTranscript:
        refined = refine(
            raw, clients.refiner, settings.refiner_model, glossary, notes_for(STAGE_REFINER), details_for(STAGE_REFINER)
        )
        if not any(segment.speaker for segment in refined.segments):
            return refined
        if on_detail:
            on_detail(STAGE_REFINER, "Identifying speaker names")
        segments, names, warnings = name_speakers(
            refined.segments, clients.refiner, settings.refiner_model,
            settings.documenter_max_request_tokens, notes_for(STAGE_REFINER),
        )
        return refined.model_copy(update={"segments": segments, "speaker_names": names, "warnings": refined.warnings + warnings})

    refined = run_stage(STAGE_REFINER, refine_stage)
    if on_refined:
        on_refined(refined)
    record = run_stage(
        STAGE_DOCUMENTER,
        lambda: document(
            refined, clients.documenter, settings.documenter_model, notes_for(STAGE_DOCUMENTER),
            details_for(STAGE_DOCUMENTER), settings.documenter_max_request_tokens,
        ),
    )

    trust = build_trust_report(raw, refined, record)
    speaking = build_speaking_stats(refined.segments)
    return MeetingResult(
        raw_transcript=raw,
        refined_transcript=refined,
        record=record,
        trust=trust,
        speaking=speaking,
        markdown=record_to_markdown(record, trust=trust, speaking=speaking),
        record_json=record_to_json(record, trust, speaking),
        models={
            STAGE_STT: settings.stt_model,
            STAGE_REFINER: settings.refiner_model,
            STAGE_DOCUMENTER: settings.documenter_model,
        },
        timings_seconds=timings,
    )
