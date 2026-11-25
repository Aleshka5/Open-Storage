"""Tests of the aggregated `/health` (US-08, item 2) — happy and negative.

The rule being checked:

- `mongo` and `minio` are required: `down` → `503`, `status: "down"`,
  `error_code: STORAGE_UNAVAILABLE`, the name in `down[]`;
- `qdrant`, `rabbitmq`, `asr` are optional: `down` → `200` with `status: "degraded"`.
  `asr` matters especially: a killed `asr-worker` must not break the `audio-api` healthcheck
  in compose (otherwise `make up` "waits for the model" forever).

The body holds no text, keys or tokens — only storage names and statuses.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.presentation.api import create_app
from app.presentation.container import Container


@pytest.fixture
def client(settings, repo, voice_repo, voice_index, store, queue, monkeypatch):
    """TestClient with fakes; the external HTTP checks (qdrant/asr) are alive by default."""
    async def _qdrant_ok(url):
        return url is not None

    async def _asr_ok(ws_url):
        return ws_url is not None

    monkeypatch.setattr("app.presentation.health._qdrant_ok", _qdrant_ok)
    monkeypatch.setattr("app.presentation.health._asr_ok", _asr_ok)

    c = Container(
        settings,
        repo=repo,
        store=store,
        queue=queue,
        voice_repo=voice_repo,
        voice_index=voice_index,
    )
    Container.set_instance(c)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_health_all_ok_is_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "status": "ok",
        "mongo": "ok",
        "minio": "ok",
        "qdrant": "ok",
        "rabbitmq": "ok",
        "asr": "ok",
    }
    assert "error_code" not in body


def test_health_public_without_identity(client):
    """`/health` answers 200 without an identity header."""
    r = client.get("/health")
    assert r.status_code == 200


def test_minio_down_is_503(client, store):
    """MinIO stopped: `503` and `minio: down` (US-08 acceptance criterion)."""
    store.available = False
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["minio"] == "down"
    assert body["mongo"] == "ok"
    assert body["status"] == "down"
    assert body["error_code"] == "STORAGE_UNAVAILABLE"
    assert body["down"] == ["minio"]


def test_minio_check_raises_is_503(client, store):
    """An exception from `store.check()` — the same `down`, not a 500."""

    async def _boom():
        raise ConnectionError("minio unreachable")

    store.check = _boom
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["minio"] == "down"


def test_mongo_down_is_503(client, repo):
    class _FailingDb:
        async def command(self, name: str):
            raise ConnectionError("mongo unreachable")

    class _Recordings:
        database = _FailingDb()

    repo._recordings = _Recordings()
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["mongo"] == "down"
    assert body["down"] == ["mongo"]
    assert body["error_code"] == "STORAGE_UNAVAILABLE"


def test_both_stores_down_lists_both(client, store, repo):
    store.available = False

    class _FailingDb:
        async def command(self, name: str):
            raise ConnectionError("down")

    class _Recordings:
        database = _FailingDb()

    repo._recordings = _Recordings()
    r = client.get("/health")
    assert r.status_code == 503
    assert sorted(r.json()["down"]) == ["minio", "mongo"]


def test_asr_down_does_not_fail_endpoint(client, monkeypatch):
    """asr-worker killed: `200` and `asr: down` — reading an open chat keeps working."""

    async def _asr_down(ws_url):
        return False

    monkeypatch.setattr("app.presentation.health._asr_ok", _asr_down)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["asr"] == "down"
    assert r.json()["status"] == "degraded"


def test_asr_hits_asr_worker_health_not_stream_path(settings):
    """The `asr` check goes to the worker's `/health`: `/v1/stream` is a socket, not HTTP."""
    from app.presentation.health import _asr_ok

    seen: list[str] = []

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            seen.append(url)
            return _Resp()

    import app.presentation.health as health_mod

    original = health_mod.httpx.AsyncClient
    health_mod.httpx.AsyncClient = _Client
    try:
        import asyncio

        ok = asyncio.run(_asr_ok("ws://asr-worker:8020/v1/stream"))
    finally:
        health_mod.httpx.AsyncClient = original

    assert ok is True
    assert seen == ["http://asr-worker:8020/health"]


def test_rabbitmq_and_qdrant_down_degrade_only(client, queue, monkeypatch):
    queue.available = False

    async def _qdrant_down(url):
        return False

    monkeypatch.setattr("app.presentation.health._qdrant_ok", _qdrant_down)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["rabbitmq"] == "down"
    assert body["qdrant"] == "down"
    assert body["mongo"] == "ok"


def test_health_body_carries_no_secrets(client, settings):
    """The body holds only storage names and statuses (US-08: no tokens/keys)."""
    body = client.get("/health").text
    assert settings.s3_secret_key not in body
    for banned in ("original.", "norm.wav", "note.webm", "u/", "hf_"):
        assert banned not in body
