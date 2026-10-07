import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest

import app.pipeline.audio as audio_module
from app.pipeline.audio import plan_cuts, prepare_chunks, validate_audio_file
from app.pipeline.errors import PipelineError


def make_tone_wav(path: Path, seconds: float = 1.0, rate: int = 44100) -> Path:
    """Write a short stereo sine-wave WAV file (a real, valid audio file)."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(int(seconds * rate)):
            sample = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            wav.writeframes(struct.pack("<hh", sample, sample))
    return path


def test_valid_wav_passes_and_returns_duration(tmp_path: Path) -> None:
    audio = make_tone_wav(tmp_path / "meeting.wav", seconds=1.0)

    assert validate_audio_file(audio, max_upload_mb=25) == pytest.approx(1.0, abs=0.05)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    document = tmp_path / "notes.pdf"
    document.write_bytes(b"%PDF-1.4 not audio")

    with pytest.raises(PipelineError, match="'.pdf' files are not supported") as error:
        validate_audio_file(document, max_upload_mb=25)
    assert ".mp3" in str(error.value)  # tells the user what IS accepted


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp3"
    empty.touch()

    with pytest.raises(PipelineError, match="the file is empty"):
        validate_audio_file(empty, max_upload_mb=25)


def test_oversized_file_is_rejected(tmp_path: Path) -> None:
    big = tmp_path / "big.wav"
    big.write_bytes(b"\0" * (2 * 1024 * 1024))  # 2 MB

    with pytest.raises(PipelineError, match="above the 1 MB limit"):
        validate_audio_file(big, max_upload_mb=1)


def test_fake_audio_file_is_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "song.mp3"
    fake.write_text("This is a text file pretending to be an mp3.")

    with pytest.raises(PipelineError, match="could not be read as audio"):
        validate_audio_file(fake, max_upload_mb=25)


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="was not found"):
        validate_audio_file(tmp_path / "nope.wav", max_upload_mb=25)


def make_wav_with_pauses(path: Path, pattern: list[tuple[str, float]], rate: int = 16000) -> Path:
    """A mono WAV made of ("tone", seconds) and ("silence", seconds) pieces."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for kind, seconds in pattern:
            for i in range(int(seconds * rate)):
                sample = int(8000 * math.sin(2 * math.pi * 300 * i / rate)) if kind == "tone" else 0
                wav.writeframes(struct.pack("<h", sample))
    return path


def probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_recording_over_the_duration_limit_is_rejected(tmp_path: Path) -> None:
    audio = make_tone_wav(tmp_path / "long.wav", seconds=2.0)

    with pytest.raises(PipelineError, match="above the 0-minute limit"):
        validate_audio_file(audio, max_upload_mb=25, max_audio_minutes=0)


def test_short_recording_becomes_one_mono_opus_part(tmp_path: Path) -> None:
    audio = make_tone_wav(tmp_path / "meeting.wav")  # stereo, 44.1 kHz

    chunks = prepare_chunks(audio, 1.0, tmp_path)

    assert len(chunks) == 1
    assert (chunks[0].start, chunks[0].end) == (0.0, 1.0)
    assert chunks[0].path.suffix == ".ogg"
    assert probe(chunks[0].path, "stream=codec_name,channels") == "opus,1"
    assert not (tmp_path / "full_16k_mono.wav").exists()  # temporary WAV cleaned up


def test_long_recording_is_split_at_pauses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Pretend a "chunk" is 10 s (instead of 10 min) so a 25 s file stands in for a long meeting.
    monkeypatch.setattr(audio_module, "CHUNK_SECONDS", 10)
    monkeypatch.setattr(audio_module, "CUT_SEARCH_SECONDS", 4)
    audio = make_wav_with_pauses(tmp_path / "long.wav", [
        ("tone", 7.0), ("silence", 1.0),   # pause 7-8 s, just before the 10 s mark
        ("tone", 9.0), ("silence", 1.0),   # pause 17-18 s, just before the next mark (8 + 10)
        ("tone", 7.0),
    ])

    chunks = prepare_chunks(audio, 25.0, tmp_path)

    assert [(c.start, c.end) for c in chunks] == [(0.0, pytest.approx(7.5, abs=0.15)),
                                                  (pytest.approx(7.5, abs=0.15), pytest.approx(17.5, abs=0.15)),
                                                  (pytest.approx(17.5, abs=0.15), 25.0)]
    total = sum(float(probe(c.path, "format=duration")) for c in chunks)
    assert total == pytest.approx(25.0, abs=0.3)  # nothing lost or duplicated


def test_cut_plan_without_pauses_cuts_at_the_marks() -> None:
    assert plan_cuts(1500, [], chunk_seconds=600, search_seconds=30) == [600, 1200]


def test_cut_plan_uses_latest_pause_before_each_mark() -> None:
    pauses = [(570, 571), (590, 592), (640, 641), (1150, 1152), (1170, 1172)]
    # 1st cut: pauses in 570..600 -> latest middle is 591.
    # 2nd mark: 591 + 600 = 1191, window 1161..1191 -> pause at 1171 (1151 is too early).
    assert plan_cuts(1700, pauses, chunk_seconds=600, search_seconds=30) == [591, 1171]


def test_cut_plan_merges_a_tiny_final_part() -> None:
    assert plan_cuts(650, [], chunk_seconds=600) == []  # 10 min + 50 s: one part, not a 50-second leftover
    assert plan_cuts(1250, [], chunk_seconds=600) == [600]  # 600 + 650
