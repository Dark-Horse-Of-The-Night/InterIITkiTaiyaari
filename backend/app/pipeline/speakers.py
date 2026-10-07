"""Label who spoke each segment ("Speaker 1", "Speaker 2"...) by comparing voices.

Part of stage 1 (speech-to-text). For every Whisper segment we compute a "voice
fingerprint" (a speaker embedding from SpeechBrain's ECAPA model, which runs locally),
then group segments whose fingerprints are similar. Groups are numbered in the order
they first speak. Real names are NOT decided here; see speaker_names.py.

Short segments ("Sure.", "Yes.") give weak fingerprints, and they are often the first
words of a new speaker's turn. So voices are grouped using only segments of 1.5 s or
more, and every shorter segment joins whichever group its voice is closest to.
Measured on the 5-voice test meeting: 23/23 segments in the right group, 5 groups.

Limitation: a segment that contains two people gets one label.

PyTorch and SpeechBrain are optional: if they're not installed, or the model can't be
loaded, transcripts simply have no speaker labels (and a note says so).
"""

import logging
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app.pipeline.models import Segment

logger = logging.getLogger("app.pipeline.speakers")

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"  # downloaded once from Hugging Face
RELIABLE_SECONDS = 1.5  # segments at least this long decide the voice groups
MIN_CLIP_SECONDS = 0.3  # shorter clips can't be fingerprinted; they take the previous label
# Two groups of segments are the same speaker if their average cosine distance is below this.
# Measured on the 5-voice test meeting: same person 0.41 on average, different people 0.83.
DISTANCE_THRESHOLD = 0.6


class VoiceEmbedder(Protocol):
    """Turns a clip of 16 kHz mono audio into a voice fingerprint (a vector)."""

    def embed(self, samples: Any) -> Any: ...


def label_speakers(segments: list[Segment], wav_path: Path, embedder: VoiceEmbedder) -> list[Segment]:
    """Return copies of `segments` with `speaker` set to "Speaker 1", "Speaker 2"..."""
    import numpy as np

    audio, rate = read_wav(wav_path)
    fingerprints: dict[int, Any] = {}
    for i, segment in enumerate(segments):
        clip = audio[int(segment.start * rate) : int(segment.end * rate)]
        if len(clip) >= MIN_CLIP_SECONDS * rate:
            vector = np.asarray(embedder.embed(clip), dtype=np.float32).reshape(-1)
            fingerprints[i] = vector / (np.linalg.norm(vector) or 1.0)
    if not fingerprints:
        return [s.model_copy(update={"speaker": "Speaker 1"}) for s in segments]

    # 1. Decide the voice groups from the reliable (longer) segments.
    reliable = [i for i in fingerprints if segments[i].end - segments[i].start >= RELIABLE_SECONDS]
    if len(reliable) < 2:
        reliable = list(fingerprints)
    groups = cluster(np.stack([fingerprints[i] for i in reliable]), DISTANCE_THRESHOLD)
    group_of = dict(zip(reliable, groups))
    centres = {}
    for group in set(groups):
        mean = np.mean([fingerprints[i] for i, g in group_of.items() if g == group], axis=0)
        centres[group] = mean / (np.linalg.norm(mean) or 1.0)

    # 2. Every other segment joins the closest group; unfingerprintable ones take the previous label.
    numbers: dict[int, int] = {}
    labelled: list[Segment] = []
    previous: int | None = None
    for i, segment in enumerate(segments):
        if i in group_of:
            group = group_of[i]
        elif i in fingerprints:
            group = max(centres, key=lambda g: float(fingerprints[i] @ centres[g]))
        else:
            group = previous if previous is not None else next(iter(centres))
        numbers.setdefault(group, len(numbers) + 1)  # numbered in order of first speaking
        labelled.append(segment.model_copy(update={"speaker": f"Speaker {numbers[group]}"}))
        previous = group
    return labelled


def cluster(fingerprints: Any, threshold: float) -> list[int]:
    """Average-linkage clustering on cosine distance. Returns a group id per fingerprint.

    Repeatedly merges the two closest groups until the closest pair is farther apart than
    `threshold`. (Plain NumPy; fine for the few hundred segments in a long meeting.)
    """
    import numpy as np

    vectors = fingerprints / np.linalg.norm(fingerprints, axis=1, keepdims=True)
    count = len(vectors)
    distance = 1.0 - vectors @ vectors.T
    np.fill_diagonal(distance, np.inf)
    sizes = np.ones(count)
    group = np.arange(count)
    while count > 1:
        i, j = np.unravel_index(np.argmin(distance), distance.shape)
        if distance[i, j] > threshold:
            break
        # Merge j into i; the distance to the merged group is the size-weighted average.
        merged = (sizes[i] * distance[i] + sizes[j] * distance[j]) / (sizes[i] + sizes[j])
        distance[i, :] = merged
        distance[:, i] = merged
        distance[i, i] = np.inf
        distance[j, :] = np.inf
        distance[:, j] = np.inf
        sizes[i] += sizes[j]
        group[group == j] = i
        count -= 1
    return [int(g) for g in group]


def read_wav(path: Path) -> tuple[Any, int]:
    """Read a 16-bit mono WAV as float32 samples in [-1, 1]."""
    import numpy as np

    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0, rate


class SpeechBrainEmbedder:
    """ECAPA speaker embeddings from SpeechBrain, running on the CPU."""

    def __init__(self, model_dir: Path) -> None:
        from speechbrain.inference.speaker import EncoderClassifier  # optional dependency

        source = str(model_dir) if (model_dir / "hyperparams.yaml").is_file() else MODEL_SOURCE
        self.model = EncoderClassifier.from_hparams(
            source=source,
            savedir=str(model_dir),
            overrides={"pretrained_path": source},
            run_opts={"device": "cpu"},
        )

    def embed(self, samples: Any) -> Any:
        import torch

        with torch.no_grad():
            return self.model.encode_batch(torch.from_numpy(samples).unsqueeze(0)).squeeze().numpy()


@lru_cache
def load_embedder(model_dir: str) -> VoiceEmbedder | None:
    """Load the speaker model once per server. None if PyTorch/SpeechBrain aren't available."""
    try:
        return SpeechBrainEmbedder(Path(model_dir))
    except Exception as error:  # missing packages, no network for the first download, etc.
        logger.warning("Speaker labels disabled: could not load the speaker model (%s)", error)
        return None
