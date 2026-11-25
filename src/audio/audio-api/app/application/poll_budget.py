"""Polling budget: `429 RATE_LIMITED` instead of silently exceeding the gateway limit (US-08).

Why. The limit of `180` requests/min per IP is held by the **gateway** (ADR-005: polling interval
1.5 s ≈ 40 requests/min per open chat; 2–3 recordings in processing are already at the edge).
The client-side error is invisible to the service: the `429` comes from another process,
and in the `audio-api` logs the run looks successful. That is why the service itself has a
**voluntary** counter on `GET /api/recordings/{id}/phrases`:

- the budget is `POLL_BUDGET_PER_MINUTE` requests per minute per owner (default `0` —
  disabled; enabled together with the rollout, value not above the gateway limit);
- the window is a sliding 60 s, state in process memory (`audio-api` is a single instance,
  ADR-005: "no state on the server" still holds, this is not storage);
- exceeding it → `429 RATE_LIMITED` through the usual `AppError` envelope, plus a log record
  with `error_code=RATE_LIMITED` — the share of `429`s is counted from it (ADR-005 follow-up).

The client already handles this per contract: the interval doubles up to 6 s (`docs/frontend/
chat-and-player.md`), so enabling the budget requires no SPA change.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from app.domain.app_error import AppError
from app.domain.errors import ErrorCode

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60.0


class PollBudget:
    """Sliding window of "N requests per 60 s" per key (owner)."""

    def __init__(self, limit: int, *, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self._limit = max(0, int(limit))
        self._window = float(window)
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    @property
    def limit(self) -> int:
        return self._limit

    def check(self, key: str) -> None:
        """Counts a request; raises `429 RATE_LIMITED` when exceeded.

        A disabled budget (`limit == 0`) counts nothing and holds no memory.
        """
        if not self.enabled:
            return
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        edge = now - self._window
        while hits and hits[0] <= edge:
            hits.popleft()
        if len(hits) >= self._limit:
            logger.warning(
                "poll_budget_exceeded owner=%s limit=%d error_code=RATE_LIMITED stage=poll",
                key[:8],
                self._limit,
            )
            raise AppError(ErrorCode.RATE_LIMITED, "Polling too often, increase the interval")
        hits.append(now)

    def reset(self, key: str | None = None) -> None:
        """Resets the window (tests and `POLL_BUDGET_RESET` on a configuration change)."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
