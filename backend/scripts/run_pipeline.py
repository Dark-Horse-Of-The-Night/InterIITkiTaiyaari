"""Run all three stages on an audio file and save the outputs.

Usage, from the backend/ folder:
    .venv/bin/python scripts/run_pipeline.py path/to/recording.mp3 [--glossary "Zephyr,KubeFlow"]

Outputs go to scratch/output/<recording name>/:
    raw_transcript.txt, refined_transcript.txt, record.json, record.md
"""

import argparse
import sys
from pathlib import Path

# Let this script import the app package when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.pipeline.errors import PipelineError  # noqa: E402
from app.pipeline.models import Transcript  # noqa: E402
from app.pipeline.render import format_time, record_to_json  # noqa: E402
from app.pipeline.run import PipelineClients, run_pipeline  # noqa: E402

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "scratch" / "output"


def transcript_lines(transcript: Transcript) -> str:
    return "\n".join(f"[{format_time(s.start)}] {s.speaker + ': ' if s.speaker else ''}{s.text}" for s in transcript.segments) + "\n"


def print_progress(stage: str, state: str, seconds: float | None) -> None:
    print(f"{stage}: done in {seconds}s" if state == "done" else f"{stage}: running...")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full pipeline on an audio file.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--glossary", default="", help="comma-separated terms used in the meeting")
    args = parser.parse_args()
    glossary = [term.strip() for term in args.glossary.split(",") if term.strip()]

    try:
        settings = load_settings()
        result = run_pipeline(
            args.file, settings, PipelineClients.from_settings(settings), glossary, print_progress,
            on_note=lambda stage, note: print(f"{stage}: {note}"),
            on_detail=lambda stage, detail: print(f"{stage}: {detail}"),
        )
    except (ConfigError, PipelineError) as error:
        print(f"Error: {error}")
        return 1

    out_dir = OUTPUT_ROOT / args.file.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_transcript.txt").write_text(transcript_lines(result.raw_transcript), encoding="utf-8")
    (out_dir / "refined_transcript.txt").write_text(transcript_lines(result.refined_transcript), encoding="utf-8")
    (out_dir / "record.json").write_text(record_to_json(result.record), encoding="utf-8")
    (out_dir / "record.md").write_text(result.markdown, encoding="utf-8")

    print(f"\nSaved to {out_dir}\n")
    print(result.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
