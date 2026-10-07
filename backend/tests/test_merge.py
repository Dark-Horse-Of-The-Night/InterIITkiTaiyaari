"""Long meetings: documenting in parts, splitting cut-off parts, and the cross-check merge."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.pipeline.documenter import document, record_json_schema, split_into_parts
from app.pipeline.errors import PipelineError
from app.pipeline.llm_json import estimate_tokens
from app.pipeline.merge import Removal, apply_removals, join_minutes, label_items
from app.pipeline.models import ActionItem, Decision, Evidence, MeetingRecord, OpenItem, Segment, Topic, Transcript
from app.prompt_loader import load_prompt

CUT_OFF = "CUT_OFF"  # a reply that hits the output limit

FILLER = "Status update {i}: the dashboards look healthy and nobody raised concerns."
SEGMENTS = [Segment(start=i * 5.0, end=i * 5.0 + 5, text=FILLER.format(i=i)) for i in range(40)]
SEGMENTS[0] = Segment(start=0, end=5, text="Sofia proposed that we migrate the reporting jobs to Airflow.")
SEGMENTS[1] = Segment(start=5, end=10, text="Let's park that for now and come back to it.")
SEGMENTS[3] = Segment(start=15, end=20, text="We decided to keep the legacy endpoint until December.")
SEGMENTS[30] = Segment(start=150, end=155, text="Going back to Sofia's idea, we'll move the reporting jobs to Airflow.")
SEGMENTS[32] = Segment(start=160, end=165, text="Actually, we will shut down the legacy endpoint at the end of this month.")
SEGMENTS[35] = Segment(start=175, end=180, text="Daniel will add rate limiting by October 20th.")
TRANSCRIPT = Transcript(segments=SEGMENTS)


def budget_for_room(room: int) -> int:
    """The max_request_tokens that leaves `room` tokens for transcript lines in each request."""
    overhead = estimate_tokens(load_prompt("documenter") + str(record_json_schema()))
    return 2 * (room + 100 + overhead)  # half the budget is kept for the reply


def ev(ids: list[int], quote: str) -> dict[str, Any]:
    return {"segment_ids": ids, "quote": quote}


def record(summary: str, decisions: list[Any] = (), actions: list[Any] = (), open_items: list[Any] = ()) -> dict[str, Any]:  # type: ignore[assignment]
    return {"summary": summary, "minutes": [{"topic": "Updates", "points": [summary], "segment_ids": []}],
            "decisions": list(decisions), "action_items": list(actions), "open_items": list(open_items)}


PART_1 = record(
    "Sofia proposed Airflow; legacy endpoint kept until December.",
    decisions=[{"text": "Keep the legacy endpoint until December", "evidence": ev([3], "keep the legacy endpoint until December")}],
    open_items=[{"text": "Migrate reporting jobs to Airflow", "kind": "proposal", "raised_by": "Sofia",
                 "evidence": ev([0], "Sofia proposed that we migrate the reporting jobs to Airflow")}],
)
PART_2 = record(
    "Airflow accepted; legacy endpoint to be shut down this month; Daniel owns rate limiting.",
    decisions=[
        {"text": "Move the reporting jobs to Airflow", "evidence": ev([30], "we'll move the reporting jobs to Airflow")},
        {"text": "Shut down the legacy endpoint at the end of this month",
         "evidence": ev([32], "we will shut down the legacy endpoint at the end of this month")},
    ],
    actions=[{"task": "Add rate limiting", "owner": "Daniel", "deadline": "by October 20th",
              "evidence": ev([35], "Daniel will add rate limiting by October 20th")}],
)
CROSS_CHECK = {
    "summary": "The team adopted Airflow, will shut down the legacy endpoint this month, and Daniel owns rate limiting.",
    "removals": [
        {"item": "O1", "replaced_by": "D2", "reason": "accepted_later"},
        {"item": "D1", "replaced_by": "D3", "reason": "superseded"},
    ],
}


class FakeClient:
    """Returns replies in order: dicts as JSON, CUT_OFF as a reply that hit the output limit."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply == CUT_OFF:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary": "cut'), finish_reason="length")])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)), finish_reason="stop")])


