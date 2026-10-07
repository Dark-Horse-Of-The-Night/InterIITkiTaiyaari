"""Try stage 2 (refiner) and print what it changed.

Usage, from the backend/ folder:
    .venv/bin/python scripts/run_refine.py path/to/recording.mp3      # stages 1 + 2
    .venv/bin/python scripts/run_refine.py path/to/transcript.txt     # stage 2 only, one segment per line
    .venv/bin/python scripts/run_refine.py FILE --glossary "Zephyr,KubeFlow"
"""

import argparse
import sys
from pathlib import Path

# Let this script import the app package when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.pipeline.errors import PipelineError  # noqa: E402
from app.pipeline.models import Segment, Transcript  # noqa: E402
from app.pipeline.refiner import make_refiner_client, refine  # noqa: E402
from app.pipeline.stt import make_stt_client, transcribe_file  # noqa: E402


def load_text_transcript(path: Path) -> Transcript:
    """Read a .txt file as a transcript: one segment per non-empty line, 5 s apart."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return Transcript(segments=[Segment(start=i * 5.0, end=i * 5.0 + 5, text=line) for i, line in enumerate(lines)])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the refiner on an audio file or a .txt transcript.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--glossary", default="", help="comma-separated terms used in the meeting")
    args = parser.parse_args()

    try:
        settings = load_settings()
        if args.file.suffix.lower() == ".txt":
            transcript = load_text_transcript(args.file)
        else:
            stt_client = make_stt_client(settings)
            transcript = transcribe_file(args.file, stt_client, settings.stt_model, settings.max_upload_mb)
        refined = refine(transcript, make_refiner_client(settings), settings.refiner_model, args.glossary.split(","))
    except (ConfigError, PipelineError) as error:
        print(f"Error: {error}")
        return 1

    print("=== Changed segments ===")
    for i, (old, new) in enumerate(zip(transcript.segments, refined.segments)):
        if old.text != new.text:
            print(f"[{i + 1}] before: {old.text}\n    after:  {new.text}")

    print("\n=== Corrections ===")
    for c in refined.corrections or []:
        print(f"segment {c.segment_id + 1}: {c.before!r} -> {c.after!r}")
    if not refined.corrections:
        print("(none)")

    print("\n=== Warnings (edits rejected by safety checks) ===")
    print("\n".join(refined.warnings) if refined.warnings else "(none)")

    print(f"\n{len(refined.segments)} segments, model: {settings.refiner_model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
