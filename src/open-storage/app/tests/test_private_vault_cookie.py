"""Vault Redis keys are the hash of __Secure-open_session, not auth_session."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from loguru import logger

from app.domain.entities.user import User
from app.domain.exceptions import PrivateSessionExpiredError
from app.domain.value_objects.error_codes import ErrorCode
from app.domain.value_objects.role import Role
from app.infrastructure.session_store import SessionStore
from app.presentation.dependencies.auth import get_current_user
from app.presentation.dependencies.private import (
    VAULT_COOKIE_NAME,
    _get_session_id,
    vault_session_key,
)
from app.presentation.exception_handlers import register_exception_handlers
from app.presentation.routers.private_router import router as private_router
from config import get_settings

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
COOKIE_A = "session-cookie-alpha"
COOKIE_B = "session-cookie-beta"


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _family_user() -> User:
    return User(
        id=USER_ID,
        email="family@example.test",
        role=Role.FAMILY,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _request_with_cookie(value: str | None) -> MagicMock:
    request = MagicMock()
    request.cookies = {} if value is None else {VAULT_COOKIE_NAME: value}
    return request


def test_session_key_is_hash_of_secure_cookie_not_the_raw_value() -> None:
    request = _request_with_cookie(COOKIE_A)
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        session_id = _get_session_id(request)
    finally:
        logger.remove(sink)

    expected = hashlib.sha256(COOKIE_A.encode("utf-8")).hexdigest()
    assert session_id == expected
    assert session_id == vault_session_key(COOKIE_A)
    assert COOKIE_A not in session_id
    assert all(COOKIE_A not in message for message in messages)


def test_get_session_id_missing_cookie_is_unauthorized() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _get_session_id(_request_with_cookie(None))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error_code"] == ErrorCode.UNAUTHORIZED


def test_auth_session_cookie_is_not_the_vault_key() -> None:
    request = MagicMock()
    request.cookies = {"auth_session": COOKIE_A}

    with pytest.raises(HTTPException) as exc_info:
        _get_session_id(request)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_two_logins_use_two_redis_keys_and_do_not_share_the_private_key() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def setex(self, key: str, _ttl: int, value: str) -> None:
            self.values[key] = value

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def delete(self, key: str) -> int:
            return 1 if self.values.pop(key, None) is not None else 0

        async def ttl(self, key: str) -> int:
            return 10 if key in self.values else -2

    fake = FakeRedis()
    store = SessionStore.__new__(SessionStore)
    store._redis = fake

    key_a = vault_session_key(COOKIE_A)
    key_b = vault_session_key(COOKIE_B)
    await store.set_private_key(key_a, "aes-key-a", 60)
    await store.set_private_key(key_b, "aes-key-b", 60)

    redis_keys = set(fake.values)
    assert redis_keys == {f"private_key:{key_a}", f"private_key:{key_b}"}
    assert all(COOKIE_A not in key and COOKIE_B not in key for key in redis_keys)
    assert await store.get_private_key(key_a) == "aes-key-a"
    assert await store.get_private_key(key_b) == "aes-key-b"
    assert key_a != key_b


@pytest.mark.asyncio
async def test_unlock_attempts_stay_keyed_on_user_and_ip() -> None:
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    store = SessionStore.__new__(SessionStore)
    store._redis = redis

    count = await store.increment_unlock_attempts(str(USER_ID), "10.1.2.3")

    assert count == 1
    redis.incr.assert_awaited_once_with(f"unlock_attempts:{USER_ID}:10.1.2.3")
    redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_private_file_service_expired_key_is_private_session_expired() -> None:
    from app.application.private_service import PrivateService

    store = MagicMock()
    store.get_private_key = AsyncMock(return_value=None)
    service = PrivateService(
        session_store=store,
        quota_repo=MagicMock(),
        file_repo=MagicMock(),
    )

    with pytest.raises(PrivateSessionExpiredError):
        await service.get_file_service(USER_ID, vault_session_key(COOKIE_A))


def test_private_session_without_cookie_is_unauthorized_not_expired() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(private_router)
    app.dependency_overrides[get_current_user] = _family_user

    client = TestClient(app)
    response = client.get(
        "/api/private/session",
        headers={
            "X-Auth-Subject": str(USER_ID),
            "X-Auth-Roles": "svc:storage:family",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == ErrorCode.UNAUTHORIZED
    assert "error" not in response.json()
