"""FileService must keep one record per storage key.

A second ``COMMITTED`` row for one key is what made a file impossible to delete:
the singular path lookup raised ``MultipleResultsFound`` (HTTP 500). These tests
pin the two halves of the fix — upload updates the existing row, delete sweeps
any duplicates left by older builds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.application.file_service import FileService
from app.domain.entities.file_record import FileRecord, FileSection, FileStatus
from tests.test_encrypted_storage_adapter import InMemoryStorageAdapter

OWNER_ID = UUID("33333333-3333-3333-3333-333333333333")
ROOT_PREFIX = f"users/{OWNER_ID}/files"


class FilesInMemoryAdapter(InMemoryStorageAdapter):
    def __init__(self) -> None:
        super().__init__(root_prefix=ROOT_PREFIX)
        self._dirs.add(".tmp")

    def stored_keys(self) -> list[str]:
        return sorted(self._files)


class RecordingFileRepo:
    """Minimal FileRepository stand-in with the duplicate-aware surface."""

    def __init__(self) -> None:
        self.records: list[FileRecord] = []

    def live_for_path(self, relative_path: str) -> list[FileRecord]:
        return [
            record
            for record in self.records
            if record.relative_path == relative_path
            and record.status == FileStatus.COMMITTED
        ]

    def _replace(self, updated: FileRecord) -> FileRecord:
        self.records = [updated if item.id == updated.id else item for item in self.records]
        return updated

    def _patch(self, record: FileRecord, **changes: object) -> FileRecord:
        return self._replace(FileRecord(**{**record.__dict__, **changes}))

    async def create(self, **kwargs: object) -> FileRecord:
        now = datetime.now(UTC)
        record = FileRecord(
            id=uuid4(),
            user_id=kwargs["user_id"],
            disk_id=kwargs["disk_id"],
            relative_path=kwargs["relative_path"],
            original_name=kwargs["original_name"],
            size_bytes=kwargs["size_bytes"],
            mime_type=kwargs["mime_type"],
            is_encrypted=kwargs["is_encrypted"],
            section=kwargs["section"],
            status=kwargs.get("status", FileStatus.PENDING),
            checksum_sha256=None,
            created_at=now,
            last_accessed_at=now,
        )
        self.records.append(record)
        return record

    async def get_by_id(self, file_id: UUID) -> FileRecord | None:
        return next((item for item in self.records if item.id == file_id), None)

    async def update_status(
        self,
        file_id: UUID,
        status: FileStatus,
        *,
        checksum_sha256: str | None = None,
        relative_path: str | None = None,
        original_name: str | None = None,
    ) -> FileRecord | None:
        record = await self.get_by_id(file_id)
        if record is None:
            return None
        return self._patch(
            record,
            status=status,
            checksum_sha256=checksum_sha256 or record.checksum_sha256,
            relative_path=relative_path or record.relative_path,
            original_name=original_name or record.original_name,
        )

    async def update_size(
        self,
        file_id: UUID,
        size_bytes: int,
        *,
        checksum_sha256: str | None = None,
    ) -> FileRecord | None:
        record = await self.get_by_id(file_id)
        if record is None:
            return None
        return self._patch(
            record,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256 or record.checksum_sha256,
        )

    async def clear_archive(self, file_id: UUID) -> FileRecord | None:
        record = await self.get_by_id(file_id)
        if record is None:
            return None
        return self._patch(
            record,
            status=FileStatus.COMMITTED,
        )

    async def delete(self, file_id: UUID) -> FileRecord | None:
        record = await self.get_by_id(file_id)
        if record is None:
            return None
        return self._patch(record, status=FileStatus.DELETED)

    async def get_downloadable_by_relative_path(
        self,
        user_id: UUID,
        relative_path: str,
        section: FileSection,
    ) -> FileRecord | None:
        # Oldest first, exactly like the SQL: duplicates must not raise.
        matches = [
            record
            for record in self.live_for_path(relative_path)
            if record.user_id == user_id and record.section == section
        ]
        return sorted(matches, key=lambda item: item.created_at)[0] if matches else None

    async def get_downloadable_by_relative_path_in_section(
        self,
        relative_path: str,
        section: FileSection,
    ) -> FileRecord | None:
        matches = [
            record
            for record in self.live_for_path(relative_path)
            if record.section == section
        ]
        return sorted(matches, key=lambda item: item.created_at)[0] if matches else None

    async def list_live_by_relative_path(
        self,
        relative_path: str,
        section: FileSection,
        *,
        user_id: UUID | None = None,
    ) -> list[FileRecord]:
        return [
            record
            for record in self.live_for_path(relative_path)
            if record.section == section
            and (user_id is None or record.user_id == user_id)
        ]

    async def heal_stale_relative_path(self, *args: object, **kwargs: object) -> None:
        return None

    async def heal_stale_relative_path_in_section(self, *args: object, **kwargs: object) -> None:
        return None

    async def touch_last_accessed(self, file_id: UUID) -> None:
        return None

    async def list_archived_direct_children(self, *args: object, **kwargs: object) -> list[FileRecord]:
        return []


class RecordingQuotaRepo:
    def __init__(self) -> None:
        self.total_bytes = 0
        self.limit_bytes = 1024 * 1024 * 1024
        self.decrements: list[int] = []

    async def get_by_user_id(self, user_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(
            user_id=user_id,
            total_bytes=self.total_bytes,
            limit_bytes=self.limit_bytes,
            private_bytes=0,
            private_limit_bytes=0,
        )

    async def increment(self, user_id: UUID, size_bytes: int, section: FileSection) -> SimpleNamespace:
        del section
        self.total_bytes += size_bytes
        return await self.get_by_user_id(user_id)

    async def decrement(self, user_id: UUID, size_bytes: int, section: FileSection) -> SimpleNamespace:
        del section
        self.decrements.append(size_bytes)
        self.total_bytes = max(0, self.total_bytes - size_bytes)
        return await self.get_by_user_id(user_id)


async def _chunks(payload: bytes):
    yield payload


def _service() -> tuple[FileService, RecordingFileRepo, RecordingQuotaRepo, FilesInMemoryAdapter]:
    storage = FilesInMemoryAdapter()
    repo = RecordingFileRepo()
    quota = RecordingQuotaRepo()
    service = FileService(storage, quota, repo, section=FileSection.FILES)
    return service, repo, quota, storage


async def _upload(service: FileService, filename: str, payload: bytes) -> FileRecord:
    return await service.upload_file(
        OWNER_ID,
        "",
        filename,
        _chunks(payload),
        len(payload),
        FileSection.FILES,
    )


async def _seed_duplicate(repo: RecordingFileRepo, filename: str, payload: bytes) -> tuple[FileRecord, FileRecord]:
    relative_path = f"{ROOT_PREFIX}/{filename}"
    first = await repo.create(
        user_id=OWNER_ID,
        disk_id="disk1",
        relative_path=relative_path,
        original_name=filename,
        size_bytes=len(payload),
        mime_type="application/pdf",
        is_encrypted=False,
        section=FileSection.FILES,
        status=FileStatus.COMMITTED,
    )
    second = await repo.create(
        user_id=OWNER_ID,
        disk_id="disk1",
        relative_path=relative_path,
        original_name=filename,
        size_bytes=len(payload),
        mime_type="application/pdf",
        is_encrypted=False,
        section=FileSection.FILES,
        status=FileStatus.COMMITTED,
    )
    return first, second


async def test_upload_of_an_existing_name_updates_the_same_record() -> None:
    service, repo, quota, storage = _service()

    first = await _upload(service, "scan.pdf", b"first" * 100)
    second = await _upload(service, "scan.pdf", b"second" * 300)

    assert second.id == first.id, "the second upload must reuse the record"
    live = repo.live_for_path(f"{ROOT_PREFIX}/scan.pdf")
    assert len(live) == 1, "one storage key must own exactly one record"
    assert live[0].size_bytes == 1800
    assert quota.total_bytes == 1800, "quota is charged as the size delta, not twice"
    assert storage.stored_keys() == ["scan.pdf"]


async def test_delete_removes_the_duplicate_rows_of_one_path(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, quota, storage = _service()
    payload = b"%PDF-1.4 duplicate" * 10
    await storage.write("Загран.pdf", _chunks(payload), len(payload))
    first, second = await _seed_duplicate(repo, "Загран.pdf", payload)
    quota.total_bytes = len(payload) * 2

    await service.delete_by_path(OWNER_ID, "/Загран.pdf")

    assert first.id != second.id
    assert repo.live_for_path(f"{ROOT_PREFIX}/Загран.pdf") == []
    assert all(
        record.status == FileStatus.DELETED
        for record in repo.records
        if record.relative_path == f"{ROOT_PREFIX}/Загран.pdf"
    )
    assert storage.stored_keys() == []
    assert quota.total_bytes == 0, "both duplicate charges must be released"


