import json

from app.pipeline.models import (
    ActionItem,
    Correction,
    Decision,
    Evidence,
    MeetingRecord,
    RefinedTranscript,
    Segment,
    SpeakerName,
    Transcript,
)
from app.pipeline.render import record_to_json, record_to_markdown
from app.pipeline.stats import build_speaking_stats
from app.pipeline.trust import build_trust_report


def seg(start: float, end: float, text: str, speaker: str | None = None, unclear: bool = False) -> Segment:
    return Segment(start=start, end=end, text=text, speaker=speaker, unclear=unclear)


SEGMENTS = [
    seg(0, 4, "Neha, can you fix the crash?", "Speaker 1"),
    seg(4, 6, "Sure.", "Neha"),
    seg(6.5, 10, "I'll have it ready by Friday.", "Neha", unclear=True),
    seg(10, 12, "Great, thanks.", "Speaker 1"),
    seg(12, 13, "Anything else?", "Speaker 1"),
]


def make_record() -> MeetingRecord:
    return MeetingRecord(
        summary="Neha will fix the crash.",
        minutes=[],
        decisions=[Decision(text="Fix the crash first.", evidence=Evidence(segment_ids=[0], quote="fix the crash"))],
        action_items=[
            ActionItem(task="Fix the crash", owner="Neha", deadline="by Friday",
                       evidence=Evidence(segment_ids=[2], quote="I'll have it ready", unclear=True)),
            ActionItem(task="Update notes", owner=None, deadline=None, evidence=Evidence(segment_ids=[3], quote="Great")),
        ],
        open_items=[],
        warnings=["Removed owner 'Ravi' from action item 'Update notes': not stated in the recording near that point."],
        fix_counts={"unstated_detail": 1, "unsupported_item": 2},
    )


def make_refined() -> RefinedTranscript:
    return RefinedTranscript(
        segments=SEGMENTS,
        corrections=[Correction(segment_id=0, before="crush", after="crash")],
        warnings=["Segment 4 (00:10): kept the original wording because the suggested edit changed a number."],
        speaker_names=[SpeakerName(label="Speaker 2", name="Neha", how="was addressed by name and answered", quote="Neha", start=0)],
        blocked_edits={"changed a number": 1},
    )


# --- Trust report ---


def test_trust_report_counts_every_check() -> None:
    trust = build_trust_report(Transcript(segments=SEGMENTS), make_refined(), make_record())

    assert trust.items_verified == 3
    assert trust.items_removed == 2
    assert trust.details_removed == 1
    assert trust.items_superseded == 0
    assert (trust.owners_unspecified, trust.deadlines_unspecified) == (1, 1)
    assert trust.corrections == 1
    assert trust.edits_blocked == {"changed a number": 1}
    assert (trust.speakers_named, trust.speakers_unnamed) == (1, 1)
    assert (trust.unclear_segments, trust.unclear_items) == (1, 1)
    assert len(trust.notes) == 2  # refiner note + record note


def test_trust_report_for_a_clean_meeting_without_speakers() -> None:
    plain = [s.model_copy(update={"speaker": None, "unclear": False}) for s in SEGMENTS]
    record = make_record().model_copy(update={"warnings": [], "fix_counts": {}})

    trust = build_trust_report(Transcript(segments=plain), RefinedTranscript(segments=plain), record)

    assert trust.items_removed == trust.details_removed == trust.unclear_segments == 0
    assert (trust.speakers_named, trust.speakers_unnamed) == (0, 0)
    assert trust.notes == []


# --- Speaking stats ---


def test_speaking_stats_talk_time_share_turns_and_questions() -> None:
    stats = build_speaking_stats(SEGMENTS)

    assert stats is not None
    first, second = stats.speakers
    assert (first.speaker, first.seconds, first.turns, first.questions) == ("Speaker 1", 7.0, 2, 2)
    assert (second.speaker, second.seconds, second.turns, second.questions) == ("Neha", 5.5, 1, 0)
    assert round(first.share + second.share, 2) == 1.0
    assert second.longest_turn_seconds == 6.0  # 4.0 -> 10.0, the 0.5 s gap is the same turn


def test_timeline_joins_consecutive_lines_into_turns() -> None:
    stats = build_speaking_stats(SEGMENTS)

    assert stats is not None
    assert [(t.speaker, t.start, t.end) for t in stats.timeline] == [
        ("Speaker 1", 0, 4), ("Neha", 4, 10), ("Speaker 1", 10, 13),
    ]


def test_long_pause_starts_a_new_turn() -> None:
    stats = build_speaking_stats([seg(0, 2, "Hi.", "A"), seg(10, 12, "Still me.", "A")])

    assert stats is not None and len(stats.timeline) == 2


def test_no_speaker_labels_means_no_stats() -> None:
    assert build_speaking_stats([seg(0, 1, "Hello.")]) is None


# --- Downloads ---


def test_markdown_and_json_carry_the_same_trust_and_speaking_data() -> None:
    record = make_record()
    trust = build_trust_report(Transcript(segments=SEGMENTS), make_refined(), record)
    speaking = build_speaking_stats(SEGMENTS)

    markdown = record_to_markdown(record, trust=trust, speaking=speaking)
    data = json.loads(record_to_json(record, trust, speaking))

    assert "## Trust report" in markdown and "## Who spoke" in markdown
    assert "3 items (decisions, tasks, open items) checked" in markdown
    assert "1 risky edit blocked (1 changed a number)" in markdown
    assert "1 task owner and 1 deadline left Unspecified" in markdown
    assert "| Speaker 1 | 00:07 | 56% | 2 | 2 |" in markdown
    assert data["trust_report"]["items_verified"] == 3
    assert data["speaking_stats"]["speakers"][0]["speaker"] == "Speaker 1"
    assert "fix_counts" not in data  # covered by the trust report


def test_downloads_without_extras_keep_the_old_notes_section() -> None:
    markdown = record_to_markdown(make_record())

    assert "## Notes on this record" in markdown
    assert "## Trust report" not in markdown
    assert "trust_report" not in json.loads(record_to_json(make_record()))
