"""diarizer domain: turns, speakers, ownership invariant.

No Pyannote, no Mongo, no MinIO here — only the rules that hold the
`docs/backend/diarizer/*` contracts and ADR-002/014. The diarization model is injected through
the `DiarizerModel` port (application/ports) so tests can drive synthetic data without a GPU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Pyannote speaker key — `SPEAKER_00`, `SPEAKER_01`, … (not the display label).
SPEAKER_KEY_FMT = "SPEAKER_{index:02d}"

# Centroid for future nicks: one vector per speaker (dimension = Qdrant collection).
CENTROID_DIM = 256


@dataclass(frozen=True)
class Turn:
    """One turn of the exclusive track: exactly one speaker at every moment."""

    speaker_key: str
    start_ms: int
    end_ms: int
    overlap: bool = False


@dataclass
class SpeakerSpec:
    """What diarizer writes to `speakers` for one voice."""

    speaker_key: str
    order_index: int
    centroid: list[float] | None


@dataclass
class DiarizationResult:
    """Result of one cluster for the whole file (ADR-002)."""

    turns: list[Turn] = field(default_factory=list)
    speakers: list[SpeakerSpec] = field(default_factory=list)
    duration_ms: int = 0


def owner_prefix(owner_id: str) -> str:
    """Ownership prefix for MinIO keys: `u/{owner}/`."""
    return f"u/{owner_id}/"


def norm_key_for(owner_id: str, recording_id: str) -> str:
    """`norm.wav` derivative key per the MinIO contract."""
    return f"{owner_prefix(owner_id)}rec/{recording_id}/norm.wav"


def key_belongs_to_owner(audio_key: str, owner_id: str) -> bool:
    """True if the object starts with `u/{owner}/` (otherwise it is foreign — reject it)."""
    return audio_key.startswith(owner_prefix(owner_id))


def source_extension(audio_key: str) -> str:
    """Source extension from the key (`original.m4a` -> `m4a`). None — `bin`."""
    name = audio_key.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot + 1 :] if dot >= 0 else "bin"


def sort_turns(turns: list[Turn]) -> list[Turn]:
    """Exclusive-track turns: by `start_ms`, then by `speaker_key` (stable)."""
    return sorted(turns, key=lambda t: (t.start_ms, t.speaker_key))


def validate_no_overlap(turns: list[Turn]) -> bool:
    """Turns are sorted and do not overlap (exclusive track)."""
    prev_end = -1
    for t in turns:
        if t.start_ms < prev_end:
            return False
        if t.end_ms <= t.start_ms:
            return False
        prev_end = t.end_ms
    return True


def build_speakers(
    turns: list[Turn],
    *,
    centroids: dict[str, list[float] | None],
) -> list[SpeakerSpec]:
    """Speakers by first appearance: `order_index` = 1..N (ADR-002 / D-02)."""
    first_seen: dict[str, int] = {}
    order = 0
    for turn in sort_turns(turns):
        if turn.speaker_key not in first_seen:
            order += 1
            first_seen[turn.speaker_key] = order
    specs: list[SpeakerSpec] = []
    for key, index in sorted(first_seen.items(), key=lambda kv: kv[1]):
        specs.append(
            SpeakerSpec(
                speaker_key=key,
                order_index=index,
                centroid=centroids.get(key),
            )
        )
    return specs
