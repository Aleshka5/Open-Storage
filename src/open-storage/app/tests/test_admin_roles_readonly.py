"""Admin routes stay behind the app ADMIN gate. The user list is local."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.admin_service import AdminService
from app.domain.entities.user import User
from app.domain.exceptions import UserNotFoundError
from app.domain.value_objects.error_codes import ErrorCode
from app.domain.value_objects.role import Role
from app.infrastructure.database.repositories.user_repo import UserAdminRow
from app.infrastructure.database.session import get_async_session
from app.presentation.dependencies.admin import get_admin_service
from app.presentation.dependencies.auth import get_user_repository
from app.presentation.dependencies.indexing import get_index_link_repository, get_rag_index
from app.presentation.exception_handlers import register_exception_handlers
from app.presentation.routers.admin_router import router as admin_router
from app.presentation.routers.indexing_router import router as indexing_router
from config import get_settings

ADMIN_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FAMILY_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

ADMIN_ROUTES = (
    ("GET", "/api/admin/users", None),
    ("PATCH", f"/api/admin/users/{USER_B_ID}/role", None),
    ("PATCH", f"/api/admin/users/{USER_B_ID}/quota", {"limit_mb": 1}),
    ("POST", f"/api/admin/users/{USER_B_ID}/block", None),
    ("DELETE", f"/api/admin/users/{USER_B_ID}", None),
    ("GET", "/api/admin/storage", None),
    ("GET", "/api/admin/storage/health", None),
    ("GET", "/api/admin/maintenance/run", None),
    ("GET", "/api/admin/maintenance/stats", None),
    ("GET", "/api/admin/backup/run", None),
    ("GET", "/api/admin/backup/list", None),
    ("GET", "/api/admin/indexing", None),
    ("POST", "/api/admin/indexing/backfill", {}),
    ("POST", "/api/admin/indexing/retry", {}),
)


def _user(user_id: UUID, email: str, role: Role = Role.STRANGER) -> User:
    return User(
        id=user_id,
        email=email,
        role=role,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeUserRepository:
    def __init__(self) -> None:
        self.rows: list[UserAdminRow] = []
        self.users: dict[UUID, User] = {}

    async def upsert_from_principal(self, principal) -> User:
        user_id = UUID(principal.id)
        user = _user(user_id, principal.email or "caller@example.test", principal.role)
        self.users[user_id] = user
        return user

    async def list_admin_rows(self) -> list[UserAdminRow]:
        return list(self.rows)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)


def _headers(roles: str, user_id: UUID = ADMIN_USER_ID) -> dict[str, str]:
    return {
        "X-Auth-Subject": str(user_id),
        "X-Auth-Email": "caller@example.test",
        "X-Auth-Name": "Caller",
        "X-Auth-Roles": roles,
        "X-Auth-Session": "sid-admin",
    }


def _build_app(user_repo: FakeUserRepository | None = None, quota_repo: AsyncMock | None = None) -> FastAPI:
    repo = user_repo or FakeUserRepository()
    quotas = quota_repo or AsyncMock()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(admin_router)
    app.include_router(indexing_router)
    app.dependency_overrides[get_user_repository] = lambda: repo

    async def fake_session():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_async_session] = fake_session
    app.dependency_overrides[get_admin_service] = lambda: AdminService(
        user_repo=repo,
        quota_repo=quotas,
        file_repo=MagicMock(),
        disk_router=MagicMock(),
        settings=get_settings(),
    )
    app.dependency_overrides[get_index_link_repository] = lambda: MagicMock()
    app.dependency_overrides[get_rag_index] = lambda: MagicMock()
    return app


def _error_code(response) -> str:
    return response.json()["detail"]["error_code"]


def test_admin_list_users_empty() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/admin/users", headers=_headers("svc:storage:admin"))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_admin_list_users_reads_local_rows_and_quota() -> None:
    user_repo = FakeUserRepository()
    user_repo.rows = [
        UserAdminRow(
            user=_user(ADMIN_USER_ID, "admin@example.test", Role.STRANGER),
            quota_used_bytes=0,
            limit_bytes=100 * 1024 * 1024,
            private_limit_bytes=0,
        ),
        UserAdminRow(
            user=_user(USER_B_ID, "user-b@example.test", Role.STRANGER),
            quota_used_bytes=1024,
            limit_bytes=50 * 1024 * 1024,
            private_limit_bytes=2048,
        ),
    ]
    client = TestClient(_build_app(user_repo))

    response = client.get("/api/admin/users", headers=_headers("svc:storage:admin"))

    assert response.status_code == 200
    body = response.json()
    by_id = {item["id"]: item for item in body["items"]}
    assert body["total"] == 2
    assert by_id[str(USER_B_ID)]["email"] == "user-b@example.test"
    assert by_id[str(USER_B_ID)]["role"] == Role.STRANGER.value
    assert by_id[str(USER_B_ID)]["quota_used_bytes"] == 1024
    assert by_id[str(USER_B_ID)]["limit_bytes"] == 50 * 1024 * 1024
    assert by_id[str(ADMIN_USER_ID)]["limit_bytes"] == 100 * 1024 * 1024


def test_admin_list_users_returns_negative_cached_usage() -> None:
    user_repo = FakeUserRepository()
    user_repo.rows = [
        UserAdminRow(
            user=_user(USER_B_ID, "user-b@example.test"),
            quota_used_bytes=-283_713_391,
            limit_bytes=50 * 1024 * 1024,
            private_limit_bytes=0,
        )
    ]
    client = TestClient(_build_app(user_repo))

    response = client.get("/api/admin/users", headers=_headers("svc:storage:admin"))

    assert response.status_code == 200
    assert response.json()["items"][0]["quota_used_bytes"] == -283_713_391


def test_patch_user_role_is_gone() -> None:
    client = TestClient(_build_app())

    response = client.patch(
        f"/api/admin/users/{USER_B_ID}/role",
        json={"role": "STRANGER"},
        headers=_headers("svc:storage:admin"),
    )

    assert response.status_code == 410
    assert _error_code(response) == ErrorCode.ACCESS_DENIED
    assert response.json()["detail"]["message"] == "Storage roles are managed in the identity provider"


@pytest.mark.parametrize(("method", "path", "json_body"), ADMIN_ROUTES)
def test_family_gets_app_403_on_admin_routes(method: str, path: str, json_body: dict | None) -> None:
    client = TestClient(_build_app())

    response = client.request(
        method,
        path,
        headers=_headers("svc:storage:family", FAMILY_USER_ID),
        json=json_body,
    )

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"detail"}
    assert body["detail"]["error_code"] == ErrorCode.ACCESS_DENIED
    assert "message" in body["detail"]
    assert "error" not in body


def test_storage_admin_without_realm_admin_lists_users() -> None:
    client = TestClient(_build_app())

    without_realm = client.get("/api/admin/users", headers=_headers("svc:storage:admin"))
    with_realm = client.get("/api/admin/users", headers=_headers("admin svc:storage:admin"))

    assert without_realm.status_code == 200
    assert with_realm.status_code == 200


def test_patch_quota_requires_a_local_user() -> None:
    user_repo = FakeUserRepository()
    user_repo.users[USER_B_ID] = _user(USER_B_ID, "user-b@example.test")
    quota_repo = AsyncMock()
    client = TestClient(_build_app(user_repo, quota_repo=quota_repo))

    response = client.patch(
        f"/api/admin/users/{USER_B_ID}/quota",
        json={"private_limit_gb": 10.0},
        headers=_headers("svc:storage:admin"),
    )

    assert response.status_code == 204
    quota_repo.update_private_limit.assert_awaited_once_with(USER_B_ID, 10 * 1024 * 1024 * 1024)
    quota_repo.update_limit.assert_not_called()


def test_patch_quota_unknown_local_user_is_not_found() -> None:
    quota_repo = AsyncMock()
    client = TestClient(_build_app(FakeUserRepository(), quota_repo=quota_repo))

    response = client.patch(
        f"/api/admin/users/{USER_B_ID}/quota",
        json={"private_limit_gb": 10.0},
        headers=_headers("svc:storage:admin"),
    )

    assert response.status_code == 404
    assert _error_code(response) == ErrorCode.USER_NOT_FOUND
    quota_repo.update_private_limit.assert_not_called()


@pytest.mark.asyncio
async def test_update_user_quota_rejects_user_missing_from_local_table() -> None:
    service = AdminService(
        user_repo=FakeUserRepository(),
        quota_repo=AsyncMock(),
        file_repo=MagicMock(),
        disk_router=MagicMock(),
        settings=get_settings(),
    )

    with pytest.raises(UserNotFoundError):
        await service.update_user_quota(
            ADMIN_USER_ID,
            USER_B_ID,
            private_limit_gb=10.0,
        )
