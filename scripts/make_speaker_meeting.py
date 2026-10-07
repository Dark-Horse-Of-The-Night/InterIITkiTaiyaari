"""Generate a multi-speaker test meeting with different macOS voices (macOS only, uses `say`).

Usage, from the project root:
    python3 scripts/make_speaker_meeting.py

Writes scratch/speakers_meeting.m4a and scratch/speakers_meeting_expected.txt (who said
each line, and which speakers can be named from what is said).

Five speakers. Three can be identified from the audio, two cannot:
- Neha and Rahul are addressed by name and answer straight away.
- Tom introduces himself.
- The host and the person asking about the App Store are never named, so they must stay
  "Speaker N" (guessing a name would be inventing it).
"""

import subprocess
import tempfile
from pathlib import Path

# (voice, who it really is, what they say)
LINES = [
    ("Samantha", "Host (never named)", "Good morning, everyone. Let's go through the mobile release."),
    ("Samantha", "Host (never named)", "Neha, can you give us an update on the Android crash?"),
    ("Karen", "Neha", "Sure. The crash comes from the image cache. I'll have a fix ready by Friday."),
    ("Samantha", "Host (never named)", "Great, thanks. Rahul, anything on the analytics side?"),
    ("Rishi", "Rahul", "Yes. I'd suggest we move our analytics from Firebase to Mixpanel. It's cheaper for our volume."),
    ("Daniel", "Tom", "Hi, this is Tom from the platform team. I think that's a good idea, and I'll set up the Mixpanel account this week."),
    ("Samantha", "Host (never named)", "Okay, let's do that. We'll switch to Mixpanel."),
    ("Moira", "Questioner (never named)", "Quick question. Does anyone know if the App Store review still takes a week?"),
    ("Rishi", "Rahul", "Last time it took about three days."),
    ("Samantha", "Host (never named)", "Good. Someone needs to update the release notes, but we can sort that out later."),
    ("Karen", "Neha", "I can't take that on this week, sorry."),
    ("Samantha", "Host (never named)", "No problem. That's everything. Thanks, everyone."),
]

PAUSE_SECONDS = 0.6


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "scratch"  # git-ignored
    out_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        silence = tmp_dir / "silence.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                        "-t", str(PAUSE_SECONDS), str(silence)], check=True)
        pieces = []
        for i, (voice, _, text) in enumerate(LINES):
            aiff = tmp_dir / f"line{i:02d}.aiff"
            wav = tmp_dir / f"line{i:02d}.wav"
            subprocess.run(["say", "-v", voice, "-r", "175", "-o", str(aiff), text], check=True)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ar", "22050", "-ac", "1", str(wav)], check=True)
            pieces += [wav, silence]
        concat_list = tmp_dir / "list.txt"
        concat_list.write_text("".join(f"file '{p}'\n" for p in pieces))
        output = out_dir / "speakers_meeting.m4a"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                        "-c:a", "aac", "-b:a", "64k", str(output)], check=True)

    expected = ["Who said each line (ground truth):"]
    expected += [f"  {who:26} | {voice:8} | {text}" for voice, who, text in LINES]
    expected += [
        "",
        "Expected speaker names: Neha (addressed, then answers), Rahul (addressed, then answers),",
        "Tom (introduces himself). The host and the questioner must stay unnamed (Speaker N).",
        "Expected owners: Neha -> fix the Android crash (by Friday); Tom -> set up the Mixpanel account (this week).",
        "Release notes: no owner (Neha declined) -> Unspecified.",
    ]
    (out_dir / "speakers_meeting_expected.txt").write_text("\n".join(expected) + "\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
