"""US-06 tests — suggestions and nicks (UC-9/UC-10).

They cover the acceptance criteria:
- owner isolation (a foreign nick → 404, a foreign speaker → 404);
- the owner filter is mandatory (the type has no search method without owner_id);
- assigning the same nick is idempotent (200, unchanged);
- 409 ASSIGNMENT_LOCKED for a different nick to an already assigned speaker;
- name reuse (reused:true, no new point);
- Qdrant unavailable → the nick is still created, the point is not;
- `centroid is None` → empty suggestions without a crash;
- an is_me speaker → empty items, current=me.
"""

from __future__ import annotations

import pytest

from app.application.nick_service import NickService
from app.application.ports.voice_index import VoiceIndex
from app.config import Settings
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.voice import name_key, nick_point_id
from tests.conftest import OTHER_OWNER, OWNER, RECORDING

SPEAKER_1 = "a1b2c3d4-1111-4111-8111-111111111111"
SPEAKER_2 = "a1b2c3d4-2222-4222-8222-222222222222"
NICK_1 = "n1n20000-0000-4000-8000-000000000001"
NICK_2 = "n1n20000-0000-4000-8000-000000000002"

CENTROID = [0.1] * 256


def _settings() -> Settings:
    return Settings(
        qdrant_url="http://qdrant:6333",
        suggestion_limit=5,
        voice_embedding_size=256,
    )


def _service(repo, index, settings=None) -> NickService:
    return NickService(repo, index, settings or _settings())


def _seed_speaker(repo, *, speaker_id=SPEAKER_1, owner=OWNER, centroid=CENTROID, **kw):
    s = {
        "_id": speaker_id,
        "owner_user_id": owner,
        "recording_id": RECORDING,
        "speaker_key": "SPEAKER_00",
        "order_index": 1,
        "centroid": list(centroid) if centroid is not None else None,
        "label": "Speaker 1",
        "nick_id": None,
        "is_me": False,
    }
    s.update(kw)
    repo.speakers[speaker_id] = s
    return s


def _seed_nick(repo, *, nick_id=NICK_1, owner=OWNER, name="Anya"):
    n = {
        "_id": nick_id,
        "owner_user_id": owner,
        "name": name,
        "name_key": name_key(name),
        "created_from": {"recording_id": RECORDING, "speaker_id": SPEAKER_1},
        "created_at": "2026-11-01T00:00:00Z",
    }
    repo.nicks[nick_id] = n
    return n


def _seed_phrase(repo, *, phrase_id, speaker_id, owner=OWNER, side="left"):
    repo.phrases[phrase_id] = {
        "_id": phrase_id,
        "owner_user_id": owner,
        "recording_id": RECORDING,
        "speaker_id": speaker_id,
        "seq": len(repo.phrases) + 1,
        "side": side,
        "text": "…",
        "state": "final",
    }


# --- owner isolation ---


async def test_suggestions_foreign_speaker_404(voice_repo, voice_index):
    _seed_speaker(voice_repo, owner=OWNER)
    svc = _service(voice_repo, voice_index)
    with pytest.raises(AppError) as exc:
        await svc.suggestions(OTHER_OWNER, RECORDING, SPEAKER_1)
    assert exc.value.code == ErrorCode.NOT_FOUND


async def test_assign_foreign_nick_404(voice_repo, voice_index):
    _seed_speaker(voice_repo, owner=OWNER)
    _seed_nick(voice_repo, owner=OWNER)
    svc = _service(voice_repo, voice_index)
    with pytest.raises(AppError) as exc:
        await svc.assign(OTHER_OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)
    assert exc.value.code == ErrorCode.NOT_FOUND


async def test_search_scoped_to_owner(voice_repo, voice_index):
    # A nick point belongs only to its owner; a foreign owner does not see it in a search.
    _seed_speaker(voice_repo, owner=OWNER)
    voice_index.points[nick_point_id(OWNER, NICK_1)] = {
        "vector": CENTROID,
        "payload": {
            "owner_user_id": OWNER,
            "kind": "nick",
            "nick_id": NICK_1,
            "name": "Anya",
        },
    }
    svc = _service(voice_repo, voice_index)
    r = await svc.suggestions(OWNER, RECORDING, SPEAKER_1)
    assert len(r["items"]) == 1
    # A second owner: the same speaker is not theirs — 404, not data.
    with pytest.raises(AppError):
        await svc.suggestions(OTHER_OWNER, RECORDING, SPEAKER_1)


# --- the filter is mandatory (typing, not a silent scan) ---


