"""Infrastructure: GPU lease in Redis (`SET NX PX`), ADR-006.

Key `gpu:lease`, TTL 30 s, heartbeat 5 s. `acquire` is atomic; no lease — `LeaseDenied`
(a wait, not an error: attempt does not grow). The key value stores the class so that
`interactive`/`stream` can preempt `offline` between steps instead of queueing behind it.
"""

from __future__ import annotations

import logging
import threading
import uuid

from redis import Redis

from app.application.ports.gpu_lease import GpuClass, LeaseDenied

logger = logging.getLogger(__name__)

LEASE_KEY = "gpu:lease"


class RedisGpuLease:
    def __init__(self, url: str, *, ttl_ms: int, heartbeat_ms: int) -> None:
        self._ttl_ms = ttl_ms
        self._heartbeat_ms = heartbeat_ms
        self._token = ""
        self._redis: Redis | None = None
        try:
            self._redis = Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gpu_lease_redis_init_failed error=%s", type(exc).__name__)
            self._redis = None

    @property
    def held(self) -> bool:
        return bool(self._token and self._redis is not None)

    def _set_nx_px(self, value: str, px: int) -> bool:
        if self._redis is None:
            return False
        try:
            return bool(self._redis.set(LEASE_KEY, value, nx=True, px=px))
        except Exception as exc:  # noqa: BLE001
            logger.warning("gpu_lease_redis_error error=%s", type(exc).__name__)
            return False

    def acquire(self, klass: GpuClass) -> None:
        """Tries to take the lease atomically.

        Diarization (`offline`) preempts nobody: busy → LeaseDenied.
        """
        if self._redis is None:
            raise LeaseDenied("redis unavailable")
        token = f"{klass}:{uuid.uuid4().hex}"
        if not self._set_nx_px(token, self._ttl_ms):
            raise LeaseDenied(f"gpu busy (klass={klass})")
        self._token = token

    def heartbeat(self) -> None:
        """Extends the TTL only if the lease is still ours (value comparison)."""
        if not self.held:
            return
        # Lua for an atomic compare-set: extend only our own lease.
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('pexpire', KEYS[1], tonumber(ARGV[2])) "
            "else return 0 end"
        )
        try:
            self._redis.eval(script, 1, LEASE_KEY, self._token, self._ttl_ms)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning("gpu_lease_heartbeat_error error=%s", type(exc).__name__)

    def release(self) -> None:
        if self._token and self._redis is not None:
            script = (
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end"
            )
            try:
                self._redis.eval(script, 1, LEASE_KEY, self._token)  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                logger.warning("gpu_lease_release_error error=%s", type(exc).__name__)
        self._token = ""

    def start_heartbeat(self) -> HeartbeatThread:
        """Starts a background heartbeat (every `heartbeat_ms`) while we compute."""
        thread = HeartbeatThread(self, self._heartbeat_ms / 1000)
        thread.start()
        return thread


class HeartbeatThread(threading.Thread):
    """Background heartbeat every `interval_s` while we hold the lease and are not asked to stop."""

    def __init__(self, lease: RedisGpuLease, interval_s: float) -> None:
        super().__init__(daemon=True, name="gpu-lease-heartbeat")
        self._lease = lease
        self._interval_s = interval_s
        # NOT `self._stop`: that name belongs to `threading.Thread` (the internal
        # wait-for-exit hook). Overriding it with an Event makes `Thread.join()`
        # raise `TypeError: 'Event' object is not callable` — which killed both
        # consumers after the first job on the stand (2026-11-01).
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            # `wait`, not `sleep`: `stop()` must wake the thread at once. With `sleep(5)` the
            # caller's `join()` blocked for the rest of the interval after every job.
            if self._stop_event.wait(self._interval_s):
                return
            if not self._lease.held:
                return
            self._lease.heartbeat()
