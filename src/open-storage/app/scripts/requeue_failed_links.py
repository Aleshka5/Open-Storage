"""Re-queue links that gave up, so RAG re-registers them from the live object.

``FAILED`` rows with ``rag_file_id`` keep a RAG file that already gave up on its
own side (``processing_attempts_exceeded``, ``timeout``): polling it again only
returns the same error. Moving the row to ``REINDEX_PENDING`` makes the sync job
delete that stale file and register a fresh one from the same storage key, which
is what recovers documents after the OCR service comes back.

Nothing is deleted from storage: only vectors and the RAG-side file go away.

Usage inside the app container::

    podman exec -i webstorage_app_1 python /app/scripts/requeue_failed_links.py --dry-run
    podman exec -i webstorage_app_1 python /app/scripts/requeue_failed_links.py
"""

from __future__ import annotations

import argparse
import asyncio
import json

from loguru import logger
from sqlalchemy import select

from app.domain.indexing import IndexLinkState
from app.infrastructure.database.models import (
    FileIndexLink,
    FileRecord as FileRecordModel,
)
from app.infrastructure.database.repositories.file_index_link_repo import (
    FileIndexLinkRepository,
)
from app.infrastructure.database.session import async_session_factory


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--error-code",
        action="append",
        default=None,
        help="only these last_error_code values (default: every FAILED row)",
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async with async_session_factory() as session:
        stmt = (
            select(FileIndexLink, FileRecordModel.original_name)
            .join(FileRecordModel, FileIndexLink.file_record_id == FileRecordModel.id)
            .where(FileIndexLink.state == IndexLinkState.FAILED.value)
            .order_by(FileIndexLink.created_at)
            .limit(args.limit)
        )
        rows = (await session.execute(stmt)).all()
        if args.error_code:
            wanted = set(args.error_code)
            rows = [row for row in rows if row[0].last_error_code in wanted]

        logger.info("failed links to re-queue: {}", len(rows))
        links = FileIndexLinkRepository(session)
        requeued = 0
        for model, name in rows:
            logger.info(
                "{} {} error={} rag_file_id={}{}",
                model.id,
                name,
                model.last_error_code,
                model.rag_file_id,
                " [dry-run]" if args.dry_run else "",
            )
            if args.dry_run:
                continue
            updated = await links.apply_transition(
                model.id,
                state=IndexLinkState.REINDEX_PENDING,
                attempts=0,
                next_attempt_at=None,
                last_error_code=None,
            )
            if updated is not None:
                requeued += 1
        if not args.dry_run:
            await session.commit()

        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "candidates": len(rows),
                    "requeued": requeued,
                    "with_rag_file_id": sum(1 for row in rows if row[0].rag_file_id),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
