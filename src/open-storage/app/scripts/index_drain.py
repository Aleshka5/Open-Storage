"""Drain the RAG index queue without waiting for the 60 s scheduler tick.

Why it exists: ``claim_due`` takes the oldest *due* rows and the batch is
``RAG_INDEX_BATCH_SIZE`` (20). A handful of rows that stay ``SUBMITTED`` while
RAG processes them are re-claimed on every tick and can fill the whole batch,
so a large backlog never moves. This script runs the same tick repeatedly with
a larger batch, which is an operational workaround, not a scheduler change.

Usage inside the app container::

    podman exec -e RAG_INDEX_BATCH_SIZE=200 webstorage_app_1 \
        python /app/scripts/index_drain.py --max-ticks 60 --sleep 2

Exits when a tick claims nothing, so it is safe to re-run.
"""

from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from app.application.indexing.sync_job import run_index_sync
from app.infrastructure.database.repositories.file_index_link_repo import (
    FileIndexLinkRepository,
)
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.disk_router import STORAGE_VOLUME_ID
from app.infrastructure.rag.client import RagIndexClient
from app.infrastructure.storage.s3_adapter import build_disk_root_adapter
from config import get_settings


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-ticks", type=int, default=60)
    parser.add_argument("--sleep", type=float, default=2.0)
    args = parser.parse_args()

    rag_settings = get_settings().rag
    logger.info(
        "index drain started: batch={} interval={}s max_ticks={}",
        rag_settings.index_batch_size,
        rag_settings.sync_interval_seconds,
        args.max_ticks,
    )

    totals = {"claimed": 0, "transitioned": 0, "retried": 0, "failed": 0, "skipped": 0}
    rag = RagIndexClient(
        base_url=rag_settings.base_url,
        timeout_seconds=rag_settings.timeout_seconds,
    )
    try:
        for tick in range(1, args.max_ticks + 1):
            async with async_session_factory() as session:
                links = FileIndexLinkRepository(session)
                objects = build_disk_root_adapter(STORAGE_VOLUME_ID)
                result = await run_index_sync(links, rag, objects)
                await session.commit()
            logger.info(
                "tick {} claimed={} transitioned={} retried={} failed={} skipped={}",
                tick,
                result.claimed,
                result.transitioned,
                result.retried,
                result.failed,
                result.skipped,
            )
            for key in totals:
                totals[key] += getattr(result, key)
            if result.claimed == 0:
                logger.info("queue is empty; stopping after {} ticks", tick)
                break
            await asyncio.sleep(args.sleep)
    finally:
        await rag.aclose()

    logger.info("index drain finished: {}", totals)


if __name__ == "__main__":
    asyncio.run(main())
