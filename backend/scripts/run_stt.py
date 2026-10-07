"""Try stage 1 (speech-to-text) on an audio file and print the timestamped segments.

Usage, from the backend/ folder:
    .venv/bin/python scripts/run_stt.py path/to/recording.mp3
"""

import sys
from pathlib import Path

# Let this script import the app package when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.pipeline.errors import PipelineError  # noqa: E402
from app.pipeline.stt import make_stt_client, transcribe_file  # noqa: E402


def format_time(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    try:
        settings = load_settings()
        client = make_stt_client(settings)
        transcript = transcribe_file(Path(sys.argv[1]), client, settings.stt_model, settings.max_upload_mb)
    except (ConfigError, PipelineError) as error:
        print(f"Error: {error}")
        return 1

    for segment in transcript.segments:
        print(f"[{format_time(segment.start)} - {format_time(segment.end)}] {segment.text}")
    print(f"\n{len(transcript.segments)} segments, model: {settings.stt_model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
