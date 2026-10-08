"""Data shapes passed between pipeline stages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Segment(BaseModel):
    """One timestamped piece of speech. Times are in seconds from the start."""

    start: float
    end: float
    text: str
    # Who spoke: a name if one was identified from the audio, else a label like "Speaker 2".
    # None when speaker labelling is off or unavailable.
    speaker: str | None = None
    # How sure Whisper was about this stretch of audio (0-1), and whether that is low enough to
    # be worth a listen. Whisper scores ~30-second windows, so neighbouring segments share a score.
    confidence: float | None = None
    unclear: bool = False


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


class SpeakerName(BaseModel):
    """A speaker label that was given a real name, and the evidence for it."""

    label: str  # e.g. "Speaker 2"
    name: str  # e.g. "Neha"
    how: str  # "introduced themselves" or "was addressed by name and answered"
    quote: str  # the words that show it
    start: float  # when the quote was said (seconds)


class RefinedTranscript(Transcript):
    """The output of the refiner: the same segments (same timestamps) with terms corrected.

    `corrections` is computed by comparing old and new text, not taken from the model.
    `warnings` lists segments where an edit was rejected and the original wording kept.
    `speaker_names` lists labels replaced by real names; other labels stay "Speaker N".
    `blocked_edits` counts rejected edits by reason, e.g. {"changed a number": 1}.
    """

    corrections: list[Correction] = []
    warnings: list[str] = []
    speaker_names: list[SpeakerName] = []
    blocked_edits: dict[str, int] = {}


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
    unclear: bool = False  # set by code: the quote comes from audio Whisper was unsure about


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
    # How many fixes of each kind the checks made, e.g. {"unsupported_item": 1}. Filled in by code.
    fix_counts: dict[str, int] = {}


# --- Computed by code after the documenter (no model involved) ---


class TrustReport(BaseModel):
    """What the automatic checks verified, removed or blocked for this recording."""

    items_verified: int  # decisions, tasks and open items whose quote was found in the transcript
    items_removed: int  # items dropped because their quote was not in the transcript
    details_removed: int  # owners, deadlines or names the model guessed but nobody said
    items_superseded: int  # long meetings: proposals later accepted, decisions later changed
    owners_unspecified: int  # tasks left without an owner because none was stated
    deadlines_unspecified: int
    corrections: int  # term fixes the refiner made
    edits_blocked: dict[str, int]  # refiner edits rejected, by reason
    speakers_named: int  # speakers named from evidence in the recording
    speakers_unnamed: int  # speakers kept as "Speaker N"
    unclear_segments: int  # transcript lines from audio Whisper was unsure about
    unclear_items: int  # record items whose quote comes from such audio
    notes: list[str]  # every adjustment, in plain English


class SpeakerStats(BaseModel):
    speaker: str
    seconds: float  # total talk time
    share: float  # fraction of all talk time (0-1)
    turns: int  # times they took the floor
    longest_turn_seconds: float
    questions: int  # lines they spoke that end with "?"


class SpeakingTurn(BaseModel):
    speaker: str
    start: float
    end: float


class SpeakingStats(BaseModel):
    """Who spoke how much, worked out from the speaker labels and timestamps."""

    speakers: list[SpeakerStats]  # most talk time first
    timeline: list[SpeakingTurn]  # consecutive lines by the same speaker joined into one turn
