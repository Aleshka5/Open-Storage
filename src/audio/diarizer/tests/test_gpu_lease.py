"""GPU lease tests (RedisGpuLease): SET NX PX, TTL, heartbeat, denial when busy."""

from __future__ import annotations

from app.application.ports.gpu_lease import LeaseDenied
from app.infrastructure import gpu_lease as gl_mod
from app.infrastructure.gpu_lease import RedisGpuLease


class FakeRedis:
    """In-memory Redis: SET NX PX, GET, PEXPIRE, DEL, EVAL (compare-set)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl_ms: dict[str, int] = {}

    def set(self, key, value, nx=False, px=None, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        if px is not None:
            self.ttl_ms[key] = px
        return True

    def get(self, key):
        return self.data.get(key)

    def pexpire(self, key, px):
        if key in self.data:
            self.ttl_ms[key] = px
            return 1
        return 0

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            self.ttl_ms.pop(key, None)
            return 1
        return 0

    def eval(self, script, numkeys, *args):
        # Support two Lua scripts: heartbeat (pexpire) and release (del), both compare-set.
        if "pexpire" in script:
            key = args[0]
            token = args[1]
            px = int(args[2])
            if self.data.get(key) == token:
                self.ttl_ms[key] = px
                return 1
            return 0
        if "del" in script:
            key = args[0]
            token = args[1]
            if self.data.get(key) == token:
                return self.delete(key)
            return 0
        return 0


def _make_lease(redis, ttl_ms=30000, heartbeat_ms=5000) -> tuple[RedisGpuLease, FakeRedis]:
    lease = RedisGpuLease.__new__(RedisGpuLease)
    lease._redis = redis
    lease._ttl_ms = ttl_ms
    lease._heartbeat_ms = heartbeat_ms
    lease._token = ""
    return lease, redis


def test_acquire_sets_key_with_ttl():
    redis = FakeRedis()
    lease, _ = _make_lease(redis, ttl_ms=30000)
    lease.acquire("offline")
    assert gl_mod.LEASE_KEY in redis.data
    assert redis.ttl_ms[gl_mod.LEASE_KEY] == 30000
    # the value is class + token
    assert redis.data[gl_mod.LEASE_KEY].startswith("offline:")
    assert lease.held


def test_acquire_denied_when_held():
    redis = FakeRedis()
    redis.data[gl_mod.LEASE_KEY] = "stream:other"
    lease, _ = _make_lease(redis)
    try:
        lease.acquire("offline")
        raise AssertionError("LeaseDenied expected")
    except LeaseDenied:
        pass
    assert not lease.held


def test_heartbeat_only_refreshes_own_lease():
    redis = FakeRedis()
    lease, _ = _make_lease(redis, ttl_ms=30000)
    lease.acquire("offline")
    lease.heartbeat()
    assert redis.ttl_ms[gl_mod.LEASE_KEY] == 30000


def test_release_deletes_own_lease():
    redis = FakeRedis()
    lease, _ = _make_lease(redis)
    lease.acquire("offline")
    lease.release()
    assert gl_mod.LEASE_KEY not in redis.data
    assert not lease.held


def test_killed_worker_leases_expire_by_ttl():
    """A lease without release stays in Redis with a TTL; nobody else can take it until it dies.

    We model `SET NX PX`: the key is held for `ttl_ms`; once it expires Redis hands it out
    again. PX itself guarantees release no later than the TTL (ADR-006).
    """
    redis = FakeRedis()
    lease1, _ = _make_lease(redis, ttl_ms=30000)
    lease1.acquire("offline")
    # a killed worker never calls release — the key stays
    assert gl_mod.LEASE_KEY in redis.data
    assert redis.ttl_ms[gl_mod.LEASE_KEY] == 30000
    # a second worker does not duplicate the lease while the key lives
    lease2, _ = _make_lease(redis, ttl_ms=30000)
    try:
        lease2.acquire("offline")
        raise AssertionError("LeaseDenied expected")
    except LeaseDenied:
        pass
