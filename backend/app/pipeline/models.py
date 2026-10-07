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
