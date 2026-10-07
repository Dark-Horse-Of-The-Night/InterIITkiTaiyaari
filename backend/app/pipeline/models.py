"""Data shapes passed between pipeline stages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Segment(BaseModel):
    """One timestamped piece of speech. Times are in seconds from the start."""

    start: float
    end: float
    text: str


class Transcript(BaseModel):
    """The output of speech-to-text: an ordered list of segments."""

    segments: list[Segment]

    @property
    def text(self) -> str:
        """The whole transcript as one string."""
        return " ".join(segment.text for segment in self.segments)


class Correction(BaseModel):
    """One change the refiner made, e.g. "CICD" -> "CI/CD" in segment 4."""

    segment_id: int
    before: str
    after: str


class RefinedTranscript(Transcript):
    """The output of the refiner: the same segments (same timestamps) with terms corrected.

    `corrections` is computed by comparing old and new text, not taken from the model.
    `warnings` lists segments where an edit was rejected and the original wording kept.
    """

    corrections: list[Correction] = []
    warnings: list[str] = []


# --- Meeting record (output of the documenter) ---
# Fields WITH a default (start, warnings) are filled in by code, never by the model:
# they are left out of the JSON schema the model is asked to follow.


class RecordModel(BaseModel):
    """Base for record parts: unknown fields are rejected, so the model can't add extras."""

    model_config = ConfigDict(extra="forbid")


class Evidence(RecordModel):
    """Where an item came from: segment ids and an exact quote from those segments."""

    segment_ids: list[int]
    quote: str
    start: float | None = None  # seconds; set by code from the first segment


class Topic(RecordModel):
    topic: str
    points: list[str]
    segment_ids: list[int]


class Decision(RecordModel):
    text: str
    evidence: Evidence


class ActionItem(RecordModel):
    task: str
    owner: str | None  # None = not stated in the recording; shown as "Unspecified"
    deadline: str | None  # the phrase as spoken, e.g. "by Friday"; None if not stated
    evidence: Evidence


class OpenItem(RecordModel):
    """A proposal or question that was raised but not agreed. Never a decision or task."""

    text: str
    kind: Literal["proposal", "question"]
    raised_by: str | None
    evidence: Evidence


class MeetingRecord(RecordModel):
    """The structured meeting record. Markdown and JSON are both generated from this."""

    summary: str
    minutes: list[Topic]
    decisions: list[Decision]
    action_items: list[ActionItem]
    open_items: list[OpenItem]
    warnings: list[str] = []  # problems the code checks found and fixed
