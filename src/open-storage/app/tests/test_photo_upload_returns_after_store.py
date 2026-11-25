"""The photo upload 201 does not wait for the index notify.

A notify that blocks must leave the response at 201, and the handler must
still hand it the file id captured while the original was stored.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from app.application.indexing.immediate import note_immediate_index_ids
from app.domain.entities.file_record import FileRecord, FileSection, FileStatus
from app.domain.entities.user import User
from app.domain.value_objects.role import Role
from app.infrastructure.database.session import get_async_session
from app.presentation.dependencies.auth import get_current_user, get_quota_repository
from app.presentation.dependencies.photos import get_photo_service
from app.presentation.routers import photo_router
from app.presentation.routers.photo_router import router as photos_router

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PHOTO_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
NOW = datetime(2026, 10, 26, tzinfo=UTC)
_RESPONSE_TIMEOUT_SECONDS = 1.0


def _user() -> User:
    return User(
        id=USER_ID,
        email="family@example.test",
        role=Role.FAMILY,
        is_active=True,
        created_at=NOW,
    )


def _record() -> FileRecord:
    return FileRecord(
        id=PHOTO_ID,
        user_id=USER_ID,
        disk_id="storage",
        relative_path=f"users/{USER_ID}/photos/originals/{PHOTO_ID}.jpg",
        original_name="sunset.jpg",
        size_bytes=4,
        mime_type="image/jpeg",
        is_encrypted=False,
        section=FileSection.PHOTOS,
        status=FileStatus.COMMITTED,
        checksum_sha256="abc",
        created_at=NOW,
        last_accessed_at=NOW,
    )


class _Session:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def commit(self) -> None:
        self.events.append("commit")

    async def rollback(self) -> None:
        self.events.append("rollback")


class _Quota:
    async def get_by_user_id(self, user_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(
            user_id=user_id,
            total_bytes=0,
            limit_bytes=100 * 1024 * 1024,
        )


class _Photos:
    def __init__(self, record: FileRecord, events: list[str]) -> None:
        self._record = record
        self._events = events

    async def upload_photo(
        self,
        user_id: UUID,
        filename: str,
        data: AsyncIterator[bytes],
        size: int,
    ) -> FileRecord:
        del user_id, filename, size
        async for _chunk in data:
            pass
        self._events.append("store")
        note_immediate_index_ids((self._record.id,))
        return self._record


def _app(session: _Session, photos: _Photos) -> FastAPI:
    app = FastAPI()
    app.include_router(photos_router)

    async def _session():
        yield session

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_photo_service] = lambda: photos
    app.dependency_overrides[get_quota_repository] = lambda: _Quota()
    app.dependency_overrides[get_async_session] = _session
    return app


async def test_blocking_index_notify_does_not_delay_photo_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    record = _record()
    photos = _Photos(record, session.events)
    release = asyncio.Event()
    started = asyncio.Event()
    finished = asyncio.Event()
    seen: list[list[UUID]] = []

    async def slow_notify(file_record_ids: list[UUID]) -> None:
        seen.append(list(file_record_ids))
        session.events.append("notify-start")
        started.set()
        try:
            await release.wait()
        finally:
            session.events.append("notify-end")
            finished.set()

    monkeypatch.setattr(
        photo_router,
        "deliver_immediate_index_notifications",
        slow_notify,
    )

    transport = httpx.ASGITransport(app=_app(session, photos))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        post = asyncio.create_task(
            client.post(
                "/api/photos/upload",
                files={"file": ("sunset.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            )
        )
        try:
            done, _pending = await asyncio.wait({post}, timeout=_RESPONSE_TIMEOUT_SECONDS)
            assert post in done, "POST /api/photos/upload waited on the index notify"
            response = post.result()
            assert response.status_code == 201
            assert response.json()["id"] == str(PHOTO_ID)
            assert session.events[:2] == ["store", "commit"]
            assert "notify-end" not in session.events
            assert "rollback" not in session.events

            await asyncio.wait_for(started.wait(), timeout=_RESPONSE_TIMEOUT_SECONDS)
            assert session.events[:3] == ["store", "commit", "notify-start"]
            assert seen == [[PHOTO_ID]]
            assert photo_router._photo_upload_notify_tasks
        finally:
            release.set()
            if not post.done():
                post.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await post
            if started.is_set():
                await asyncio.wait_for(finished.wait(), timeout=_RESPONSE_TIMEOUT_SECONDS)
