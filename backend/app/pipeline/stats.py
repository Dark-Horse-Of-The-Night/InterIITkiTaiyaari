"""Speaking stats: who spoke how much and when. Code only, from speaker labels and timestamps."""

from app.pipeline.models import Segment, SpeakerStats, SpeakingStats, SpeakingTurn

# Lines from the same speaker with a gap shorter than this count as one turn.
SAME_TURN_GAP_SECONDS = 2.0


def build_speaking_stats(segments: list[Segment]) -> SpeakingStats | None:
    """Return the stats, or None if the transcript has no speaker labels."""
    labelled = [segment for segment in segments if segment.speaker]
    if not labelled:
        return None

    timeline = speaking_turns(labelled)
    total = sum(segment.end - segment.start for segment in labelled) or 1.0
    stats = []
    for speaker in dict.fromkeys(segment.speaker for segment in labelled):  # first-heard order, no repeats
        own = [segment for segment in labelled if segment.speaker == speaker]
        turns = [turn for turn in timeline if turn.speaker == speaker]
        seconds = sum(segment.end - segment.start for segment in own)
        stats.append(SpeakerStats(
            speaker=speaker or "",
            seconds=round(seconds, 1),
            share=round(seconds / total, 3),
            turns=len(turns),
            longest_turn_seconds=round(max(turn.end - turn.start for turn in turns), 1),
            questions=sum(1 for segment in own if segment.text.rstrip().endswith("?")),
        ))
    stats.sort(key=lambda s: s.seconds, reverse=True)
    return SpeakingStats(speakers=stats, timeline=timeline)


def speaking_turns(segments: list[Segment]) -> list[SpeakingTurn]:
    """Join consecutive lines by the same speaker into turns."""
    turns: list[SpeakingTurn] = []
    for segment in segments:
        last = turns[-1] if turns else None
        if last and last.speaker == segment.speaker and segment.start - last.end < SAME_TURN_GAP_SECONDS:
            last.end = max(last.end, segment.end)
        else:
            turns.append(SpeakingTurn(speaker=segment.speaker or "", start=segment.start, end=segment.end))
    return turns
