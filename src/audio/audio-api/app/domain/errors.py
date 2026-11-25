"""Domain: product error codes.

Single error envelope (constitution.md §11). The code and HTTP status are fixed by the contract
`docs/backend/audio-api/api.md`.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    IDENTITY_MISSING = "IDENTITY_MISSING"
    NOT_FOUND = "NOT_FOUND"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    AUDIO_NOT_READY = "AUDIO_NOT_READY"
    ASSIGNMENT_LOCKED = "ASSIGNMENT_LOCKED"
    VOICE_NOT_READY = "VOICE_NOT_READY"
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"
    ASR_BUSY = "ASR_BUSY"
    QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    VOICE_INDEX_UNAVAILABLE = "VOICE_INDEX_UNAVAILABLE"
    VOICE_INDEX_INCOMPATIBLE = "VOICE_INDEX_INCOMPATIBLE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"


# HTTP status per error code (per api.md).
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.IDENTITY_MISSING: 401,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA: 415,
    ErrorCode.AUDIO_NOT_READY: 409,
    ErrorCode.ASSIGNMENT_LOCKED: 409,
    ErrorCode.VOICE_NOT_READY: 409,
    ErrorCode.ASR_UNAVAILABLE: 503,
    ErrorCode.ASR_BUSY: 503,
    ErrorCode.QUEUE_UNAVAILABLE: 503,
    ErrorCode.STORAGE_UNAVAILABLE: 503,
    ErrorCode.VOICE_INDEX_UNAVAILABLE: 503,
    ErrorCode.VOICE_INDEX_INCOMPATIBLE: 503,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL: 500,
}
