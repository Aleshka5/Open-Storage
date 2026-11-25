import hashlib

from fastapi import Depends, HTTPException, Request, status
from loguru import logger

from app.application.file_service import FileService
from app.application.keys_registry_service import KeysRegistryService
from app.application.private_service import PrivateService
from app.domain.entities.user import User
from app.domain.value_objects.error_codes import ErrorCode
from app.infrastructure.database.repositories.file_repo import FileRepository
from app.infrastructure.database.repositories.quota_repo import QuotaRepository
from app.infrastructure.session_store import SessionStore, get_session_store
from app.presentation.dependencies.auth import get_current_user, get_quota_repository
from app.presentation.dependencies.files import get_file_repository
from config import get_settings

VAULT_COOKIE_NAME = "__Secure-open_session"


def vault_session_key(cookie_value: str) -> str:
    """Hash the gateway session cookie before it is used as a Redis key."""
    return hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()


def _get_session_id(request: Request) -> str:
    token = request.cookies.get(VAULT_COOKIE_NAME)
    if not token:
        logger.warning("Private vault requested without session cookie")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": ErrorCode.UNAUTHORIZED,
                "message": "Authentication required",
            },
        )
    return vault_session_key(token)


def get_private_service(
    quota_repo: QuotaRepository = Depends(get_quota_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    session_store: SessionStore = Depends(get_session_store),
) -> PrivateService:
    return PrivateService(
        session_store=session_store,
        quota_repo=quota_repo,
        file_repo=file_repo,
        settings=get_settings(),
    )


async def get_private_file_service(
    request: Request,
    current_user: User = Depends(get_current_user),
    private_service: PrivateService = Depends(get_private_service),
) -> FileService:
    session_id = _get_session_id(request)
    return await private_service.get_file_service(
        current_user.id,
        session_id,
        storage_id=current_user.storage_id,
    )


def get_keys_registry_service(
    file_service: FileService = Depends(get_private_file_service),
) -> KeysRegistryService:
    return KeysRegistryService(file_service)
