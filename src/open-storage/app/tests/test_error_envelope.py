"""The app's own errors keep the detail envelope. A gateway body is not rewritten."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.domain.value_objects.error_codes import ErrorCode
from app.presentation.exception_handlers import register_exception_handlers


def test_app_http_exception_keeps_detail_envelope() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api/files")
    async def files() -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": ErrorCode.ACCESS_DENIED,
                "message": "Insufficient permissions for this section",
            },
        )

    response = TestClient(app).get("/api/files")

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "error_code": ErrorCode.ACCESS_DENIED,
            "message": "Insufficient permissions for this section",
        }
    }


def test_gateway_shaped_body_passes_through() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-owned")
    async def not_owned() -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    response = TestClient(app).get("/not-owned")

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}