def test_voice_index_search_has_no_ownerless_signature():
    # There is no search method without owner_id: the signature requires owner_id, so a call
    # without it is a type error before runtime (acceptance criterion).
    import inspect

    sig = inspect.signature(VoiceIndex.search)
    params = list(sig.parameters)
    assert "owner_id" in params


# --- idempotency + ASSIGNMENT_LOCKED ---


async def test_assign_same_nick_twice_idempotent(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo)
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    svc = _service(voice_repo, voice_index)

    r1 = await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)
    r2 = await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)

    assert r1["phrases_updated"] == 1
    assert r2["phrases_updated"] == 1  # a repeat: the same state
    assert voice_repo.speakers[SPEAKER_1]["label"] == "Anya"
    assert voice_repo.speakers[SPEAKER_1]["nick_id"] == NICK_1


async def test_assign_different_nick_to_assigned_speaker_409(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo, nick_id=NICK_1, name="Anya")
    _seed_nick(voice_repo, nick_id=NICK_2, name="Dima")
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    svc = _service(voice_repo, voice_index)

    await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)
    with pytest.raises(AppError) as exc:
        await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_2)
    assert exc.value.code == ErrorCode.ASSIGNMENT_LOCKED
    # The labels did not change (they are still "Anya").
    assert voice_repo.speakers[SPEAKER_1]["label"] == "Anya"


async def test_assign_me_to_nick_assigned_speaker_409(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo)
    svc = _service(voice_repo, voice_index)
    await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)
    with pytest.raises(AppError) as exc:
        await svc.assign(OWNER, RECORDING, SPEAKER_1, me=True)
    assert exc.value.code == ErrorCode.ASSIGNMENT_LOCKED


# --- name reuse ---


async def test_new_nick_with_existing_name_reused(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo, nick_id=NICK_1, name="Anya")
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    svc = _service(voice_repo, voice_index)

    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, name="Anya")

    assert r["nick"]["reused"] is True
    assert r["nick"]["id"] == NICK_1
    # No new point appeared in Qdrant (we only assign, we do not write a new one).
    assert voice_index.upserted_points == []


async def test_new_nick_with_casefold_match_reused(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo, nick_id=NICK_1, name="Anya")  # name_key = "anya"
    svc = _service(voice_repo, voice_index)
    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, name="  anya ")
    assert r["nick"]["reused"] is True
    assert r["nick"]["id"] == NICK_1


async def test_new_nick_creates_point_from_centroid(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    svc = _service(voice_repo, voice_index)

    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, name="Anya")

    assert r["nick"]["reused"] is False
    nick_id = r["nick"]["id"]
    point_id = nick_point_id(OWNER, nick_id)
    assert point_id in voice_index.points
    assert voice_index.points[point_id]["payload"]["kind"] == "nick"
    assert voice_repo.speakers[SPEAKER_1]["label"] == "Anya"


# --- Qdrant unavailable ---


async def test_qdrant_down_nick_still_created(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    voice_index.available = False
    svc = _service(voice_repo, voice_index)

    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, name="Anya")

    assert r["nick"]["reused"] is False
    nick_id = r["nick"]["id"]
    assert voice_repo.nicks[nick_id]["name"] == "Anya"
    assert voice_index.upserted_points == []  # the point is not written
    assert voice_repo.speakers[SPEAKER_1]["label"] == "Anya"


