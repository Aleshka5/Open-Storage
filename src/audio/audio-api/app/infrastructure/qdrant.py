"""Infrastructure: Qdrant via the REST API (httpx) — the `audio_voices` collection.

We do not pull in the heavy `qdrant-client`; HTTP is enough: collection create/read, point search
and upsert. The collection dimension is a contract; a mismatch → `VoiceIndexIncompatible`
(`503 VOICE_INDEX_INCOMPATIBLE`), not a silent overwrite (ADR-007).

`QDRANT_URL` empty → the index counts as "disabled" (a deployment without Qdrant):
`ensure` does nothing, search and writes raise `VoiceIndexUnavailable`. This is a single
semantics of "no index", so that dev without Qdrant does not fail at startup.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.application.ports.voice_index import (
    VoiceIndexIncompatible,
    VoiceIndexUnavailable,
)

logger = logging.getLogger(__name__)

# Payload indexes of the collection (external_contracts/qdrant/collection.md): the owner filter
# turns into a scan without an index on the owner field. `kind` and
# `nick_id` — for the "Me" lookup and a point check of a nick.
PAYLOAD_INDEX_FIELDS = ["owner_user_id", "kind", "nick_id"]


class _Point:
    """Search result — id, score, payload (used to build suggestions)."""

    def __init__(self, point_id: str, score: float, payload: dict[str, Any]) -> None:
        self.point_id = point_id
        self.score = score
        self.payload = payload


class QdrantVoiceIndex:
    def __init__(
        self,
        url: str | None,
        *,
        collection: str,
        api_key: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._url = (url or "").rstrip("/")
        self._collection = collection
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["api-key"] = self._api_key
        return h

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        if not self._url:
            raise VoiceIndexUnavailable("Qdrant is not configured (QDRANT_URL is empty)")
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.request(
                    method, f"{self._url}{path}", headers=self._headers(), **kw
                )
        except httpx.HTTPError as exc:
            raise VoiceIndexUnavailable(f"Qdrant unavailable: {type(exc).__name__}") from exc

    async def ensure_collection(self, vector_size: int) -> None:
        if not self._url:
            return
        exists = await self._get_collection()
        if exists is None:
            await self._create_collection(vector_size)
            logger.info(
                "qdrant_collection_created collection=%s size=%d",
                self._collection,
                vector_size,
            )
            return
        size = exists.get("config", {}).get("params", {}).get("vectors", {}).get("size")
        if size is not None and int(size) != int(vector_size):
            raise VoiceIndexIncompatible(
                f"collection {self._collection}: size={size}, expected {vector_size}"
            )
        # We do not "fix" an existing collection: a dimension mismatch is a 503, not a silent
        # overwrite (collection.md).

    async def _get_collection(self) -> dict[str, Any] | None:
        r = await self._request("GET", f"/collections/{self._collection}")
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant {r.status_code}")
        return r.json().get("result")

    async def _create_collection(self, vector_size: int) -> None:
        r = await self._request(
            "PUT",
            f"/collections/{self._collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
        )
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant create {r.status_code}: {r.text[:200]}")
        # Payload indexes: separate calls after creation (not atomic, but idempotent).
        for field in PAYLOAD_INDEX_FIELDS:
            await self._create_payload_index(field)

    async def _create_payload_index(self, field: str) -> None:
        body = {
            "field_name": field,
            "field_schema": "keyword",
        }
        r = await self._request(
            "PUT",
            f"/collections/{self._collection}/index",
            params={"wait": "true"},
            json=body,
        )
        if r.status_code >= 400:
            # The index is not critical for startup; we log and continue (do not crash the app).
            logger.warning(
                "qdrant_payload_index_failed collection=%s field=%s status=%d",
                self._collection,
                field,
                r.status_code,
            )

    async def search(
        self, owner_id: str, vector: list[float], *, limit: int
    ) -> list[_Point]:
        body = {
            "vector": vector,
            "filter": {
                "must": [
                    {"key": "owner_user_id", "match": {"value": owner_id}}
                ]
            },
            "limit": limit,
            "with_payload": True,
            "score_threshold": None,
        }
        r = await self._request(
            "POST",
            f"/collections/{self._collection}/points/search",
            json=body,
        )
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant search {r.status_code}")
        result = r.json().get("result", [])
        return [
            _Point(
                point_id=p.get("id"),
                score=float(p.get("score", 0.0)),
                payload=p.get("payload") or {},
            )
            for p in result
        ]

    async def has_me(self, owner_id: str) -> bool:
        # The "Me" point: kind=me for the owner. A small scroll with a filter, limit=1.
        body = {
            "filter": {
                "must": [
                    {"key": "owner_user_id", "match": {"value": owner_id}},
                    {"key": "kind", "match": {"value": "me"}},
                ]
            },
            "limit": 1,
            "with_payload": False,
            "with_vector": False,
        }
        r = await self._request(
            "POST",
            f"/collections/{self._collection}/points/scroll",
            json=body,
        )
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant scroll {r.status_code}")
        result = r.json().get("result", {})
        points = result.get("points", [])
        return len(points) > 0

    async def upsert_nick(
        self,
        owner_id: str,
        *,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        await self._upsert(point_id, vector, payload)

    async def upsert_me(
        self,
        owner_id: str,
        *,
        point_id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        await self._upsert(point_id, vector, payload)

    async def delete_point(self, owner_id: str, *, point_id: str) -> None:
        """Deletes a point by id (no `filter`).

        The `points` selector is already unambiguous: the id of "Me"/a nick is deterministic as
        `uuid5(owner, ...)`, so a foreign point cannot be deleted by this call — the id
        is computed only from one's own `owner_id`. The old `filter` referred to a
        nonexistent field and matched nothing on the live Qdrant (deleted 0 points).
        """
        body = {"points": [point_id]}
        r = await self._request(
            "POST",
            f"/collections/{self._collection}/points/delete",
            params={"wait": "true"},
            json=body,
        )
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant delete {r.status_code}")

    async def _upsert(self, point_id: str, vector: list[float], payload: dict) -> None:
        body = {"points": [{"id": point_id, "vector": vector, "payload": payload}]}
        r = await self._request(
            "PUT",
            f"/collections/{self._collection}/points",
            params={"wait": "true"},
            json=body,
        )
        if r.status_code >= 400:
            raise VoiceIndexUnavailable(f"Qdrant upsert {r.status_code}")
