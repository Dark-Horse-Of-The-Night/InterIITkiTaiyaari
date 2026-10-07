import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.pipeline.errors import PipelineError
from app.pipeline.models import Segment, Transcript
from app.pipeline.refiner import check_edit, refine

FAKE_REQUEST = httpx.Request("POST", "https://example.test/v1/chat/completions")


class FakeChatClient:
    """Stands in for the OpenAI client.

    By default it echoes the segments back with `replacements` applied, like a
    well-behaved refiner. `replies` (strings or exceptions) are returned first, in order.
    """

    def __init__(
        self, replacements: dict[str, str] | None = None, replies: list[Any] | None = None, finish_reason: str = "stop"
    ) -> None:
        self.finish_reason = finish_reason
        self.replacements = replacements or {}
        self.replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            content = reply
        else:
            segments = json.loads(kwargs["messages"][1]["content"])["segments"]
            for seg in segments:
                for wrong, right in self.replacements.items():
                    seg["text"] = seg["text"].replace(wrong, right)
            content = json.dumps({"segments": segments})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=self.finish_reason)])


def make_transcript(*texts: str) -> Transcript:
    return Transcript(segments=[Segment(start=i * 5.0, end=i * 5.0 + 5, text=t) for i, t in enumerate(texts)])


def test_fixes_terms_and_keeps_timestamps() -> None:
    transcript = make_transcript("We moved our CICD to cooper netties.", "Ravi owns it.")
    client = FakeChatClient({"CICD": "CI/CD", "cooper netties.": "Kubernetes."})

    refined = refine(transcript, client, model="fake")

    assert refined.segments[0].text == "We moved our CI/CD to Kubernetes."
    assert refined.segments[1].text == "Ravi owns it."
    assert [s.start for s in refined.segments] == [0.0, 5.0]
    assert [(c.before, c.after) for c in refined.corrections] == [("CICD", "CI/CD"), ("cooper netties.", "Kubernetes.")]
    assert refined.warnings == []


def test_unchanged_transcript_has_no_corrections() -> None:
    refined = refine(make_transcript("Nothing to fix here."), FakeChatClient(), model="fake")

    assert refined.corrections == []
    assert refined.text == "Nothing to fix here."


@pytest.mark.parametrize(
    ("original", "bad_edit", "reason"),
    [
        ("We need five servers.", "We need six servers.", "changed a number"),
        ("Budget is 2000 dollars.", "Budget is 20000 dollars.", "changed a number"),
        ("We haven't agreed on Jenkins.", "We have agreed on Jenkins.", "changed a negation"),
        ("Do not deploy on Friday.", "Do deploy on Friday.", "changed a negation"),
        ("We haven’t agreed.", "We have agreed.", "changed a negation"),  # curly apostrophe
        ("We should ship the billing feature soon.", "We must ship the billing feature soon.", "changed a commitment"),
        ("I think Priya might take this one.", "Priya will definitely take this one.", "changed a commitment"),
        ("We'll review it on Monday.", "We review it on Monday.", "changed a commitment"),
        ("Arjun suggested trying it.", "Arjun decided trying it.", "changed a commitment"),
        ("Honestly the new thing looks fun to try out later on.", "Kafka streams events from the queue into the warehouse.", "rewrote too much"),
        ("Some words here.", "   ", "was empty"),
        ("Okay, so we moved on. Next item.", "Okay so we moved on Next item", "changed the punctuation"),
    ],
)
def test_unsafe_edits_are_rejected(original: str, bad_edit: str, reason: str) -> None:
    client = FakeChatClient(replies=[json.dumps({"segments": [{"id": 0, "text": bad_edit}]})])

    refined = refine(make_transcript(original), client, model="fake")

    assert refined.segments[0].text == original  # original wording kept
    assert refined.corrections == []
    assert len(refined.warnings) == 1
    assert reason in refined.warnings[0]


@pytest.mark.parametrize(
    ("original", "good_edit"),
    [
        ("We use post gress for storage.", "We use PostgreSQL for storage."),
        ("Sign it with a jason web token.", "Sign it with a JSON Web Token."),
        ("Store files in S three.", "Store files in S3."),  # number word -> digit is the same number
        ("We can't use oauth yet.", "We can't use OAuth yet."),
        # Two fixes changing 5 of 11 words: many words, but letters stay similar.
        ("The login API should use oh auth with jason web tokens.", "The login API should use OAuth with JSON Web Tokens."),
        ("cooper netties.", "Kubernetes."),
    ],
)
def test_safe_edits_pass_the_checks(original: str, good_edit: str) -> None:
    assert check_edit(original, good_edit) is None


def test_segments_left_out_of_the_reply_stay_unchanged() -> None:
    only_one = json.dumps({"segments": [{"id": 1, "text": "We use Kubernetes."}]})
    client = FakeChatClient(replies=[only_one])

    refined = refine(make_transcript("First.", "We use cooper netties.", "Third."), client, model="fake")

    assert len(client.calls) == 1
    assert [s.text for s in refined.segments] == ["First.", "We use Kubernetes.", "Third."]
    assert [(c.before, c.after) for c in refined.corrections] == [("cooper netties.", "Kubernetes.")]


def test_empty_reply_means_nothing_to_fix() -> None:
    refined = refine(make_transcript("All good."), FakeChatClient(replies=['{"segments": []}']), model="fake")

    assert refined.text == "All good."
    assert refined.corrections == []


