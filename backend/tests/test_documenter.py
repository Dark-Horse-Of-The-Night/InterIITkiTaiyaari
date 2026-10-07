import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.pipeline.documenter import document, locate_quote, record_json_schema
from app.pipeline.errors import PipelineError
from app.pipeline.models import Segment, Transcript

FAKE_REQUEST = httpx.Request("POST", "https://example.test/v1/chat/completions")

TRANSCRIPT = Transcript(segments=[
    Segment(start=0.0, end=3.0, text="Okay, let's start the sprint planning."),
    Segment(start=3.0, end=7.0, text="Priya said the Kubernetes cluster keeps running out of memory,"),
    Segment(start=7.0, end=11.0, text="so she will move the PostgreSQL database to a managed instance by Friday."),
    Segment(start=11.0, end=15.0, text="Arjun proposed switching our CI/CD pipeline to GitHub Actions,"),
    Segment(start=15.0, end=18.0, text="but we haven't agreed on that yet."),
    Segment(start=18.0, end=22.0, text="We decided to use OAuth with JWT tokens for the login API."),
    Segment(start=22.0, end=25.0, text="Someone needs to update the Swagger docs."),
    Segment(start=25.0, end=28.0, text="I'll handle the release notes."),
])


def evidence(ids: list[int], quote: str) -> dict[str, Any]:
    return {"segment_ids": ids, "quote": quote}


def make_record(**overrides: Any) -> dict[str, Any]:
    """A well-behaved model reply for TRANSCRIPT. Override any section to test the checks."""
    record = {
        "summary": "Sprint planning covering the database, CI/CD and login.",
        "minutes": [{"topic": "Database", "points": ["Cluster runs out of memory."], "segment_ids": [1, 2]}],
        "decisions": [{"text": "Use OAuth with JWT for the login API.", "evidence": evidence([5], "We decided to use OAuth with JWT tokens")}],
        "action_items": [
            {"task": "Move PostgreSQL to a managed instance", "owner": "Priya", "deadline": "by Friday",
             "evidence": evidence([2], "she will move the PostgreSQL database to a managed instance")},
            {"task": "Update the Swagger docs", "owner": None, "deadline": None,
             "evidence": evidence([6], "Someone needs to update the Swagger docs")},
        ],
        "open_items": [
            {"text": "Switch CI/CD to GitHub Actions", "kind": "proposal", "raised_by": "Arjun",
             "evidence": evidence([3], "Arjun proposed switching our CI/CD pipeline to GitHub Actions")},
        ],
    }
    record.update(overrides)
    return record


