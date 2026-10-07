"""Speaker labels (voice grouping) and speaker names (evidence-checked). No real model needed."""

import json
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.pipeline.documenter import document
from app.pipeline.models import Segment, Transcript
from app.pipeline.speaker_names import NameGuess, check_guess, name_speakers
from app.pipeline.speakers import cluster, label_speakers


class PitchEmbedder:
    """Fake voice model: each "voice" in the test audio is a different pitch, and the
    fingerprint is just which pitch dominates (plus a little noise)."""

    def embed(self, samples: Any) -> Any:
        spectrum = np.abs(np.fft.rfft(samples))
        frequency = np.argmax(spectrum) * 16000 / len(samples)
        vector = np.zeros(8)
        vector[min(int(frequency // 150), 7)] = 1.0
        return vector + np.random.default_rng(len(samples)).normal(0, 0.02, 8)


def make_voices_wav(path: Path, turns: list[tuple[int, float]], rate: int = 16000) -> tuple[Path, list[Segment]]:
    """A WAV of (pitch_hz, seconds) turns with short gaps, and one segment per turn."""
    segments, t = [], 0.0
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for pitch, seconds in turns:
            for i in range(int(seconds * rate)):
                wav.writeframes(struct.pack("<h", int(8000 * math.sin(2 * math.pi * pitch * i / rate))))
            segments.append(Segment(start=t, end=t + seconds, text=f"words at {pitch} hz"))
            t += seconds
            wav.writeframes(b"\0\0" * int(0.3 * rate))
            t += 0.3
    return path, segments


def test_voices_are_grouped_and_numbered_in_order_of_first_speaking(tmp_path: Path) -> None:
    wav, segments = make_voices_wav(tmp_path / "m.wav", [(200, 2), (500, 2), (200, 1.5), (800, 2), (500, 1.2)])

    labelled = label_speakers(segments, wav, PitchEmbedder())

    assert [s.speaker for s in labelled] == ["Speaker 1", "Speaker 2", "Speaker 1", "Speaker 3", "Speaker 2"]
    assert [s.text for s in labelled] == [s.text for s in segments]  # text and times untouched


def test_short_segments_borrow_the_previous_label(tmp_path: Path) -> None:
    wav, segments = make_voices_wav(tmp_path / "m.wav", [(200, 2), (500, 2), (800, 0.4)])

    labelled = label_speakers(segments, wav, PitchEmbedder())

    assert labelled[2].speaker == "Speaker 2"  # too short to compare: same as the segment before


def test_cluster_merges_close_fingerprints_only() -> None:
    a, b = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    groups = cluster(np.stack([a, a * 0.98 + b * 0.05, b, b + a * 0.03]), threshold=0.3)

    assert groups[0] == groups[1] and groups[2] == groups[3] and groups[0] != groups[2]


# --- Names: only with evidence that holds up ---

SEGMENTS = [
    Segment(start=0, end=3, text="Good morning, everyone.", speaker="Speaker 1"),
    Segment(start=3, end=6, text="Neha, can you give us an update on the Android crash?", speaker="Speaker 1"),
    Segment(start=6, end=9, text="Sure. I'll have a fix ready by Friday.", speaker="Speaker 2"),
    Segment(start=9, end=12, text="Hi, this is Tom from the platform team. I'll set up the Mixpanel account.", speaker="Speaker 3"),
    Segment(start=12, end=15, text="Rahul said yesterday that the build is green.", speaker="Speaker 1"),
    Segment(start=15, end=18, text="Great.", speaker="Speaker 4"),
]


def guess(speaker: str, name: str, evidence: str, quote: str) -> NameGuess:
    return NameGuess(speaker=speaker, name=name, evidence=evidence, quote=quote)  # type: ignore[arg-type]


LABELS = {"Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4"}


@pytest.mark.parametrize(
    ("g", "problem"),
    [
        (guess("Speaker 2", "Neha", "addressed_then_answered", "Neha, can you give us an update"), None),
        (guess("Speaker 3", "Tom", "introduced_themselves", "this is Tom from the platform team"), None),
        # merely mentioned ("Rahul said…"), even though Speaker 4 happens to speak next
        (guess("Speaker 4", "Rahul", "addressed_then_answered", "Rahul said yesterday that the build is green"), "the name is only mentioned, not said to someone"),
        (guess("Speaker 2", "Neha", "addressed_then_answered", "Good morning, everyone."), "the quote doesn't contain the name"),
        (guess("Speaker 3", "Neha", "addressed_then_answered", "Neha, can you give us an update"), "someone else answered"),
        (guess("Speaker 1", "Tom", "introduced_themselves", "this is Tom from the platform team"), "the introduction was said by someone else"),
        (guess("Speaker 2", "Neha", "introduced_themselves", "Sure. I'll have a fix ready by Friday."), "the quote doesn't contain the name"),
        (guess("Speaker 2", "Priya", "addressed_then_answered", "Priya, can you take this?"), "quote not in the transcript"),
        (guess("Speaker 2", "everyone", "addressed_then_answered", "Good morning, everyone."), "not a person's name"),
        (guess("Speaker 9", "Neha", "addressed_then_answered", "Neha, can you give us an update"), "unknown speaker label"),
    ],
)
def test_names_need_evidence_that_holds_up(g: NameGuess, problem: str | None) -> None:
    assert check_guess(g, SEGMENTS, LABELS) == problem


class FakeClient:
    def __init__(self, guesses: list[dict[str, str]]) -> None:
        self.reply = json.dumps({"guesses": guesses})
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply), finish_reason="stop")])