async def test_suggestions_qdrant_down_returns_503(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    voice_index.available = False
    svc = _service(voice_repo, voice_index)
    with pytest.raises(AppError) as exc:
        await svc.suggestions(OWNER, RECORDING, SPEAKER_1)
    assert exc.value.code == ErrorCode.VOICE_INDEX_UNAVAILABLE


# --- centroid None and is_me


async def test_suggestions_null_centroid_empty_items(voice_repo, voice_index):
    _seed_speaker(voice_repo, centroid=None)
    svc = _service(voice_repo, voice_index)
    r = await svc.suggestions(OWNER, RECORDING, SPEAKER_1)
    assert r["items"] == []
    assert r["speaker"]["current"] == {"kind": "none"}


async def test_suggestions_is_me_speaker_empty(voice_repo, voice_index):
    _seed_speaker(voice_repo, is_me=True, nick_id=None, label="Me")
    svc = _service(voice_repo, voice_index)
    r = await svc.suggestions(OWNER, RECORDING, SPEAKER_1)
    assert r["items"] == []
    assert r["speaker"]["current"] == {"kind": "me"}


# --- "Me" first, current=none, limit ---


async def test_suggestions_me_first_then_nicks(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    # The "Me" point and two nicks.
    voice_index.points[nick_point_id(OWNER, "me")] = {
        "vector": CENTROID,
        "payload": {"owner_user_id": OWNER, "kind": "me"},
    }
    for nid, nm in [(NICK_1, "Anya"), (NICK_2, "Dima")]:
        voice_index.points[nick_point_id(OWNER, nid)] = {
            "vector": CENTROID,
            "payload": {
                "owner_user_id": OWNER,
                "kind": "nick",
                "nick_id": nid,
                "name": nm,
            },
        }
    svc = _service(voice_repo, voice_index)
    r = await svc.suggestions(OWNER, RECORDING, SPEAKER_1)

    assert r["speaker"]["current"] == {"kind": "none"}  # no preselection
    kinds = [i["kind"] for i in r["items"]]
    assert kinds[0] == "me"
    # The nicks follow "Me", no more than limit.
    assert len([k for k in kinds if k == "nick"]) <= 5


async def test_suggestions_respect_limit(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    for i in range(10):
        nid = f"n1n20000-0000-4000-8000-0000000000{i:02d}"
        voice_index.points[nick_point_id(OWNER, nid)] = {
            "vector": CENTROID,
            "payload": {
                "owner_user_id": OWNER,
                "kind": "nick",
                "nick_id": nid,
                "name": f"Nick{i}",
            },
        }
    svc = _service(voice_repo, voice_index)
    r = await svc.suggestions(OWNER, RECORDING, SPEAKER_1)
    assert len(r["items"]) <= 5


# --- merging two speakers ---


async def test_merge_two_speakers_same_nick(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_speaker(voice_repo, speaker_id=SPEAKER_2, speaker_key="SPEAKER_01", order_index=2)
    _seed_nick(voice_repo, nick_id=NICK_1, name="Anya")
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    _seed_phrase(voice_repo, phrase_id="p2", speaker_id=SPEAKER_2)
    svc = _service(voice_repo, voice_index)

    r1 = await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)
    r2 = await svc.assign(OWNER, RECORDING, SPEAKER_2, nick_id=NICK_1)

    assert r1["phrases_updated"] == 1
    assert r2["phrases_updated"] == 1
    assert voice_repo.speakers[SPEAKER_1]["label"] == "Anya"
    assert voice_repo.speakers[SPEAKER_2]["label"] == "Anya"


# --- "Me": side set to right ---


async def test_assign_me_sets_phrases_right(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1)
    svc = _service(voice_repo, voice_index)

    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, me=True)

    assert r["speaker"]["is_me"] is True
    assert r["speaker"]["label"] == "Me"
    assert voice_repo.phrases["p1"]["side"] == "right"
    assert r["phrases_updated"] == 1


async def test_assign_nick_sets_phrases_left(voice_repo, voice_index):
    _seed_speaker(voice_repo)
    _seed_nick(voice_repo, nick_id=NICK_1, name="Anya")
    _seed_phrase(voice_repo, phrase_id="p1", speaker_id=SPEAKER_1, side="right")
    svc = _service(voice_repo, voice_index)

    r = await svc.assign(OWNER, RECORDING, SPEAKER_1, nick_id=NICK_1)

    assert voice_repo.phrases["p1"]["side"] == "left"
    assert r["phrases_updated"] == 1


# --- Deterministic point ids and name validation ---


def test_point_id_matches_contract_formula():
    import uuid

    # qdrant/collection.md contract + ADR-008: uuid5(owner_id, "me") and
    # uuid5(owner_id, "nick:"+nick_id), owner_id used as the namespace directly.
    assert nick_point_id(OWNER, NICK_1) == str(uuid.uuid5(uuid.UUID(OWNER), f"nick:{NICK_1}"))
    from app.domain.voice import me_point_id

    assert me_point_id(OWNER) == str(uuid.uuid5(uuid.UUID(OWNER), "me"))


def test_me_and_nick_point_ids_differ_but_deterministic():
    from app.domain.voice import me_point_id

    a = me_point_id(OWNER)
    b = me_point_id(OWNER)
    c = nick_point_id(OWNER, NICK_1)
    assert a == b  # deterministic
    assert a != c  # me != nick


def test_assign_empty_name_rejected():
    # An empty/whitespace-only name does not pass the schema — rejected before the service (422).
    import pydantic

    from app.presentation.schemas import NickAssignment

    with pytest.raises(pydantic.ValidationError):
        NickAssignment(name="   ")  # whitespace only
    with pytest.raises(pydantic.ValidationError):
        NickAssignment(name="")  # empty string
