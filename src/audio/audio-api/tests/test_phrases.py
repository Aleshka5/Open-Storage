"""US-04/UC-5 tests — phrase reading (incremental chat polling).

They cover the semantics of `MongoVoiceRepo.list_phrases` through `PhraseService.list_phrases`:
- an empty result when there are no phrases (items [] and next_after_seq unchanged);
- sorting by seq, the `label` is joined from `speakers`;
- the `seq > after_seq` filter;
- `side` defaults to `left` when there is no assignment;
- owner isolation (`FakeVoiceRepo.list_phrases` returns empty to a foreign owner, and
  `PhraseService` raises NOT_FOUND for a foreign recording);
- `next_after_seq` advances to the maximum seq in the response.
"""

from __future__ import annotations

import pytest

from app.application.recording_service import PhraseService
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.recording import Recording
from app.domain.status import RecordingStatus
from tests.conftest import OTHER_OWNER, OWNER, RECORDING
from tests.fakes import FakeRecordingRepo

SPEAKER_1 = "a1b2c3d4-1111-4111-8111-111111111111"
SPEAKER_2 = "a1b2c3d4-2222-4222-8222-222222222222"
FOREIGN_RECORDING = "cccccccc-0000-0000-0000-000000000000"


async def _seed_recording(repo: FakeRecordingRepo, owner: str, rid: str = RECORDING) -> None:
    rec = Recording(
        recording_id=rid,
        owner_user_id=owner,
        title="Lecture",
        status=RecordingStatus.TRANSCRIBING,
        audio_key=f"u/{owner}/rec/{rid}/original.wav",
        audio_content_type="audio/wav",
        audio_bytes=1600,
    )
    rec.processing = rec.default_processing()
    await repo.insert_recording(rec)


def _seed_speaker(voice_repo, speaker_id, *, owner=OWNER, label="Speaker 1", **kw):
    s = {
        "_id": speaker_id,
        "owner_user_id": owner,
        "recording_id": RECORDING,
        "speaker_key": "SPEAKER_00",
        "order_index": 1,
        "label": label,
        "nick_id": None,
        "is_me": False,
    }
    s.update(kw)
    voice_repo.speakers[speaker_id] = s
    return s


def _seed_phrase(
    voice_repo,
    phrase_id,
    *,
    speaker_id,
    seq,
    owner=OWNER,
    recording_id=RECORDING,
    **kw,
):
    p = {
        "_id": phrase_id,
        "owner_user_id": owner,
        "recording_id": recording_id,
        "speaker_id": speaker_id,
        "seq": seq,
        "start_ms": seq * 1000,
        "end_ms": seq * 1000 + 900,
        "text": f"phrase {seq}",
        "state": "final",
    }
    p.update(kw)
    voice_repo.phrases[phrase_id] = p
    return p


def _service(repo: FakeRecordingRepo, voice_repo, settings=None) -> PhraseService:
    from app.config import Settings

    return PhraseService(
        repo,
        settings
        or Settings(
            qdrant_url="http://qdrant:6333",
            voice_embedding_size=256,
        ),
        voice_repo=voice_repo,
    )


# --- (a) empty result ---


async def test_phrases_empty_when_no_phrases(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)

    assert result["items"] == []
    assert result["next_after_seq"] == 0


# --- (b) sorted by seq + label joined ---


async def test_phrases_sorted_by_seq_with_label(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    _seed_speaker(voice_repo, SPEAKER_2, label="Dima", speaker_key="SPEAKER_01", order_index=2)
    # Insertion in shuffled seq order.
    _seed_phrase(voice_repo, "p3", speaker_id=SPEAKER_2, seq=3)
    _seed_phrase(voice_repo, "p1", speaker_id=SPEAKER_1, seq=1)
    _seed_phrase(voice_repo, "p2", speaker_id=SPEAKER_1, seq=2)
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)

    seqs = [i["seq"] for i in result["items"]]
    assert seqs == [1, 2, 3]
    # The label comes from speakers and is not stored on the phrase.
    assert result["items"][0]["label"] == "Anya"
    assert result["items"][0]["id"] == "p1"
    assert result["items"][2]["label"] == "Dima"
    assert result["items"][2]["id"] == "p3"


# --- (c) after_seq filter ---


async def test_phrases_after_seq_filter(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    for n in range(1, 6):
        _seed_phrase(voice_repo, f"p{n}", speaker_id=SPEAKER_1, seq=n)
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=3, limit=200)

    seqs = [i["seq"] for i in result["items"]]
    assert seqs == [4, 5]


# --- (d) side defaults to left ---


async def test_phrases_side_defaults_left(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    # A phrase without the side field.
    _seed_phrase(voice_repo, "p1", speaker_id=SPEAKER_1, seq=1)
    _seed_phrase(voice_repo, "p2", speaker_id=SPEAKER_1, seq=2, side="right")
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)

    assert result["items"][0]["side"] == "left"
    assert result["items"][1]["side"] == "right"


# --- (e) owner isolation ---


async def test_phrases_exclude_foreign_owner(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya", owner=OWNER)
    _seed_phrase(voice_repo, "mine", speaker_id=SPEAKER_1, seq=1, owner=OWNER)
    # A foreign phrase in the same recording.
    _seed_phrase(voice_repo, "foreign", speaker_id=SPEAKER_1, seq=2, owner=OTHER_OWNER)
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)

    assert [i["id"] for i in result["items"]] == ["mine"]


async def test_voice_repo_list_phrases_foreign_recording_empty(voice_repo):
    # FakeVoiceRepo.list_phrases returns empty for a foreign recording_id (without crashing).
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    _seed_phrase(voice_repo, "p1", speaker_id=SPEAKER_1, seq=1)

    items, next_after_seq = await voice_repo.list_phrases(
        FOREIGN_RECORDING, OWNER, after_seq=0, limit=200
    )

    assert items == []
    assert next_after_seq == 0


async def test_phrases_foreign_recording_404(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER, RECORDING)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    _seed_phrase(voice_repo, "p1", speaker_id=SPEAKER_1, seq=1)
    svc = _service(repo, voice_repo)

    # A foreign owner on an existing recording — NOT_FOUND through PhraseService.
    with pytest.raises(AppError) as exc:
        await svc.list_phrases(OTHER_OWNER, RECORDING, after_seq=0, limit=200)
    assert exc.value.code == ErrorCode.NOT_FOUND


# --- (f) next_after_seq advances ---


async def test_phrases_next_after_seq_advances(voice_repo):
    repo = FakeRecordingRepo()
    await _seed_recording(repo, OWNER)
    _seed_speaker(voice_repo, SPEAKER_1, label="Anya")
    for n in range(1, 6):
        _seed_phrase(voice_repo, f"p{n}", speaker_id=SPEAKER_1, seq=n)
    svc = _service(repo, voice_repo)

    result = await svc.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)

    assert result["next_after_seq"] == 5
