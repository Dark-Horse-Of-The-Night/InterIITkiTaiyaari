"""Data shapes passed between pipeline stages."""

from pydantic import BaseModel


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
