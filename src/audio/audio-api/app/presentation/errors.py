"""Error handler: the single envelope `{"detail": {error_code, message, ...}}`."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.app_error import AppError
from app.domain.errors import ErrorCode

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.detail()},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic validation (e.g. an empty/too long title) → 422 per contract.
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "error_code": "VALIDATION_ERROR",
                    "message": "Invalid request body",
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.exception("internal_error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "error_code": ErrorCode.INTERNAL.value,
                    "message": "Internal error",
                }
            },
        )
