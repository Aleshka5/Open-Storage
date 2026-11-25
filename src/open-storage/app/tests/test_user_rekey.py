"""Email-match cutover re-keys a legacy user onto the identity subject."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.test_file_index_link_repo  # noqa: F401  sqlite UUID + aiosqlite
from app.domain.entities.auth_principal import AuthPrincipal
from app.domain.exceptions import IdentityProjectionError
from app.domain.value_objects.role import Role
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import FileIndexLink
from app.infrastructure.database.models import FileRecord as FileRecordModel
from app.infrastructure.database.models import FileSection
from app.infrastructure.database.models import FileStatus
from app.infrastructure.database.models import UploadSession
from app.infrastructure.database.models import User as UserModel
from app.infrastructure.database.models import UserQuotaUsage
from app.infrastructure.database.repositories.user_repo import UserRepository

LEGACY_ID = UUID("eb482017-4fbf-474c-84d0-7a390448eec8")
SUBJECT_ID = UUID("70b9ef7b-dee8-4427-81d8-d6fd9abe42e1")
OTHER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EMAIL = "owner@example.test"
CREATED = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        await db_session.execute(text("PRAGMA foreign_keys=ON"))
        yield db_session
    await engine.dispose()


def _principal(subject: UUID, email: str) -> AuthPrincipal:
    return AuthPrincipal(
        id=str(subject),
        email=email,
        name="Owner",
        role=Role.FAMILY,
        session_id="sid-one",
    )


async def _seed_owner(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
    is_active: bool = True,
) -> UUID:
    file_id = uuid4()
    relative = f"users/{user_id}/files/a.txt"
    session.add(
        UserModel(
            id=user_id,
            email=email,
            is_active=is_active,
            object_prefix_id=user_id,
            created_at=CREATED,
        )
    )
    session.add(
        FileRecordModel(
            id=file_id,
            user_id=user_id,
            disk_id="primary",
            relative_path=relative,
            original_name="a.txt",
            size_bytes=12,
            mime_type="text/plain",
            is_encrypted=False,
            section=FileSection.FILES,
            status=FileStatus.COMMITTED,
            created_at=CREATED,
            last_accessed_at=CREATED,
        )
    )
    session.add(
        UserQuotaUsage(
            user_id=user_id,
            total_bytes=12,
            limit_bytes=100,
            private_bytes=0,
            private_limit_bytes=0,
            photos_bytes=0,
        )
    )
    session.add(
        UploadSession(
            id=uuid4(),
            user_id=user_id,
            target_path="docs/a.txt",
            total_size=12,
            received_bytes=0,
            is_encrypted=False,
            expires_at=datetime(2026, 12, 1, tzinfo=UTC),
            created_at=CREATED,
        )
    )
    session.add(
        FileIndexLink(
            id=uuid4(),
            file_record_id=None,
            user_id=user_id,
            section=FileSection.FILES,
            s3_key=relative,
            content_type="text/plain",
            state="pending",
            attempts=0,
            created_at=CREATED,
            updated_at=CREATED,
        )
    )
    await session.commit()
    return file_id


async def _user_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(UserModel))
    return int(result.scalar_one())


async def test_email_match_rekeys_user_and_keeps_file_ownership(session: AsyncSession) -> None:
    file_id = await _seed_owner(session, user_id=LEGACY_ID, email=EMAIL)
    relative = f"users/{LEGACY_ID}/files/a.txt"
    repo = UserRepository(session)

    projected = await repo.upsert_from_principal(_principal(SUBJECT_ID, EMAIL))
    await session.commit()

    assert projected is not None
    assert projected.id == SUBJECT_ID
    assert projected.storage_id == LEGACY_ID
    assert await _user_count(session) == 1

    owner = await session.get(UserModel, SUBJECT_ID)
    assert owner is not None
    assert owner.object_prefix_id == LEGACY_ID
    assert owner.email == EMAIL
    assert await session.get(UserModel, LEGACY_ID) is None

    record = await session.get(FileRecordModel, file_id)
    assert record is not None
    assert record.user_id == SUBJECT_ID
    assert record.relative_path == relative

    quota = await session.get(UserQuotaUsage, SUBJECT_ID)
    assert quota is not None
    assert quota.total_bytes == 12
    assert await session.get(UserQuotaUsage, LEGACY_ID) is None

    uploads = (
        await session.execute(select(UploadSession).where(UploadSession.user_id == SUBJECT_ID))
    ).scalars().all()
    assert len(uploads) == 1
    links = (
        await session.execute(select(FileIndexLink).where(FileIndexLink.user_id == SUBJECT_ID))
    ).scalars().all()
    assert len(links) == 1
    assert links[0].s3_key == relative

    again = await repo.upsert_from_principal(_principal(SUBJECT_ID, EMAIL))
    await session.commit()
    assert again is not None
    assert again.id == SUBJECT_ID
    assert again.storage_id == LEGACY_ID
    assert await _user_count(session) == 1
    record_again = await session.get(FileRecordModel, file_id)
    assert record_again is not None
    assert record_again.user_id == SUBJECT_ID


async def test_existing_subject_syncs_without_a_new_row(session: AsyncSession) -> None:
    file_id = await _seed_owner(
        session,
        user_id=SUBJECT_ID,
        email=EMAIL,
        is_active=False,
    )
    repo = UserRepository(session)

    projected = await repo.upsert_from_principal(_principal(SUBJECT_ID, EMAIL))
    await session.commit()

    assert projected is not None
    assert projected.id == SUBJECT_ID
    assert projected.is_active is True
    assert projected.storage_id == SUBJECT_ID
    assert await _user_count(session) == 1
    record = await session.get(FileRecordModel, file_id)
    assert record is not None
    assert record.user_id == SUBJECT_ID


async def test_ambiguous_email_does_not_rekey(session: AsyncSession) -> None:
    file_id = await _seed_owner(session, user_id=LEGACY_ID, email="Owner@example.test")
    session.add(
        UserModel(
            id=OTHER_ID,
            email="owner@example.test",
            is_active=True,
            object_prefix_id=OTHER_ID,
            created_at=CREATED,
        )
    )
    await session.commit()
    repo = UserRepository(session)

    with pytest.raises(IdentityProjectionError):
        await repo.upsert_from_principal(_principal(SUBJECT_ID, "owner@example.test"))

    assert await _user_count(session) == 2
    assert await session.get(UserModel, SUBJECT_ID) is None
    legacy = await session.get(UserModel, LEGACY_ID)
    other = await session.get(UserModel, OTHER_ID)
    assert legacy is not None and legacy.email == "Owner@example.test"
    assert other is not None and other.email == "owner@example.test"
    record = await session.get(FileRecordModel, file_id)
    assert record is not None
    assert record.user_id == LEGACY_ID


async def test_subject_owned_by_someone_else_does_not_rekey(session: AsyncSession) -> None:
    file_id = await _seed_owner(session, user_id=LEGACY_ID, email=EMAIL)
    session.add(
        UserModel(
            id=SUBJECT_ID,
            email="other@example.test",
            is_active=True,
            object_prefix_id=SUBJECT_ID,
            created_at=CREATED,
        )
    )
    await session.commit()
    repo = UserRepository(session)

    with pytest.raises(IdentityProjectionError):
        await repo.upsert_from_principal(_principal(SUBJECT_ID, EMAIL))

    assert await _user_count(session) == 2
    subject = await session.get(UserModel, SUBJECT_ID)
    legacy = await session.get(UserModel, LEGACY_ID)
    assert subject is not None and subject.email == "other@example.test"
    assert legacy is not None and legacy.email == EMAIL
    record = await session.get(FileRecordModel, file_id)
    assert record is not None
    assert record.user_id == LEGACY_ID
