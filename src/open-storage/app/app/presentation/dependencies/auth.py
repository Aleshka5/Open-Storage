from fastapi import Depends, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.auth_principal import AuthPrincipal
from app.domain.entities.user import User
from app.domain.exceptions import AuthBlockedError, AuthUnauthenticatedError
from app.domain.value_objects.role import Role, role_from_auth_roles
from app.infrastructure.database.repositories.quota_repo import QuotaRepository
from app.infrastructure.database.repositories.user_repo import UserRepository
from app.infrastructure.database.session import get_async_session

HEADER_AUTH_SUBJECT = "X-Auth-Subject"
HEADER_AUTH_EMAIL = "X-Auth-Email"
HEADER_AUTH_NAME = "X-Auth-Name"
HEADER_AUTH_ROLES = "X-Auth-Roles"
HEADER_AUTH_SESSION = "X-Auth-Session"


def get_user_repository(
    session: AsyncSession = Depends(get_async_session),
) -> UserRepository:
    return UserRepository(session)


def get_quota_repository(
    session: AsyncSession = Depends(get_async_session),
) -> QuotaRepository:
    return QuotaRepository(session)


def _require_subject(request: Request) -> str:
    raw = request.headers.get(HEADER_AUTH_SUBJECT)
    if raw is None or raw.strip() == "":
        logger.warning("Authentication required: missing X-Auth-Subject")
        raise AuthUnauthenticatedError("Authentication required")
    return raw.strip()


def _user_from_principal(principal: AuthPrincipal, local: User) -> User:
    return User(
        id=local.id,
        email=principal.email or local.email,
        role=principal.role,
        is_active=local.is_active,
        created_at=local.created_at,
    )


async def get_current_user(
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    subject = _require_subject(request)
    role = role_from_auth_roles(request.headers.get(HEADER_AUTH_ROLES))
    if role is Role.BLOCKED:
        logger.warning("Storage role BLOCKED for subject present")
        raise AuthBlockedError("Access denied")

    email = (request.headers.get(HEADER_AUTH_EMAIL) or "").strip()
    name = (request.headers.get(HEADER_AUTH_NAME) or "").strip()
    session_id = (request.headers.get(HEADER_AUTH_SESSION) or "").strip()
    principal = AuthPrincipal(
        id=subject,
        email=email,
        name=name,
        role=role,
        session_id=session_id,
    )
    local_user = await user_repo.upsert_from_principal(principal)
    if local_user is None:
        logger.error("Cannot project identity subject into local users")
        raise RuntimeError("Cannot project identity subject into local users")

    await session.commit()
    user = _user_from_principal(principal, local_user)
    logger.info("Resolved current user user_id={} role={}", user.id, user.role.value)
    return user
