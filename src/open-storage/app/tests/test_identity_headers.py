"""Identity v1 headers are the only identity input."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain.entities.auth_principal import AuthPrincipal
from app.domain.entities.user import User
from app.domain.exceptions import IdentityProjectionError
from app.domain.value_objects.error_codes import ErrorCode
from app.domain.value_objects.role import Role
from app.infrastructure.database.session import get_async_session
from app.presentation.dependencies.auth import get_current_user, get_user_repository
from app.presentation.exception_handlers import register_exception_handlers
from app.presentation.middleware.check_role import check_role
from app.presentation.routers.auth_router import router as auth_router
from config import get_settings

FAMILY_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
FILES = "/api/files"
SHARED = "/api/shared"
ADMIN = "/api/admin/users"
PHOTOS = "/api/photos"
VAULT = "/api/private/quota"


class FakeUserRepository:
    def __init__(self) -> None:
        self.principals: list[AuthPrincipal] = []

    async def upsert_from_principal(self, principal: AuthPrincipal) -> User | None:
        self.principals.append(principal)
        try:
            user_id = UUID(principal.id)
        except ValueError:
            return None
        return User(
            id=user_id,
            email=principal.email,
            role=Role.STRANGER,
            is_active=True,
            created_at=datetime.now(UTC),
        )


def _v1_headers(
    *,
    roles: str = "svc:storage:family",
    subject: str | None = str(FAMILY_USER_ID),
    include_legacy: bool = False,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "X-Auth-Email": "family@example.test",
        "X-Auth-Name": "Family",
        "X-Auth-Roles": roles,
        "X-Auth-Session": "sid-one",
    }
    if subject is not None:
        headers["X-Auth-Subject"] = subject
    if include_legacy:
        headers["X-User-Id"] = "22222222-2222-2222-2222-222222222222"
        headers["X-Storage-Role"] = "ADMIN"
        headers["X-Auth-User-Id"] = "33333333-3333-3333-3333-333333333333"
    return headers


def _build_app(user_repo: FakeUserRepository | None = None) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)

    @app.get(FILES)
    async def files(_user: User = Depends(get_current_user)) -> dict[str, bool]:
        return {"ok": True}

    @app.get(SHARED)
    async def shared(
        _user: User = Depends(check_role(Role.FAMILY, Role.ADMIN)),
    ) -> dict[str, bool]:
        return {"ok": True}

    @app.get(ADMIN)
    async def admin_users(
        _user: User = Depends(check_role(Role.ADMIN)),
    ) -> dict[str, bool]:
        return {"ok": True}

    @app.get(PHOTOS)
    async def photos(_user: User = Depends(get_current_user)) -> dict[str, bool]:
        return {"ok": True}

    @app.get(VAULT)
    async def vault(_user: User = Depends(get_current_user)) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/edge-shaped")
    async def edge_shaped() -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    repo = user_repo or FakeUserRepository()
    app.dependency_overrides[get_user_repository] = lambda: repo

    async def fake_session():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_async_session] = fake_session
    return app


def _error_code(response) -> str:
    return response.json()["detail"]["error_code"]


def test_v1_headers_reach_each_section_as_the_role_allows() -> None:
    client = TestClient(_build_app())
    family = _v1_headers(roles="svc:storage:family")
    admin = _v1_headers(roles="svc:storage:admin")
    stranger = _v1_headers(roles="")
    blocked = _v1_headers(roles="svc:storage:blocked")

    assert client.get(FILES, headers=family).status_code == 200
    assert client.get(SHARED, headers=family).status_code == 200
    assert client.get(PHOTOS, headers=family).status_code == 200
    assert client.get(VAULT, headers=family).status_code == 200
    admin_denied = client.get(ADMIN, headers=family)
    assert admin_denied.status_code == 403
    assert _error_code(admin_denied) == ErrorCode.ACCESS_DENIED
    assert "error" not in admin_denied.json()

    assert client.get(ADMIN, headers=admin).status_code == 200
    assert client.get(SHARED, headers=admin).status_code == 200
    assert client.get(PHOTOS, headers=admin).status_code == 200
    assert client.get(VAULT, headers=admin).status_code == 200

    shared_denied = client.get(SHARED, headers=stranger)
    assert shared_denied.status_code == 403
    assert _error_code(shared_denied) == ErrorCode.ACCESS_DENIED
    assert client.get(FILES, headers=stranger).status_code == 200
    assert client.get(PHOTOS, headers=stranger).status_code == 200

    for path in (FILES, SHARED, ADMIN, PHOTOS, VAULT):
        response = client.get(path, headers=blocked)
        assert response.status_code == 403
        assert _error_code(response) == ErrorCode.ACCESS_DENIED


def test_legacy_headers_do_not_change_a_v1_request() -> None:
    plain_repo = FakeUserRepository()
    legacy_repo = FakeUserRepository()
    plain = TestClient(_build_app(plain_repo))
    with_legacy = TestClient(_build_app(legacy_repo))

    family = _v1_headers()
    mixed = _v1_headers(include_legacy=True)

    for path in (FILES, SHARED, PHOTOS, VAULT):
        first = plain.get(path, headers=family)
        second = with_legacy.get(path, headers=mixed)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()

    assert plain_repo.principals[0].id == str(FAMILY_USER_ID)
    assert legacy_repo.principals[0].id == str(FAMILY_USER_ID)
    assert legacy_repo.principals[0].role is Role.FAMILY


def test_legacy_headers_alone_are_unauthorized_and_write_no_user() -> None:
    user_repo = FakeUserRepository()
    client = TestClient(_build_app(user_repo))

    response = client.get(
        FILES,
        headers={
            "X-User-Id": str(FAMILY_USER_ID),
            "X-Auth-User-Id": str(FAMILY_USER_ID),
            "X-Storage-Role": Role.ADMIN.value,
        },
    )

    assert response.status_code == 401
    assert _error_code(response) == ErrorCode.UNAUTHORIZED
    assert user_repo.principals == []


def test_missing_subject_is_unauthorized_and_writes_no_user() -> None:
    user_repo = FakeUserRepository()
    client = TestClient(_build_app(user_repo))

    response = client.get(FILES, headers=_v1_headers(subject=None))

    assert response.status_code == 401
    assert _error_code(response) == ErrorCode.UNAUTHORIZED
    assert set(response.json()) == {"detail"}
    assert set(response.json()["detail"]) >= {"error_code", "message"}
    assert user_repo.principals == []


def test_non_uuid_subject_is_not_rejected_as_anonymous() -> None:
    user_repo = FakeUserRepository()
    client = TestClient(_build_app(user_repo), raise_server_exceptions=False)

    response = client.get(FILES, headers=_v1_headers(subject="not-a-uuid"))

    assert response.status_code != 401
    assert user_repo.principals[0].id == "not-a-uuid"
    assert response.status_code == 500
    assert _error_code(response) == ErrorCode.INTERNAL_ERROR


def test_storage_admin_without_realm_admin_reaches_admin() -> None:
    client = TestClient(_build_app())

    without_realm = client.get(ADMIN, headers=_v1_headers(roles="svc:storage:admin"))
    with_realm = client.get(ADMIN, headers=_v1_headers(roles="admin svc:storage:admin"))
    realm_only = client.get(ADMIN, headers=_v1_headers(roles="admin"))

    assert without_realm.status_code == 200
    assert with_realm.status_code == 200
    assert realm_only.status_code == 403
    assert _error_code(realm_only) == ErrorCode.ACCESS_DENIED


def test_me_returns_projected_storage_role() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/auth/me", headers=_v1_headers(roles="svc:storage:family admin"))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(FAMILY_USER_ID)
    assert body["email"] == "family@example.test"
    assert body["role"] == Role.FAMILY.value


def test_app_does_not_rewrite_a_body_it_did_not_produce() -> None:
    client = TestClient(_build_app())

    response = client.get("/edge-shaped")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_identity_conflict_is_a_client_error() -> None:
    class ConflictRepository(FakeUserRepository):
        async def upsert_from_principal(self, principal: AuthPrincipal) -> User | None:
            raise IdentityProjectionError(
                "Identity subject cannot be mapped onto a single local user"
            )

    client = TestClient(_build_app(ConflictRepository()))

    response = client.get(FILES, headers=_v1_headers())

    assert response.status_code == 409
    assert _error_code(response) == ErrorCode.IDENTITY_CONFLICT
    assert response.json()["detail"]["message"] == (
        "This sign-in cannot be matched to a single archive"
    )


def test_settings_cache_still_clears() -> None:
    get_settings.cache_clear()
    get_settings()
    get_settings.cache_clear()
