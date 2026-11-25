"""Domain: application error with a code from the contract.

The single error that presentation catches and wraps into the envelope
`{"detail": {"error_code", "message", "recording_id", ...}}`.
"""

from __future__ import annotations

from typing import Any

from app.domain.errors import HTTP_STATUS, ErrorCode


class AppError(Exception):
    """A domain/application level error carrying an error code and optional context."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        recording_id: str | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recording_id = recording_id
        self.extra = extra

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.code]

    def detail(self) -> dict[str, Any]:
        """Body of the error envelope."""
        d: dict[str, Any] = {"error_code": self.code.value, "message": self.message}
        if self.recording_id is not None:
            d["recording_id"] = self.recording_id
        d.update(self.extra)
        return d
