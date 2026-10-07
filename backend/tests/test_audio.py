import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from app.pipeline.audio import prepare_for_stt, validate_audio_file
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


def test_prepare_converts_to_16k_mono_flac(tmp_path: Path) -> None:
    audio = make_tone_wav(tmp_path / "meeting.wav")

    prepared = prepare_for_stt(audio, tmp_path)

    assert prepared.suffix == ".flac"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", str(prepared)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "16000,1"
