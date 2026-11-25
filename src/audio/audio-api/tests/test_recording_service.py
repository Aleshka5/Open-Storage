"""Recording scenario tests: list/details/rename, a foreign id, statuses."""
from __future__ import annotations

import datetime

import pytest

from app.application.recording_service import RecordingService
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.recording import Recording
from app.domain.status import RecordingStatus
from tests.conftest import OTHER_OWNER, OWNER, RECORDING
from tests.fakes import FakeRecordingRepo


def _iso(hour: int = 9, minute: int = 0) -> str:
    return datetime.datetime(2026, 11, 1, hour, minute, tzinfo=datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


async def _seed(repo: FakeRecordingRepo, owner: str, rid: str, title: str = "Lecture") -> None:
    rec = Recording(
        recording_id=rid,
        owner_user_id=owner,
        title=title,
        status=RecordingStatus.UPLOADED,
        audio_key=f"u/{owner}/rec/{rid}/original.wav",
        audio_content_type="audio/wav",
        audio_bytes=1600,
        created_at=_iso(),
        updated_at=_iso(),
    )
    rec.processing = rec.default_processing()
    await repo.insert_recording(rec)


@pytest.fixture
def svc(container):
    return RecordingService(container.repo, container.store, container.queue, container.settings)


async def test_get_recording_returns_speakers_empty(svc, repo):
    await _seed(repo, OWNER, RECORDING)
    result = await svc.get(OWNER, RECORDING)
    assert result["recording"]["id"] == RECORDING
    assert result["speakers"] == []


async def test_get_foreign_recording_returns_404(svc, repo):
    await _seed(repo, OWNER, RECORDING)
    with pytest.raises(AppError) as exc:
        await svc.get(OTHER_OWNER, RECORDING)
    assert exc.value.code == ErrorCode.NOT_FOUND


async def test_patch_title_returns_updated(svc, repo):
    await _seed(repo, OWNER, RECORDING)
    result = await svc.rename(OWNER, RECORDING, "Operating systems seminar")
    assert result["title"] == "Operating systems seminar"


async def test_list_sorts_newest_first_with_cursor(svc, repo):
    for i in range(3):
        rid = f"00000000-0000-0000-0000-{i:012d}"
        rec = Recording(
            recording_id=rid,
            owner_user_id=OWNER,
            title=f"rec{i}",
            status=RecordingStatus.UPLOADED,
            created_at=_iso(hour=9, minute=i),
            updated_at=_iso(hour=9, minute=i),
        )
        rec.processing = rec.default_processing()
        await repo.insert_recording(rec)

    result = await svc.list(OWNER, limit=2, cursor=None)
    assert len(result["items"]) == 2
    assert result["next_cursor"] is not None


async def test_list_hides_other_owner(svc, repo):
    await _seed(repo, OWNER, RECORDING, "mine")
    await _seed(repo, OTHER_OWNER, "aaaaaaaa-0000-0000-0000-000000000000", "not mine")
    result = await svc.list(OWNER, limit=10, cursor=None)
    titles = [i["title"] for i in result["items"]]
    assert "mine" in titles
    assert "not mine" not in titles


async def test_phrases_empty_contract_ready(svc, repo):
    from app.application.recording_service import PhraseService

    ps = PhraseService(repo, svc._settings)
    await _seed(repo, OWNER, RECORDING)
    result = await ps.list_phrases(OWNER, RECORDING, after_seq=0, limit=200)
    assert result["items"] == []
    assert result["recording"]["status"] == "uploaded"
    assert "processing" in result["recording"]
    assert result["next_after_seq"] == 0


async def test_phrases_foreign_returns_404(svc, repo):
    from app.application.recording_service import PhraseService

    ps = PhraseService(repo, svc._settings)
    await _seed(repo, OWNER, RECORDING)
    with pytest.raises(AppError) as exc:
        await ps.list_phrases(OTHER_OWNER, RECORDING, after_seq=0, limit=200)
    assert exc.value.code == ErrorCode.NOT_FOUND
