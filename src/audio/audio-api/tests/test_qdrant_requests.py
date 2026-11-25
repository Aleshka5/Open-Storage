"""Bodies of the real Qdrant requests: contract checks a fake cannot see.

US-07 review (D1/D4): the adapter sent a `delete` with a `filter` on the `"OWNER"` field — no
such field in the payload, so on the live Qdrant the request matched zero points and answered
200. The fake compared the same invented literal, so the tests stayed green.

What is checked here is exactly the HTTP request body that will go to Qdrant.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.infrastructure.qdrant import PAYLOAD_INDEX_FIELDS, QdrantVoiceIndex

OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
POINT = "f97b2c17-2a2a-5845-bc59-3ac29f780cf1"


class _Recorder:
    """Captures (method, path, body) of all Qdrant requests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            body: Any = None
            if request.content:
                try:
                    body = json.loads(request.content)
                except ValueError:
                    body = request.content
            self.calls.append(
                {"method": request.method, "path": request.url.path, "body": body}
            )
            if request.url.path.endswith("/points/delete"):
                return httpx.Response(200, json={"result": {"status": "completed"}})
            return httpx.Response(200, json={"result": {}})

        return httpx.MockTransport(handler)

    def bodies(self, suffix: str) -> list[Any]:
        return [c["body"] for c in self.calls if c["path"].endswith(suffix)]


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    original = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = rec.transport()
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return rec


async def test_delete_point_sends_no_filter_on_invented_field(recorder):
    """`delete` must not filter on a field that is not in the payload.

    The "Me"/nick id is deterministic as `uuid5(owner, ...)` — it is already owner-safe, so the
    `points` selector is enough and cannot touch a foreign point.
    """
    idx = QdrantVoiceIndex("http://qdrant:6333", collection="audio_voices")
    await idx.delete_point(OWNER, point_id=POINT)

    bodies = recorder.bodies("/points/delete")
    assert len(bodies) == 1
    body = bodies[0]
    assert body["points"] == [POINT]
    # No `filter` on the `"OWNER"` field (it does not exist in the payload).
    raw = json.dumps(body)
    assert "OWNER" not in raw
    if "filter" in body:
        # If the filter is ever brought back, it must reference the real field.
        for must in body["filter"].get("must", []):
            assert must["key"] in PAYLOAD_INDEX_FIELDS, must["key"]


async def test_upsert_me_payload_carries_real_owner_field(recorder):
    """The "Me" point payload carries the real owner field name from the collection indexes."""
    idx = QdrantVoiceIndex("http://qdrant:6333", collection="audio_voices")
    # The real field name comes from code, not typed by hand: the secret-redaction layer
    # in tool output masks it, and manual typing has already caused corruption.
    import app.domain.recording  # noqa: F401
    from app.infrastructure.mongo import MongoRecordingRepo  # noqa: F401

    owner_field = PAYLOAD_INDEX_FIELDS[0]
    assert owner_field.startswith("owner_") and owner_field.endswith("_id"), owner_field
    await idx.upsert_me(
        OWNER,
        point_id=POINT,
        vector=[0.0] * 256,
        payload={owner_field: OWNER, "kind": "me"},
    )
    bodies = recorder.bodies("/points")
    assert bodies, "upsert sent no request"
    point = bodies[-1]["points"][0]
    assert owner_field in point["payload"]
    assert point["payload"][owner_field] == OWNER
    # The owner field must be in the collection's payload index list.
    assert owner_field in PAYLOAD_INDEX_FIELDS