@pytest.mark.parametrize(
    "bad_reply",
    [
        json.dumps({"segments": [{"id": 7, "text": "Not a segment we sent."}]}),  # unknown id
        json.dumps({"segments": [{"id": 0, "text": "A."}, {"id": 0, "text": "B."}]}),  # repeated id
    ],
)
def test_unknown_or_repeated_ids_are_retried(bad_reply: str) -> None:
    client = FakeChatClient(replies=[bad_reply])  # second attempt uses the normal echo

    refined = refine(make_transcript("First.", "Second."), client, model="fake")

    assert len(client.calls) == 2
    assert refined.text == "First. Second."


def test_cut_off_reply_is_retried() -> None:
    client = FakeChatClient(finish_reason="length")

    with pytest.raises(PipelineError, match="unexpected format"):
        refine(make_transcript("Hello."), client, model="fake")
    assert len(client.calls) == 2


def test_broken_json_twice_gives_clear_error() -> None:
    client = FakeChatClient(replies=["not json", "{still not json"])

    with pytest.raises(PipelineError) as error:
        refine(make_transcript("Hello."), client, model="fake")

    assert str(error.value).startswith("Refiner failed: the model returned an unexpected format")
    assert "REFINER_MODEL" in str(error.value)


def test_groq_json_validation_error_is_retried() -> None:
    response = httpx.Response(400, request=FAKE_REQUEST)
    groq_error = openai.BadRequestError("bad json", response=response, body={"code": "json_validate_failed"})
    client = FakeChatClient(replies=[groq_error])

    refined = refine(make_transcript("Hello."), client, model="fake")

    assert len(client.calls) == 2
    assert refined.text == "Hello."


def test_api_errors_name_refiner_settings() -> None:
    error = openai.AuthenticationError("no", response=httpx.Response(401, request=FAKE_REQUEST), body=None)

    with pytest.raises(PipelineError, match="Refiner failed: the API key was rejected. Check REFINER_API_KEY"):
        refine(make_transcript("Hello."), FakeChatClient(replies=[error]), model="fake")


def test_long_transcripts_are_sent_in_batches() -> None:
    transcript = make_transcript(*[f"Line {i}." for i in range(100)])
    client = FakeChatClient()

    details: list[str] = []
    refined = refine(transcript, client, model="fake", on_detail=details.append)

    assert len(client.calls) == 3  # 40 + 40 + 20
    assert details == ["Batch 1 of 3", "Batch 2 of 3", "Batch 3 of 3"]
    assert len(refined.segments) == 100
    assert refined.segments[99].text == "Line 99."
    last_batch = json.loads(client.calls[2]["messages"][1]["content"])["segments"]
    assert last_batch[0]["id"] == 80


def test_request_settings_and_glossary() -> None:
    client = FakeChatClient()

    refine(make_transcript("Hello."), client, model="fake-model", glossary=["Zephyr", " ", "KubeFlow"])

    call = client.calls[0]
    assert call["model"] == "fake-model"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "low"
    system_prompt = call["messages"][0]["content"]
    assert "Zephyr, KubeFlow" in system_prompt
    assert "{{GLOSSARY}}" not in system_prompt


def test_no_glossary_says_none_provided() -> None:
    client = FakeChatClient()

    refine(make_transcript("Hello."), client, model="fake")

    assert "(none provided)" in client.calls[0]["messages"][0]["content"]


def test_term_split_across_segments_is_not_duplicated() -> None:
    transcript = make_transcript("We should switch our logging to open", "telemetry. People had mixed feelings.")
    client = FakeChatClient(replies=[json.dumps({"segments": [{"id": 0, "text": "We should switch our logging to OpenTelemetry"}]})])

    refined = refine(transcript, client, model="fake")

    assert refined.text == "We should switch our logging to open telemetry. People had mixed feelings."  # unchanged
    assert "would repeat a word that continues in the next segment" in refined.warnings[0]


def test_split_term_fixed_in_the_second_segment_is_also_caught() -> None:
    transcript = make_transcript("We moved the jobs to cooper", "netties last week.")
    client = FakeChatClient(replies=[json.dumps({"segments": [{"id": 1, "text": "cooper Kubernetes last week."}]})])

    refined = refine(transcript, client, model="fake")

    assert refined.segments[1].text == "netties last week."
    assert "starts in the previous segment" in refined.warnings[0]


def test_normal_fix_next_to_a_boundary_is_allowed() -> None:
    transcript = make_transcript("We store sessions in redis", "and logs in elastic search.")
    client = FakeChatClient({"redis": "Redis", "elastic search": "Elasticsearch"})

    refined = refine(transcript, client, model="fake")

    assert refined.text == "We store sessions in Redis and logs in Elasticsearch."
    assert refined.warnings == []


def test_refining_keeps_speaker_labels() -> None:
    transcript = Transcript(segments=[
        Segment(start=0, end=2, text="We use cooper netties.", speaker="Speaker 1"),
        Segment(start=2, end=4, text="Agreed.", speaker="Speaker 2"),
    ])

    refined = refine(transcript, FakeChatClient({"cooper netties.": "Kubernetes."}), model="fake")

    assert [(s.speaker, s.text) for s in refined.segments] == [("Speaker 1", "We use Kubernetes."), ("Speaker 2", "Agreed.")]
