from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.auth_principal import AuthPrincipal
from app.domain.entities.user import User as UserEntity
from app.domain.exceptions import IdentityProjectionError
from app.domain.value_objects.role import Role
from app.infrastructure.database.models import FileIndexLink
from app.infrastructure.database.models import User as UserModel
from app.infrastructure.database.models import UserQuotaUsage
from config import get_settings


def stored_user_id(subject: str) -> UUID | None:
    """``users.id`` is a UUID column until the data cutover.

    The header reader does not parse the subject. This is the persistence
    boundary: a subject the column cannot store is not inserted.
    """
    try:
        return UUID(subject)
    except (ValueError, AttributeError):
        return None


@dataclass(frozen=True)
class UserAdminRow:
    user: UserEntity
    quota_used_bytes: int
    limit_bytes: int
    private_limit_bytes: int


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self._session.execute(select(UserModel).where(UserModel.email == email))
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def get_by_id(self, user_id: UUID) -> UserEntity | None:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            return None
        return self._to_entity(model)

    async def upsert_from_principal(self, principal: AuthPrincipal) -> UserEntity | None:
        """Project the request subject into the local users table.

        A subject that is not yet a ``users.id``, whose trusted email matches
        exactly one local user, re-keys that row (and every ``user_id`` that
        points at it) inside this transaction. Object keys stay on
        ``object_prefix_id``.

        Authorization must use ``principal.role``. Returns None when the
        subject cannot be stored in ``users.id``. Raises
        ``IdentityProjectionError`` when the email matches more than one row,
        or the subject already belongs to someone other than the email owner.
        """
        user_id = stored_user_id(principal.id)
        if user_id is None:
            logger.error("Identity subject cannot be stored in users.id")
            return None

        existing = await self._session.get(UserModel, user_id)
        matches = await self._users_for_email(principal.email)

        if existing is not None:
            others = [row.id for row in matches if row.id != existing.id]
            if others:
                logger.error(
                    "Identity subject user_id={} already exists and email is owned by {}",
                    user_id,
                    others,
                )
                raise IdentityProjectionError(
                    "Identity subject cannot be mapped onto a single local user"
                )
            return await self._sync_projection(principal)

        if len(matches) > 1:
            logger.error(
                "Identity subject user_id={} email matches {} local users: {}",
                user_id,
                len(matches),
                [row.id for row in matches],
            )
            raise IdentityProjectionError(
                "Identity subject cannot be mapped onto a single local user"
            )

        if len(matches) == 1:
            return await self._rekey_user(matches[0].id, user_id, principal)

        model = UserModel(
            id=user_id,
            email=principal.email,
            is_active=True,
            object_prefix_id=user_id,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(model)
                await self._session.flush()
        except IntegrityError:
            logger.error(
                "Identity subject user_id={} could not be inserted due to a unique constraint",
                user_id,
            )
            return None

        await self._session.refresh(model)
        logger.info("Created local user projection user_id={}", model.id)
        return self._to_entity(model, role=principal.role)

    async def _users_for_email(self, email: str) -> list[UserModel]:
        """Local rows whose email matches the trusted identity, case-insensitively.

        A blank email matches nobody. Two rows that differ only by case are
        ambiguous and must not be re-keyed.
        """
        normalized = email.strip().lower()
        if not normalized:
            return []
        result = await self._session.execute(
            select(UserModel).where(func.lower(UserModel.email) == normalized)
        )
        return list(result.scalars().all())

    async def _rekey_user(
        self,
        old_id: UUID,
        new_id: UUID,
        principal: AuthPrincipal,
    ) -> UserEntity:
        """Point ``users.id`` at the subject and follow every ``user_id`` column.

        ``ON UPDATE CASCADE`` moves ``file_records``, ``user_quota_usage`` and
        ``upload_sessions``. ``file_index_links.user_id`` has no foreign key,
        so it is updated here. ``object_prefix_id``, ``relative_path`` and
        ``s3_key`` stay on the pre-cutover id: those are object locations.
        """
        self._session.expunge_all()
        rekeyed = await self._session.execute(
            update(UserModel)
            .where(UserModel.id == old_id)
            .values(id=new_id)
            .returning(UserModel.id),
            execution_options={"synchronize_session": False},
        )
        if rekeyed.scalar_one_or_none() is None:
            logger.error(
                "Identity re-key matched no row old_user_id={} subject_id={}",
                old_id,
                new_id,
            )
            raise IdentityProjectionError(
                "Identity subject cannot be mapped onto a single local user"
            )

        await self._session.execute(
            update(FileIndexLink)
            .where(FileIndexLink.user_id == old_id)
            .values(user_id=new_id),
            execution_options={"synchronize_session": False},
        )
        self._session.expire_all()

        model = await self._session.get(UserModel, new_id)
        if model is None:
            logger.error("Identity re-key lost subject_id={}", new_id)
            raise IdentityProjectionError(
                "Identity subject cannot be mapped onto a single local user"
            )
        if principal.email and model.email != principal.email:
            model.email = principal.email
        if not model.is_active:
            model.is_active = True
        await self._session.flush()
        await self._session.refresh(model)
        logger.info(
            "Re-keyed local user old_user_id={} subject_id={} object_prefix_id={}",
            old_id,
            new_id,
            model.object_prefix_id,
        )
        return self._to_entity(model, role=principal.role)

    async def _sync_projection(self, principal: AuthPrincipal) -> UserEntity:
        user_id = stored_user_id(principal.id)
        if user_id is None:
            raise RuntimeError("Identity subject cannot be stored in users.id")
        model = await self._session.get(UserModel, user_id)
        if model is None:
            logger.error("User {} disappeared during identity projection sync", user_id)
            raise RuntimeError(f"User {user_id} not found during projection sync")

        if principal.email and model.email != principal.email:
            model.email = principal.email
        if not model.is_active:
            model.is_active = True
        await self._session.flush()
        await self._session.refresh(model)
        logger.info("Updated local user projection user_id={}", model.id)
        return self._to_entity(model, role=principal.role)

    async def set_active(self, user_id: UUID, is_active: bool) -> UserEntity | None:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            logger.warning("User {} not found for active status update", user_id)
            return None
        model.is_active = is_active
        await self._session.flush()
        await self._session.refresh(model)
        logger.info("Updated active status for user {} to {}", user_id, is_active)
        return self._to_entity(model)

    def _to_admin_row(self, user_model: UserModel, quota_model: UserQuotaUsage | None) -> UserAdminRow:
        default_limit = get_settings().business_logic.default_user_quota_bytes
        return UserAdminRow(
            user=self._to_entity(user_model),
            quota_used_bytes=quota_model.total_bytes if quota_model else 0,
            limit_bytes=quota_model.limit_bytes if quota_model else default_limit,
            private_limit_bytes=quota_model.private_limit_bytes if quota_model else 0,
        )

    async def get_admin_rows_by_ids(self, user_ids: list[UUID]) -> dict[UUID, UserAdminRow]:
        if not user_ids:
            return {}

        stmt = (
            select(UserModel, UserQuotaUsage)
            .outerjoin(UserQuotaUsage, UserQuotaUsage.user_id == UserModel.id)
            .where(UserModel.id.in_(user_ids))
        )
        result = await self._session.execute(stmt)
        rows: dict[UUID, UserAdminRow] = {}
        for user_model, quota_model in result.all():
            rows[user_model.id] = self._to_admin_row(user_model, quota_model)
        logger.info("Loaded {} local admin projections", len(rows))
        return rows

    async def list_admin_rows(self) -> list[UserAdminRow]:
        stmt = (
            select(UserModel, UserQuotaUsage)
            .outerjoin(UserQuotaUsage, UserQuotaUsage.user_id == UserModel.id)
            .order_by(UserModel.created_at, UserModel.id)
        )
        result = await self._session.execute(stmt)
        rows = [self._to_admin_row(user_model, quota_model) for user_model, quota_model in result.all()]
        logger.info("Listed {} local users for admin", len(rows))
        return rows

    async def delete(self, user_id: UUID) -> bool:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            logger.warning("User {} not found for deletion", user_id)
            return False

        await self._session.delete(model)
        await self._session.flush()
        logger.info("Deleted user {}", user_id)
        return True

    @staticmethod
    def _to_entity(model: UserModel, role: Role = Role.STRANGER) -> UserEntity:
        created_at = model.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return UserEntity(
            id=model.id,
            email=model.email,
            role=role,
            is_active=model.is_active,
            created_at=created_at,
            object_prefix_id=model.object_prefix_id,
        )
