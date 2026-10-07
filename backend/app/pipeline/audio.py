"""Check uploaded audio files, then convert and split them for Whisper.

Long recordings are split into ~10-minute parts, cut at a pause in speech so no
word is cut in half. Each part is sent to Whisper separately.

Uses ffprobe/ffmpeg (installed with `brew install ffmpeg`) through subprocess.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.pipeline.errors import STAGE_FILE_CHECK, STAGE_STT, PipelineError

# Formats Groq's Whisper endpoint accepts.
SUPPORTED_EXTENSIONS = {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}

# Groq rejects audio files larger than this (free tier), so each part is checked after converting.
API_FILE_LIMIT_MB = 25

BYTES_PER_MB = 1024 * 1024

# Each part is sent as 16 kHz mono Opus at 32 kbps: about 0.24 MB per minute. Measured on a
# 13-minute meeting: same accuracy as lossless FLAC (2.1% word errors) at 1/5 of the size,
# which matters because uploading is the slowest step.
OPUS_BITRATE = "32k"

# Splitting long recordings.
CHUNK_SECONDS = 600  # aim for ~10-minute parts
CUT_SEARCH_SECONDS = 30  # look for a pause in the last 30 s before each 10-minute mark
SILENCE_NOISE_DB = -35  # quieter than this counts as a pause...
SILENCE_MIN_SECONDS = 0.2  # ...if it lasts at least this long (pauses between sentences are often 0.2-0.5 s)


@dataclass
class AudioChunk:
    """One part of the recording, ready to send to Whisper."""

    path: Path
    start: float  # seconds from the start of the whole recording
    end: float


def validate_audio_file(path: Path, max_upload_mb: int, max_audio_minutes: int | None = None) -> float:
    """Check the upload is a real, non-empty, supported audio file.

    Returns the audio duration in seconds. Raises PipelineError explaining any problem.
    """
    if not path.is_file():
        raise PipelineError(STAGE_FILE_CHECK, f"the file '{path.name}' was not found", "Upload the file again.")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        accepted = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise PipelineError(
            STAGE_FILE_CHECK,
            f"'{extension or 'no extension'}' files are not supported",
            f"Upload an audio file in one of these formats: {accepted}.",
        )

    size = path.stat().st_size
    if size == 0:
        raise PipelineError(STAGE_FILE_CHECK, "the file is empty (0 bytes)", "Upload a recording that contains audio.")

    if size > max_upload_mb * BYTES_PER_MB:
        raise PipelineError(
            STAGE_FILE_CHECK,
            f"the file is {size / BYTES_PER_MB:.1f} MB, above the {max_upload_mb} MB limit",
            "Upload a shorter or more compressed recording.",
        )

    duration = probe_audio_duration(path)
    if duration is None:
        raise PipelineError(
            STAGE_FILE_CHECK,
            "the file could not be read as audio (it may be corrupt or not really an audio file)",
            "Check that the recording plays on your computer, then upload it again.",
        )

    if max_audio_minutes is not None and duration > max_audio_minutes * 60:
        raise PipelineError(
            STAGE_FILE_CHECK,
            f"the recording is {duration / 60:.0f} minutes long, above the {max_audio_minutes}-minute limit",
            "Upload a shorter recording, or split it into parts.",
        )
    return duration


def probe_audio_duration(path: Path) -> float | None:
    """Return the duration in seconds if the file has a readable audio track, else None."""
    result = _run_tool(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type:format=duration",
            "-of", "json",
            str(path),
        ]
    )
    if result.returncode != 0:
        return None
    try:
        info = json.loads(result.stdout)
        has_audio = bool(info.get("streams"))
        duration = float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None
    return duration if has_audio and duration > 0 else None


def prepare_chunks(path: Path, duration: float, output_dir: Path) -> list[AudioChunk]:
    """Convert the recording and split it into parts of about 10 minutes (one part if it's short)."""
    wav_path = output_dir / "full_16k_mono.wav"
    _convert(["-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav_path)])

    silences = find_silences(wav_path) if duration > CHUNK_SECONDS * 1.1 else []
    bounds = [0.0, *plan_cuts(duration, silences, CHUNK_SECONDS, CUT_SEARCH_SECONDS), duration]

    chunks = []
    for number, (start, end) in enumerate(zip(bounds, bounds[1:]), start=1):
        chunk_path = output_dir / f"part_{number:02d}.ogg"
        _convert([
            "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(wav_path),
            "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", OPUS_BITRATE, str(chunk_path),
        ])
        _check_part_size(chunk_path)
        chunks.append(AudioChunk(path=chunk_path, start=start, end=end))
    wav_path.unlink(missing_ok=True)
    return chunks


def plan_cuts(
    duration: float,
    silences: list[tuple[float, float]],
    chunk_seconds: float = CHUNK_SECONDS,
    search_seconds: float = CUT_SEARCH_SECONDS,
) -> list[float]:
    """Where to cut, in seconds. Prefers the middle of the latest pause before each 10-minute mark.

    A final part shorter than 10% of a chunk is merged into the previous part instead.
    """
    cuts: list[float] = []
    start = 0.0
    while duration - start > chunk_seconds * 1.1:
        target = start + chunk_seconds
        pauses = [(a + b) / 2 for a, b in silences if target - search_seconds <= (a + b) / 2 <= target]
        cut = max(pauses) if pauses else target  # no pause found: cut exactly at the mark
        cuts.append(round(cut, 3))
        start = cut
    return cuts


def find_silences(wav_path: Path) -> list[tuple[float, float]]:
    """Pauses in speech as (start, end) seconds, using ffmpeg's silencedetect filter."""
    result = _run_tool([
        "ffmpeg", "-v", "info", "-i", str(wav_path),
        "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_SECONDS}", "-f", "null", "-",
    ])
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", result.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", result.stderr)]
    return list(zip(starts, ends))


def _convert(arguments: list[str]) -> None:
    """Run an ffmpeg conversion, with a clear error if it fails."""
    output = Path(arguments[-1])
    result = _run_tool(["ffmpeg", "-y", "-v", "error", *arguments])
    if result.returncode != 0 or not output.is_file():
        raise PipelineError(
            STAGE_FILE_CHECK,
            "the audio could not be converted for transcription",
            "Check that the recording plays on your computer, or try exporting it as .mp3 or .wav.",
        )


def _check_part_size(chunk_path: Path) -> None:
    size = chunk_path.stat().st_size
    if size > API_FILE_LIMIT_MB * BYTES_PER_MB:  # shouldn't happen: a 10-minute part is ~2.5 MB
        raise PipelineError(
            STAGE_STT,
            f"a part of the recording is too large to send ({size / BYTES_PER_MB:.0f} MB; the limit is {API_FILE_LIMIT_MB} MB)",
            "Try exporting the recording as .mp3 or .wav and upload it again.",
        )


def _run_tool(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg/ffprobe, with a clear error if ffmpeg isn't installed."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise PipelineError(
            STAGE_FILE_CHECK, "ffmpeg is not installed on the server", "Install it with: brew install ffmpeg"
        ) from None
    except subprocess.TimeoutExpired:
        raise PipelineError(
            STAGE_FILE_CHECK, "processing the audio took too long", "Try a shorter recording."
        ) from None