class FakeChatClient:
    """Returns the given replies in order (JSON strings, dicts or exceptions)."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_good_record_passes_unchanged_with_timestamps() -> None:
    record = document(TRANSCRIPT, FakeChatClient(make_record()), model="fake")

    assert record.warnings == []
    priya = record.action_items[0]
    assert (priya.owner, priya.deadline) == ("Priya", "by Friday")  # "she" -> Priya, stated 1 segment before
    assert priya.evidence.start == 7.0
    assert record.action_items[1].owner is None
    assert record.decisions[0].evidence.start == 18.0
    assert record.open_items[0].raised_by == "Arjun"


def test_invented_owner_is_removed_with_warning() -> None:
    items = make_record()["action_items"]
    items[1]["owner"] = "Ravi"  # nobody said Ravi
    record = document(TRANSCRIPT, FakeChatClient(make_record(action_items=items)), model="fake")

    assert record.action_items[1].owner is None
    assert "Removed owner 'Ravi'" in record.warnings[0]


def test_invented_deadline_is_removed_with_warning() -> None:
    items = make_record()["action_items"]
    items[1]["deadline"] = "by next Monday"
    record = document(TRANSCRIPT, FakeChatClient(make_record(action_items=items)), model="fake")

    assert record.action_items[1].deadline is None
    assert "Removed deadline 'by next Monday'" in record.warnings[0]


def test_deadline_converted_to_a_date_is_removed() -> None:
    items = make_record()["action_items"]
    items[0]["deadline"] = "2026-10-09"  # "by Friday" turned into a date: not what was said
    record = document(TRANSCRIPT, FakeChatClient(make_record(action_items=items)), model="fake")

    assert record.action_items[0].deadline is None


def test_i_will_owner_becomes_unspecified_without_warning() -> None:
    items = [{"task": "Write the release notes", "owner": "I", "deadline": None,
              "evidence": evidence([7], "I'll handle the release notes")}]
    record = document(TRANSCRIPT, FakeChatClient(make_record(action_items=items)), model="fake")

    assert record.action_items[0].owner is None
    assert record.warnings == []


def test_item_with_invented_quote_is_removed() -> None:
    decisions = [{"text": "Adopt Kafka.", "evidence": evidence([5], "We agreed to adopt Kafka")}]
    record = document(TRANSCRIPT, FakeChatClient(make_record(decisions=decisions)), model="fake")

    assert record.decisions == []
    assert "Removed decision 'Adopt Kafka.'" in record.warnings[0]


def test_wrong_segment_id_is_corrected_from_the_quote() -> None:
    decisions = [{"text": "Use OAuth.", "evidence": evidence([0], "we decided to use oauth, with JWT tokens")}]
    record = document(TRANSCRIPT, FakeChatClient(make_record(decisions=decisions)), model="fake")

    assert record.decisions[0].evidence.segment_ids == [5]  # case/punctuation ignored, id fixed
    assert record.decisions[0].evidence.start == 18.0


def test_quote_spanning_two_segments_is_found() -> None:
    ids = locate_quote("to GitHub Actions, but we haven't agreed", TRANSCRIPT.segments, preferred_ids=[])
    assert ids == [3, 4]


def test_invalid_minutes_ids_are_dropped() -> None:
    minutes = [{"topic": "Misc", "points": ["x"], "segment_ids": [1, 99, -1]}]
    record = document(TRANSCRIPT, FakeChatClient(make_record(minutes=minutes)), model="fake")

    assert record.minutes[0].segment_ids == [1]


def test_schema_mismatch_is_retried_then_fails_clearly() -> None:
    bad = {"summary": "only a summary"}
    client = FakeChatClient(bad, "not json at all")

    with pytest.raises(PipelineError) as error:
        document(TRANSCRIPT, client, model="fake")

    assert len(client.calls) == 2
    assert str(error.value).startswith("Documenter failed: the model returned a record in an unexpected format")
    assert "DOCUMENTER_MODEL" in str(error.value)


def test_retry_succeeds_after_one_bad_reply() -> None:
    client = FakeChatClient({"summary": "incomplete"}, make_record())

    record = document(TRANSCRIPT, client, model="fake")

    assert len(client.calls) == 2
    assert len(record.action_items) == 2


def test_api_errors_name_documenter_settings() -> None:
    error = openai.RateLimitError("slow down", response=httpx.Response(429, request=FAKE_REQUEST), body=None)

    with pytest.raises(PipelineError, match=r"Documenter failed: the documenter service is busy \(rate limit reached\) \(tried 7 times\)"):
        document(TRANSCRIPT, FakeChatClient(*[error] * 7), model="fake")


def test_request_uses_strict_schema_and_numbered_lines() -> None:
    client = FakeChatClient(make_record())

    document(TRANSCRIPT, client, model="fake-model")

    call = client.calls[0]
    assert call["model"] == "fake-model"
    assert call["temperature"] == 0
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "[2] (00:07) so she will move" in call["messages"][1]["content"]


def test_schema_leaves_out_code_filled_fields() -> None:
    schema_text = json.dumps(record_json_schema())

    assert '"warnings"' not in schema_text
    assert '"start"' not in schema_text
    assert '"owner"' in schema_text
