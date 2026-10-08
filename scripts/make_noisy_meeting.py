"""Make a noisy copy of the Release sync sample, to show the "unclear audio" flags.

Usage, from the project root (needs ffmpeg):
    python3 scripts/make_noisy_meeting.py

Mixes loud pink noise (a hiss, like a bad call line) into samples/speakers_meeting/recording.m4a
and writes samples/noisy_meeting/recording.mp3. The noise drowns out some words, so speech
recognition gets parts wrong and reports low confidence there.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "samples" / "speakers_meeting" / "recording.m4a"
OUTPUT = ROOT / "samples" / "noisy_meeting" / "recording.mp3"
NOISE_LEVEL = 0.8  # pink noise amplitude; 0.25 is a mild hiss, 0.8 drops words
SEED = 7  # same noise every time


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-i", str(SOURCE),
            "-filter_complex",
            f"anoisesrc=color=pink:amplitude={NOISE_LEVEL}:seed={SEED}[n];[0:a][n]amix=inputs=2:duration=first:weights=1 1",
            "-ac", "1", "-ar", "16000", str(OUTPUT),
        ],
        check=True,
    )
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
