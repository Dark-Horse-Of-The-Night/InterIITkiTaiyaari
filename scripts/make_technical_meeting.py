"""Generate a jargon-heavy ML/maths review meeting (3 voices) that gives the refiner real work.

Usage, from the project root (macOS only, uses `say`):
    python3 scripts/make_technical_meeting.py

Technical terms are written the way people SAY them ("atom optimizer", "onyx",
"int eight"), which is how speech recognition tends to write them down. The refined
transcript should restore the proper terms (Adam, ONNX, INT8...) without touching
names, numbers, negations or commitments.

Writes scratch/technical_meeting.m4a and scratch/technical_meeting_expected.txt.
"""

import subprocess
import tempfile
from pathlib import Path

# (voice, speaker, what they say)
LINES = [
    ("Samantha", "Host", "Let's review the model results. Priya, how did training go?"),
    ("Karen", "Priya", "We fine tuned the bert base model with pie torch on two A one hundreds."),
    ("Karen", "Priya", "I used the atom optimizer with a learning rate of three e minus four, and a cosine schedule with warm up."),
    ("Samantha", "Host", "What about the eigen value problem in the P C A step?"),
    ("Rishi", "Arjun", "The covariance matrix was singular, so the eigen decomposition failed."),
    ("Rishi", "Arjun", "I switched to S V D in num pie, and now the top fifty principal components explain ninety percent of the variance."),
    ("Samantha", "Host", "Good. Did we check the L two norm of the gradients?"),
    ("Rishi", "Arjun", "Yes. Gradient clipping fixed the exploding gradients, and the F one score went up to zero point eight seven."),
    ("Daniel", "Tom", "Hi, this is Tom. For deployment, I'll export the model to onyx and serve it with tensor R T on the G P U nodes in our cube er netties cluster."),
    ("Samantha", "Host", "Will latency stay under fifty milliseconds at the P ninety nine?"),
    ("Daniel", "Tom", "Not yet. With a batch size of thirty two it's about seventy milliseconds. I'll profile it with en sight and try int eight quantization."),
    ("Samantha", "Host", "Okay. We decided to keep the cross entropy loss and not switch to focal loss."),
    ("Samantha", "Host", "Arjun, can you write up the a b test plan by Thursday?"),
    ("Rishi", "Arjun", "Sure, I'll have the A B test plan ready by Thursday."),
    ("Samantha", "Host", "Great. Let's also log every run to weights and biases. Thanks, everyone."),
]

PAUSE_SECONDS = 0.6

EXPECTED_FIXES = [
    "bert -> BERT", "pie torch -> PyTorch", "A one hundreds -> A100s", "atom optimizer -> Adam optimizer",
    "eigen value / eigen decomposition -> eigenvalue / eigendecomposition", "P C A -> PCA", "S V D -> SVD",
    "num pie -> NumPy", "L two norm -> L2 norm", "F one score -> F1 score", "onyx -> ONNX", "tensor R T -> TensorRT",
    "G P U -> GPU", "cube er netties -> Kubernetes", "P ninety nine -> P99", "en sight -> Nsight",
    "int eight -> INT8", "a b test -> A/B test", "weights and biases -> Weights & Biases",
]
MUST_NOT_CHANGE = [
    "Names: Priya, Arjun, Tom", "Numbers: 'three e minus four', 'fifty', 'ninety percent', 'zero point eight seven',"
    " 'thirty two', 'seventy milliseconds', 'by Thursday'", "Negations: 'Not yet', 'not switch to focal loss'",
    "Commitments: 'I'll export', 'I'll profile', 'I'll have ... ready', 'We decided'",
]


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
            aiff, wav = tmp_dir / f"l{i:02d}.aiff", tmp_dir / f"l{i:02d}.wav"
            subprocess.run(["say", "-v", voice, "-r", "170", "-o", str(aiff), text], check=True)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ar", "22050", "-ac", "1", str(wav)], check=True)
            pieces += [wav, silence]
        (tmp_dir / "list.txt").write_text("".join(f"file '{p}'\n" for p in pieces))
        output = out_dir / "technical_meeting.m4a"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(tmp_dir / "list.txt"),
                        "-c:a", "aac", "-b:a", "64k", str(output)], check=True)

    expected = ["Script (who says what):"] + [f"  {who:6} | {text}" for _, who, text in LINES]
    expected += ["", "Terms the refiner should fix (if speech recognition writes them as spoken):"]
    expected += [f"  {fix}" for fix in EXPECTED_FIXES]
    expected += ["", "Must stay exactly as spoken:"] + [f"  {item}" for item in MUST_NOT_CHANGE]
    (out_dir / "technical_meeting_expected.txt").write_text("\n".join(expected) + "\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