def two_parts_budget() -> int:
    budget = budget_for_room(600)
    parts = split_into_parts(SEGMENTS, 600)
    assert len(parts) == 2 and parts[0][1] <= 30, parts  # Airflow acceptance must land in part 2
    return budget


def test_long_meeting_is_documented_in_parts_and_cross_checked() -> None:
    client = FakeClient(PART_1, PART_2, CROSS_CHECK)
    details: list[str] = []

    result = document(TRANSCRIPT, client, "m", on_detail=details.append, max_request_tokens=two_parts_budget())

    assert details == ["Part 1 of 2", "Part 2 of 2", "Cross-checking the parts"]
    assert [d.text for d in result.decisions] == [
        "Move the reporting jobs to Airflow", "Shut down the legacy endpoint at the end of this month",
    ]  # accepted proposal became a decision; the reversed decision is gone
    assert result.open_items == []
    assert (result.action_items[0].owner, result.action_items[0].deadline) == ("Daniel", "by October 20th")
    assert result.summary.startswith("The team adopted Airflow")
    assert any("was accepted later in the meeting" in w for w in result.warnings)
    assert any("was changed later in the meeting" in w for w in result.warnings)


def test_parts_are_told_where_they_are_and_keep_global_line_numbers() -> None:
    client = FakeClient(PART_1, PART_2, CROSS_CHECK)

    document(TRANSCRIPT, client, "m", max_request_tokens=two_parts_budget())

    second_part = client.calls[1]["messages"][1]["content"]
    assert second_part.startswith("This transcript is part 2 of 2 of one meeting")
    assert "[30] (02:30) Going back to Sofia's idea" in second_part  # numbered as in the whole transcript
    cross_check = client.calls[2]["messages"][1]["content"]
    assert "[O1] (part 1) Proposal: Migrate reporting jobs to Airflow [raised by Sofia]" in cross_check
    assert "[A1] (part 2) Action: Add rate limiting [owner: Daniel, deadline: by October 20th]" in cross_check


def test_short_meeting_still_uses_one_request() -> None:
    client = FakeClient(PART_1)

    result = document(TRANSCRIPT, client, "m", max_request_tokens=100_000)

    assert len(client.calls) == 1
    assert not client.calls[0]["messages"][1]["content"].startswith("This transcript is part")
    assert len(result.open_items) == 1


def test_cut_off_reply_splits_the_part_in_half() -> None:
    client = FakeClient(CUT_OFF, PART_1, PART_2, CROSS_CHECK)
    details: list[str] = []

    result = document(TRANSCRIPT, client, "m", on_detail=details.append, max_request_tokens=100_000)

    assert details == ["Part 1 of 2", "Part 2 of 2", "Cross-checking the parts"]
    first_half = client.calls[1]["messages"][1]["content"]
    assert "[19]" in first_half and "[20]" not in first_half  # lines 0-19, then 20-39
    assert len(result.decisions) == 2


def test_tiny_part_that_is_still_cut_off_gives_clear_error() -> None:
    tiny = Transcript(segments=SEGMENTS[:10])
    with pytest.raises(PipelineError, match="too long for the output limit"):
        document(tiny, FakeClient(CUT_OFF), "m", max_request_tokens=100_000)


def test_groq_cut_off_error_also_splits_the_part() -> None:
    groq_error = openai.BadRequestError(
        "max completion tokens reached before generating a valid document",
        response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
        body={"code": "json_validate_failed"},
    )
    client = FakeClient(groq_error, PART_1, PART_2, CROSS_CHECK)

    document(TRANSCRIPT, client, "m", max_request_tokens=100_000)

    assert len(client.calls) == 4


def test_too_many_items_to_cross_check_keeps_everything_with_a_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.pipeline.merge.RECONCILE_OUTPUT_TOKENS", 1_000_000)  # cross-check can never fit
    client = FakeClient(PART_1, PART_2)

    result = document(TRANSCRIPT, client, "m", max_request_tokens=two_parts_budget())

    assert len(client.calls) == 2  # no cross-check request
    assert len(result.decisions) == 3 and len(result.open_items) == 1
    assert any("too many items to cross-check" in w for w in result.warnings)
    assert result.summary.startswith("Sofia proposed Airflow")  # part summaries joined


