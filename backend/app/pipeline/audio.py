"""Check uploaded audio files and convert them into the format Whisper works best with.

Uses ffprobe/ffmpeg (installed with `brew install ffmpeg`) through subprocess.
"""

import json
import subprocess
from pathlib import Path

from app.pipeline.errors import STAGE_FILE_CHECK, STAGE_STT, PipelineError

# Formats Groq's Whisper endpoint accepts.
SUPPORTED_EXTENSIONS = {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}

# Groq rejects audio files larger than this (free tier), so we check after converting.
API_FILE_LIMIT_MB = 25

BYTES_PER_MB = 1024 * 1024


def validate_audio_file(path: Path, max_upload_mb: int) -> float:
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


def prepare_for_stt(path: Path, output_dir: Path) -> Path:
    """Convert to 16 kHz mono FLAC (Groq's recommended format; much smaller, same accuracy)."""
    output_path = output_dir / f"{path.stem}_16k_mono.flac"
    result = _run_tool(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(output_path)]
    )
    if result.returncode != 0 or not output_path.is_file():
        raise PipelineError(
            STAGE_FILE_CHECK,
            "the audio could not be converted for transcription",
            "Check that the recording plays on your computer, or try exporting it as .mp3 or .wav.",
        )

    size = output_path.stat().st_size
    if size > API_FILE_LIMIT_MB * BYTES_PER_MB:
        raise PipelineError(
            STAGE_STT,
            f"the recording is too long (about {size / BYTES_PER_MB:.0f} MB after compression; the limit is {API_FILE_LIMIT_MB} MB)",
            "Recordings longer than roughly 25 minutes are not supported yet. Upload a shorter section.",
        )
    return output_path


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
