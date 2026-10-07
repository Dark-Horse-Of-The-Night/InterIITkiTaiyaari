import json

from app.pipeline.models import ActionItem, Decision, Evidence, MeetingRecord, OpenItem, Topic
from app.pipeline.render import record_to_json, record_to_markdown


def make_record() -> MeetingRecord:
    return MeetingRecord(
        summary="We planned the sprint.",
        minutes=[Topic(topic="Database", points=["Memory issues."], segment_ids=[1])],
        decisions=[Decision(text="Use OAuth.", evidence=Evidence(segment_ids=[5], quote="We decided to use OAuth", start=18))],
        action_items=[
            ActionItem(task="Move DB", owner="Priya", deadline="by Friday", evidence=Evidence(segment_ids=[2], quote="she will move", start=7)),
            ActionItem(task="Update docs | API", owner=None, deadline=None, evidence=Evidence(segment_ids=[6], quote="update the docs", start=65)),
        ],
        open_items=[OpenItem(text="Use GitHub Actions", kind="proposal", raised_by="Arjun", evidence=Evidence(segment_ids=[3], quote="Arjun proposed", start=11))],
        warnings=["Removed owner 'Ravi' from action item 'Update docs'."],
    )


def test_markdown_shows_unspecified_for_missing_owner_and_deadline() -> None:
    markdown = record_to_markdown(make_record())

    assert "| 1 | Move DB | Priya | by Friday | 00:07 |" in markdown
    assert "| 2 | Update docs \\| API | Unspecified | Unspecified | 01:05 |" in markdown  # "|" escaped


def test_json_keeps_null_for_missing_owner_and_deadline() -> None:
    data = json.loads(record_to_json(make_record()))

    assert data["action_items"][1]["owner"] is None
    assert data["action_items"][1]["deadline"] is None


def test_markdown_and_json_contain_the_same_items() -> None:
    record = make_record()
    markdown = record_to_markdown(record)
    data = json.loads(record_to_json(record))

    for decision in data["decisions"]:
        assert decision["text"] in markdown
    for item in data["action_items"]:
        assert item["task"].replace("|", "\\|") in markdown
    for item in data["open_items"]:
        assert item["text"] in markdown
    assert data["summary"] in markdown


def test_sections_and_sources() -> None:
    markdown = record_to_markdown(make_record(), title="Sprint planning")

    assert markdown.startswith("# Sprint planning")
    assert '1. Use OAuth. _(00:18: "We decided to use OAuth")_' in markdown
    assert "- **Proposal, raised by Arjun:** Use GitHub Actions" in markdown
    assert "## Notes on this record" in markdown


def test_empty_sections_say_none_recorded() -> None:
    record = MeetingRecord(summary="Short chat.", minutes=[], decisions=[], action_items=[], open_items=[])
    markdown = record_to_markdown(record)

    assert markdown.count("_None recorded._") == 4  # minutes, decisions, actions, open items
    assert "Notes on this record" not in markdown  # no warnings, no section
