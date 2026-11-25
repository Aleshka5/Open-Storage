"""asr-worker domain: turns, batches, phrases, ownership invariant.

No Parakeet, no Mongo, no MinIO here — only the rules that hold the
`docs/backend/asr-worker/*` contracts,
`docs/external_contracts/queue-audio-transcription/message.md`
and ADR-003/014. The transcription model is injected through the `AsrModel` port
(application/ports) so tests can drive synthetic data without a GPU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# MinIO ownership prefix: `u/{owner}/` (constitution §3, minio/bucket-and-keys.md).
OWNER_PREFIX = "u/{owner_id}/"


@dataclass(frozen=True)
class Turn:
    """One exclusive-track turn from an `audio.transcription` job.

    `seq` is the ordinal of the turn in the recording (`1..N`), not the completion order.
    It is assigned by the handler from the sorted input and carried across batches.
    """

    turn_id: str
    speaker_key: str
    start_ms: int
    end_ms: int
    overlap: bool = False
    seq: int = 0


@dataclass(frozen=True)
class Phrase:
    """What asr-worker writes to `phrases` for one turn.

    Owns the fields `text`, `state`, `revision`, `end_ms`, `start_ms`, `seq`,
    `speaker_id`, `overlap` (data-model.md, ownership map). `label`/`side` are
    NOT written here — `audio-api` changes them (nick / `Me` assignment).
    """

    seq: int
    speaker_id: str
    text: str
    start_ms: int
    end_ms: int
    overlap: bool


@dataclass
class TranscriptionOutput:
    """Result of transcribing one batch: text per turn + the model language."""

    texts: dict[int, str] = field(default_factory=dict)  # seq -> text
    language: str | None = None  # "ru" | "en" | None (detected by the model)


def owner_prefix(owner_id: str) -> str:
    """Ownership prefix for MinIO keys: `u/{owner}/`."""
    return OWNER_PREFIX.format(owner_id=owner_id)


def key_belongs_to_owner(audio_key: str, owner_id: str) -> bool:
    """True if the object starts with `u/{owner}/` (otherwise it is foreign — reject it)."""
    return audio_key.startswith(owner_prefix(owner_id))


def sort_turns(turns: list[Turn]) -> list[Turn]:
    """Exclusive-track turns: by `start_ms` (stable relative to the input)."""
    return sorted(turns, key=lambda t: t.start_ms)


#: Turns shorter than this are not recognisable on their own: Parakeet detects the language
#: per window, and on 20–400 ms of audio it guesses (a Russian interjection comes back as
#: "Oh." / "What?" / "A jednak."). Such turns are merged into a neighbour before ASR.
SHORT_TURN_MS = 400
#: Same-speaker turns separated by a shorter pause are one utterance.
MERGE_GAP_MS = 200
#: A merged window must stay short enough for the model and for the batch budget.
MAX_MERGED_MS = 12000


def _merge(a: Turn, b: Turn) -> Turn:
    """One turn covering both, attributed to the wider one (the neighbour that has speech)."""
    first = a if a.start_ms <= b.start_ms else b
    owner = a if (a.end_ms - a.start_ms) >= (b.end_ms - b.start_ms) else b
    return Turn(
        turn_id=first.turn_id,
        speaker_key=owner.speaker_key,
        start_ms=first.start_ms,
        end_ms=max(a.end_ms, b.end_ms),
        overlap=a.overlap or b.overlap,
        seq=0,
    )


def merge_short_turns(
    turns: list[Turn],
    *,
    short_ms: int = SHORT_TURN_MS,
    gap_ms: int = MERGE_GAP_MS,
    max_merged_ms: int = MAX_MERGED_MS,
) -> list[Turn]:
    """Collapses turns that are too short (or too close) into their neighbours.

    Two passes, both bounded by `max_merged_ms`:

    1. neighbouring turns of the same speaker with a pause shorter than `gap_ms` — one
       utterance, split by the diarizer at an arbitrary boundary;
    2. turns still shorter than `short_ms` — merged into the closest neighbour (the same
       speaker if there is one). A slice this short is usually either a diarization
       bleed-over of the neighbour or an interjection the model cannot identify alone;
       inside a wider window it is recognised correctly with the rest of the utterance.

    `seq` is left at 0: the caller assigns the ordinals in the final order.
    """
    ordered = sort_turns(
        [Turn(t.turn_id, t.speaker_key, t.start_ms, t.end_ms, t.overlap) for t in turns]
    )
    if len(ordered) < 2:
        return ordered

    def span(a: Turn, b: Turn) -> int:
        return max(a.end_ms, b.end_ms) - min(a.start_ms, b.start_ms)

    def join_adjacent(current: list[Turn]) -> list[Turn]:
        """Pass 1: same speaker, pause < `gap_ms` — one utterance."""
        out: list[Turn] = []
        for turn in current:
            prev = out[-1] if out else None
            if (
                prev is not None
                and prev.speaker_key == turn.speaker_key
                and not prev.overlap
                and not turn.overlap
                and 0 <= turn.start_ms - prev.end_ms < gap_ms
                and span(prev, turn) <= max_merged_ms
            ):
                out[-1] = _merge(prev, turn)
                continue
            out.append(turn)
        return out

    def absorb_one_short(current: list[Turn]) -> list[Turn]:
        """Pass 2: one turn shorter than `short_ms` joins its nearest neighbour."""
        if len(current) < 2:
            return current
        idx = next(
            (
                i
                for i, t in enumerate(current)
                if t.end_ms - t.start_ms < short_ms and not t.overlap
            ),
            None,
        )
        if idx is None:
            return current
        turn = current[idx]
        candidates = []
        for j in (idx - 1, idx + 1):
            if not 0 <= j < len(current):
                continue
            neighbour = current[j]
            if neighbour.overlap or span(turn, neighbour) > max_merged_ms:
                continue
            if j > idx:
                gap = max(0, turn.start_ms - neighbour.end_ms)
            else:
                gap = max(0, neighbour.start_ms - turn.end_ms)
            # The same speaker wins over a marginally closer other speaker.
            score = (0 if neighbour.speaker_key == turn.speaker_key else 1, gap)
            candidates.append((score, j))
        if not candidates:
            return current
        _, j = min(candidates)
        lo, hi = min(idx, j), max(idx, j)
        current = list(current)
        current[lo : hi + 1] = [_merge(current[lo], current[hi])]
        return current

    # Both passes feed each other: absorbing a sliver can make two same-speaker turns
    # adjacent, and joining them can expose another short turn. Iterate to a fixed point.
    merged = ordered
    while True:
        before = len(merged)
        merged = join_adjacent(merged)
        merged = absorb_one_short(merged)
        if len(merged) == before:
            return merged


def build_batches(
    turns: list[Turn],
    *,
    max_turns: int,
    max_seconds: int,
) -> list[list[Turn]]:
    """Groups turns into batches: up to `max_turns` turns OR `max_seconds` s of audio.

    Whichever triggers first wins; a batch never exceeds either limit. The turn
    order is preserved: `seq` = the turn's ordinal in the recording (not completion order).
    """
    turns = sort_turns(turns)
    batches: list[list[Turn]] = []
    current: list[Turn] = []
    current_width_ms = 0
    for turn in turns:
        width = max(1, turn.end_ms - turn.start_ms)
        would_exceed_turns = len(current) >= max_turns
        would_exceed_seconds = current and (turn.end_ms - current[0].start_ms) > max_seconds * 1000
        if current and (would_exceed_turns or would_exceed_seconds):
            batches.append(current)
            current = []
            current_width_ms = 0
        current.append(turn)
        current_width_ms += width
    if current:
        batches.append(current)
    return batches
