"""Run all three stages on an audio file and save the outputs.

Usage, from the backend/ folder:
    .venv/bin/python scripts/run_pipeline.py path/to/recording.mp3 [--glossary "Zephyr,KubeFlow"]

Outputs go to scratch/output/<recording name>/:
    raw_transcript.txt, refined_transcript.txt, record.json, record.md
"""

import argparse
import sys
import time
from pathlib import Path

# Let this script import the app package when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.pipeline.documenter import document, make_documenter_client  # noqa: E402
from app.pipeline.errors import PipelineError  # noqa: E402
from app.pipeline.models import Transcript  # noqa: E402
from app.pipeline.refiner import make_refiner_client, refine  # noqa: E402
from app.pipeline.render import format_time, record_to_json, record_to_markdown  # noqa: E402
from app.pipeline.stt import make_stt_client, transcribe_file  # noqa: E402

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "scratch" / "output"


def transcript_lines(transcript: Transcript) -> str:
    return "\n".join(f"[{format_time(s.start)}] {s.text}" for s in transcript.segments) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full pipeline on an audio file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--glossary", default="", help="comma-separated terms used in the meeting")
    args = parser.parse_args()

    try:
        settings = load_settings()
        started = time.monotonic()
        raw = transcribe_file(args.file, make_stt_client(settings), settings.stt_model, settings.max_upload_mb)
        print(f"1/3 speech-to-text done: {len(raw.segments)} segments ({time.monotonic() - started:.1f}s)")
        refined = refine(raw, make_refiner_client(settings), settings.refiner_model, args.glossary.split(","))
        print(f"2/3 refiner done: {len(refined.corrections)} corrections ({time.monotonic() - started:.1f}s)")
        record = document(refined, make_documenter_client(settings), settings.documenter_model)
        print(f"3/3 documenter done ({time.monotonic() - started:.1f}s)")
    except (ConfigError, PipelineError) as error:
        print(f"Error: {error}")
        return 1

    out_dir = OUTPUT_ROOT / args.file.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_transcript.txt").write_text(transcript_lines(raw), encoding="utf-8")
    (out_dir / "refined_transcript.txt").write_text(transcript_lines(refined), encoding="utf-8")
    (out_dir / "record.json").write_text(record_to_json(record), encoding="utf-8")
    markdown = record_to_markdown(record)
    (out_dir / "record.md").write_text(markdown, encoding="utf-8")

    print(f"\nSaved to {out_dir}\n")
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
