"""Label who spoke each segment ("Speaker 1", "Speaker 2"...) by comparing voices.

Part of stage 1 (speech-to-text). For every Whisper segment we compute a "voice
fingerprint" (a speaker embedding from SpeechBrain's ECAPA model, which runs locally),
then group segments whose fingerprints are similar. Groups are numbered in the order
they first speak. Real names are NOT decided here; see speaker_names.py.

Limitations: a segment that contains two people gets one label, and very short
segments (under a second) borrow the label of the segment before them.

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
MIN_SEGMENT_SECONDS = 0.8  # shorter segments don't hold enough voice to compare
# Two groups of segments are the same speaker if their average cosine distance is below this.
# Measured on the multi-voice test meeting (see docs/DESIGN.md).
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
        if segment.end - segment.start < MIN_SEGMENT_SECONDS:
            continue
        clip = audio[int(segment.start * rate) : int(segment.end * rate)]
        if len(clip) >= MIN_SEGMENT_SECONDS * rate:
            fingerprints[i] = np.asarray(embedder.embed(clip), dtype=np.float32).reshape(-1)

    if not fingerprints:
        return [s.model_copy(update={"speaker": "Speaker 1"}) for s in segments]

    indexes = list(fingerprints)
    groups = cluster(np.stack([fingerprints[i] for i in indexes]), DISTANCE_THRESHOLD)
    group_of = dict(zip(indexes, groups))

    # Number groups in the order they first speak; short segments inherit the previous label.
    numbers: dict[int, int] = {}
    labelled: list[Segment] = []
    previous = None
    for i, segment in enumerate(segments):
        group = group_of.get(i)
        if group is None:
            group = previous if previous is not None else _next_group(i, segments, group_of)
        numbers.setdefault(group, len(numbers) + 1)
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


def _next_group(i: int, segments: list[Segment], group_of: dict[int, int]) -> int:
    for j in range(i + 1, len(segments)):
        if j in group_of:
            return group_of[j]
    return next(iter(group_of.values()))


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