def test_proven_names_replace_labels_and_unproven_ones_stay() -> None:
    client = FakeClient([
        {"speaker": "Speaker 2", "name": "Neha", "evidence": "addressed_then_answered", "quote": "Neha, can you give us an update"},
        {"speaker": "Speaker 3", "name": "Tom", "evidence": "introduced_themselves", "quote": "this is Tom from the platform team"},
        {"speaker": "Speaker 4", "name": "Rahul", "evidence": "addressed_then_answered", "quote": "Rahul said yesterday"},
    ])

    segments, names, warnings = name_speakers(SEGMENTS, client, "m")

    assert [s.speaker for s in segments] == ["Speaker 1", "Speaker 1", "Neha", "Tom", "Speaker 1", "Speaker 4"]
    assert [(n.label, n.name, n.how) for n in names] == [
        ("Speaker 2", "Neha", "was addressed by name and answered"),
        ("Speaker 3", "Tom", "introduced themselves"),
    ]
    assert names[0].start == 3
    assert warnings == []


def test_contradictory_names_are_dropped() -> None:
    client = FakeClient([
        {"speaker": "Speaker 2", "name": "Neha", "evidence": "addressed_then_answered", "quote": "Neha, can you give us an update"},
        {"speaker": "Speaker 3", "name": "Neha", "evidence": "addressed_then_answered", "quote": "Neha, can you give us an update"},
    ])

    segments, names, _ = name_speakers(SEGMENTS, client, "m")

    assert names[0].name == "Neha" and len(names) == 1  # Speaker 3's guess failed its own check


def test_no_labels_means_no_naming_call() -> None:
    plain = [Segment(start=0, end=1, text="Hello.")]

    segments, names, warnings = name_speakers(plain, client=None, model="m")

    assert (segments, names, warnings) == (plain, [], [])


def test_documenter_can_attribute_i_will_to_a_named_speaker() -> None:
    named = [s.model_copy(update={"speaker": {"Speaker 2": "Neha", "Speaker 3": "Tom"}.get(s.speaker or "", s.speaker)}) for s in SEGMENTS]
    record = {
        "summary": "s", "minutes": [], "decisions": [], "open_items": [],
        "action_items": [
            {"task": "Fix the Android crash", "owner": "Neha", "deadline": "by Friday",
             "evidence": {"segment_ids": [2], "quote": "I'll have a fix ready by Friday"}},
            {"task": "Unnamed task", "owner": "Speaker 4", "deadline": None,
             "evidence": {"segment_ids": [5], "quote": "Great."}},
        ],
    }
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(record)), finish_reason="stop")])
    calls: list[dict[str, Any]] = []
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: calls.append(kw) or reply)))

    result = document(Transcript(segments=named), client, "m", max_request_tokens=100_000)

    assert "[2] (00:06) Neha: Sure. I'll have a fix ready by Friday." in calls[0]["messages"][1]["content"]
    assert result.action_items[0].owner == "Neha"  # stated: Neha is the identified speaker of that line
    assert result.action_items[1].owner is None  # a label is not a name


@pytest.mark.parametrize(
    ("quote", "ok"),
    [
        ("Neha, can you give us an update", True),
        ("Great, thanks. Rahul, anything on the analytics side?", True),
        ("Can you take a look, Neha?", True),
        ("Rahul said yesterday that the build is green", False),
        ("we should ask Neha about it", False),
    ],
)
def test_addressed_means_said_to_someone(quote: str, ok: bool) -> None:
    segments = [
        Segment(start=0, end=3, text=quote, speaker="Speaker 1"),
        Segment(start=3, end=6, text="Sure.", speaker="Speaker 2"),
    ]
    name = "Neha" if "Neha" in quote else "Rahul"
    problem = check_guess(guess("Speaker 2", name, "addressed_then_answered", quote), segments, {"Speaker 1", "Speaker 2"})
    assert (problem is None) is ok