def test_budget_too_small_is_explained() -> None:
    with pytest.raises(PipelineError, match="DOCUMENTER_MAX_REQUEST_TOKENS \\(1000\\) is too small"):
        document(TRANSCRIPT, FakeClient(), "m", max_request_tokens=1000)


# --- Checking the cross-check's removals ---


def item_ev() -> Evidence:
    return Evidence(segment_ids=[0], quote="x")


def make_parts() -> list[MeetingRecord]:
    part1 = MeetingRecord(
        summary="1", minutes=[],
        decisions=[Decision(text="Keep until December", evidence=item_ev())],
        action_items=[ActionItem(task="Write docs", owner=None, deadline=None, evidence=item_ev())],
        open_items=[OpenItem(text="Use Airflow?", kind="proposal", raised_by=None, evidence=item_ev()),
                    OpenItem(text="Does review take a week?", kind="question", raised_by=None, evidence=item_ev())],
    )
    part2 = MeetingRecord(
        summary="2", minutes=[],
        decisions=[Decision(text="Use Airflow", evidence=item_ev()), Decision(text="Shut down now", evidence=item_ev())],
        action_items=[ActionItem(task="Write docs", owner="Ann", deadline=None, evidence=item_ev())],
        open_items=[],
    )
    return [part1, part2]  # labels: D1 (p1), D2 D3 (p2), A1 (p1), A2 (p2), O1 O2 (p1)


@pytest.mark.parametrize(
    ("removal", "accepted"),
    [
        (Removal(item="O1", replaced_by="D2", reason="accepted_later"), True),
        (Removal(item="D1", replaced_by="D3", reason="superseded"), True),
        (Removal(item="A1", replaced_by="A2", reason="duplicate"), True),
        (Removal(item="D2", replaced_by="D1", reason="superseded"), False),  # replacement is earlier
        (Removal(item="D1", replaced_by="D2", reason="accepted_later"), False),  # a decision isn't a proposal
        (Removal(item="O2", replaced_by="D2", reason="accepted_later"), False),  # a question isn't a proposal
        (Removal(item="O1", replaced_by="A2", reason="duplicate"), False),  # different kinds
        (Removal(item="O1", replaced_by="O1", reason="duplicate"), False),  # itself
        (Removal(item="X9", replaced_by="D2", reason="duplicate"), False),  # unknown
    ],
)
def test_only_sensible_removals_are_applied(removal: Removal, accepted: bool) -> None:
    warnings: list[str] = []
    removed = apply_removals([removal], label_items(make_parts()), warnings)

    assert (removal.item in removed) is accepted
    assert len(warnings) == (1 if accepted else 0)


def test_removal_chains_cannot_delete_both_items() -> None:
    removals = [Removal(item="A1", replaced_by="A2", reason="duplicate"), Removal(item="A2", replaced_by="A1", reason="duplicate")]

    assert apply_removals(removals, label_items(make_parts()), []) == {"A1"}


def test_minutes_join_a_topic_that_spans_two_parts() -> None:
    joined = join_minutes([
        [Topic(topic="Intro", points=["a"], segment_ids=[0]), Topic(topic="Billing", points=["b"], segment_ids=[5])],
        [Topic(topic="billing ", points=["c"], segment_ids=[9]), Topic(topic="Wrap-up", points=["d"], segment_ids=[12])],
    ])

    assert [(t.topic, t.points) for t in joined] == [("Intro", ["a"]), ("Billing", ["b", "c"]), ("Wrap-up", ["d"])]


@pytest.mark.parametrize("room", [300, 500, 600, 700, 2000])
def test_parts_are_balanced_and_cover_every_line_once(room: int) -> None:
    parts = split_into_parts(SEGMENTS, room)

    assert parts[0][0] == 0 and parts[-1][1] == len(SEGMENTS)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))  # no gaps or overlaps
    sizes = [end - first for first, end in parts]
    assert max(sizes) - min(sizes) <= 2  # no tiny leftover part
