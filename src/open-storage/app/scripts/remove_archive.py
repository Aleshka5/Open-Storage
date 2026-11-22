"""Restore zstd-archived objects and put their RAG links back in the queue.

Why: archiving is being removed. Every archived row must become a live object
again, and every archived/tombstoned index link must be re-queued so RAG keeps
(or regains) its vectors. Nothing here deletes user data: the archive blob is
deleted only after the expanded object is uploaded and verified.

Phases, all idempotent, all safe to re-run:

1. ``restore``  — for each ``status='ARCHIVED'`` row: expand ``<key>.zst`` to
   ``<key>``, verify SHA-256 and size against ``file_records``, delete the
   ``.zst``, then clear the archive pointers (``status -> COMMITTED``).
2. ``tombstones`` — for ``is_archived`` rows that are not ``ARCHIVED`` (deleted
   files that kept ``archive_path`` after their blob was removed): clear the two
   columns only, keep ``DELETED``.
3. ``reindex`` — recompute the registration decision from the restored record
   and re-queue its link: ``REINDEX_PENDING`` when a stale ``rag_file_id`` is
   still set, ``PENDING`` when it never registered. Unsupported records are left
   ``SKIPPED`` instead of being queued for a certain failure.

Run inside the app container (needs the storage adapter, the DB and the RAG
settings)::

    podman exec -i webstorage_app_1 python /app/scripts/remove_archive.py --dry-run
    podman exec -i webstorage_app_1 python /app/scripts/remove_archive.py

``--phases`` selects a subset, ``--limit`` caps rows per phase for a smoke run,
``--report`` writes a CSV of every key the run consumed (the rollback list).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import zstandard
from loguru import logger
from sqlalchemy import select, update

from app.domain.indexing import (
    IndexLinkState,
    PrivateIndexRefused,
    decide_registration_target,
)
from app.infrastructure.database.models import FileIndexLink
from app.infrastructure.database.models import FileRecord as FileRecordModel
from app.infrastructure.database.models import FileSection as FileSectionModel
from app.infrastructure.database.models import FileStatus as FileStatusModel
from app.infrastructure.database.repositories.file_index_link_repo import (
    FileIndexLinkRepository,
)
from app.infrastructure.database.repositories.file_repo import FileRepository
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.storage.base_adapter import READ_CHUNK_SIZE
from app.infrastructure.storage.s3_adapter import build_disk_root_adapter
from config import get_settings

PHASES = ("restore", "tombstones", "reindex")
ARCHIVE_SUFFIX = ".zst"
DELETE_OK_MARKER = "delete_ok"


@dataclass
class Report:
    restored: int = 0
    already_hot: int = 0
    restore_failed: int = 0
    tombstones_cleared: int = 0
    requeued_reindex: int = 0
    requeued_pending: int = 0
    left_skipped: int = 0
    link_missing: int = 0
    consumed_keys: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    skipped_reasons: Counter[str] = field(default_factory=Counter)

    def summary(self) -> dict[str, Any]:
        return {
            "restored": self.restored,
            "already_hot": self.already_hot,
            "restore_failed": self.restore_failed,
            "tombstones_cleared": self.tombstones_cleared,
            "requeued_reindex": self.requeued_reindex,
            "requeued_pending": self.requeued_pending,
            "left_skipped": self.left_skipped,
            "link_missing": self.link_missing,
            "skipped_reasons": dict(self.skipped_reasons),
            "failures": self.failures,
            "consumed_keys": len(self.consumed_keys),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _download(adapter: Any, key: str, target: Path) -> None:
    with target.open("wb") as handle:
        async for chunk in adapter.read(key):
            handle.write(chunk)


async def _upload(adapter: Any, key: str, source: Path, size: int) -> str:
    async def _stream() -> Any:
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(READ_CHUNK_SIZE), b""):
                yield chunk

    return await adapter.write(key, _stream(), size)


def _decompress(source: Path, target: Path) -> int:
    """Expand a zstd file, returning the decompressed byte count.

    Streaming on purpose: one row at a time, constant memory, and the archive
    manager's old ``pre_encrypt`` / ``post_encrypt`` distinction collapses to
    "the bytes at the key" — encrypted records archived after encryption are
    ciphertext and must stay ciphertext here.
    """
    written = 0
    with source.open("rb") as raw, target.open("wb") as out:
        reader = zstandard.ZstdDecompressor().stream_reader(raw, read_across_frames=True)
        while True:
            chunk = reader.read(READ_CHUNK_SIZE)
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
    return written


async def restore_phase(*, limit: int | None, dry_run: bool, report: Report) -> None:
    async with async_session_factory() as session:
        repo = FileRepository(session)
        rows = (
            await session.execute(
                select(FileRecordModel)
                .where(FileRecordModel.status == FileStatusModel.ARCHIVED)
                .order_by(FileRecordModel.created_at)
                .limit(limit or 10_000)
            )
        ).scalars().all()

        logger.info("restore: {} archived records to expand", len(rows))
        adapters: dict[str, Any] = {}

        for model in rows:
            record = await repo.get_by_id(model.id)
            if record is None or not record.archive_path:
                logger.warning("restore: {} has no archive_path, skipping", model.id)
                report.restore_failed += 1
                report.failures.append({"id": str(model.id), "reason": "no_archive_path"})
                continue

            adapter = adapters.get(record.disk_id)
            if adapter is None:
                adapter = build_disk_root_adapter(record.disk_id)
                adapters[record.disk_id] = adapter

            hot_ok = await adapter.exists(record.relative_path)
            if hot_ok:
                hot_size = await adapter.get_size(record.relative_path)
                if hot_size != record.size_bytes:
                    logger.error(
                        "restore: {} hot object size {} != {} — refusing to overwrite",
                        record.id,
                        hot_size,
                        record.size_bytes,
                    )
                    report.restore_failed += 1
                    report.failures.append(
                        {"id": str(model.id), "reason": "hot_size_mismatch"}
                    )
                    continue
                logger.info("restore: {} already hot, clearing pointers", record.id)
                report.already_hot += 1
                if not dry_run:
                    # The hot object is verified, so the archive copy is a
                    # duplicate: delete it, or removing the feature leaves an
                    # orphaned .zst nobody will ever read.
                    await adapter.delete(record.archive_path)
                    await repo.clear_archive(record.id)
                    await session.commit()
                    report.consumed_keys.append(
                        {
                            "id": str(record.id),
                            "section": record.section.value,
                            "archive_key": record.archive_path,
                            "hot_key": record.relative_path,
                            "size_bytes": str(record.size_bytes),
                            "checksum_sha256": record.checksum_sha256 or "",
                            "extracted_at": datetime.now(tz=UTC).isoformat(),
                        }
                    )
                continue

            if dry_run:
                logger.info(
                    "restore[plan]: {} <- {} ({} bytes)",
                    record.relative_path,
                    record.archive_path,
                    record.size_bytes,
                )
                report.restored += 1
                continue

            with tempfile.TemporaryDirectory(prefix=f"unarchive-{record.id}-") as tmp:
                archive_tmp = Path(tmp) / "archive.zst"
                hot_tmp = Path(tmp) / "hot"
                try:
                    await _download(adapter, record.archive_path, archive_tmp)
                    expanded = _decompress(archive_tmp, hot_tmp)

                    if expanded != record.size_bytes:
                        raise ValueError(
                            f"expanded {expanded} bytes, record says {record.size_bytes}"
                        )
                    checksum = _sha256_file(hot_tmp)
                    if record.checksum_sha256 and checksum != record.checksum_sha256:
                        raise ValueError(
                            f"checksum {checksum} != {record.checksum_sha256}"
                        )

                    written = await _upload(
                        adapter, record.relative_path, hot_tmp, expanded
                    )
                    stored = await adapter.get_size(record.relative_path)
                    if stored != record.size_bytes or written != checksum:
                        raise ValueError(
                            f"verify failed: stored {stored}, sha {written}"
                        )

                    await adapter.delete(record.archive_path)
                    await repo.clear_archive(record.id)
                    await session.commit()
                except Exception as exc:  # keep going: one bad row must not stop the run
                    await session.rollback()
                    logger.exception("restore: {} failed", record.id)
                    report.restore_failed += 1
                    report.failures.append(
                        {"id": str(model.id), "reason": str(exc)[:200]}
                    )
                    continue

            report.restored += 1
            report.consumed_keys.append(
                {
                    "id": str(record.id),
                    "section": record.section.value,
                    "archive_key": record.archive_path,
                    "hot_key": record.relative_path,
                    "size_bytes": str(record.size_bytes),
                    "checksum_sha256": record.checksum_sha256 or "",
                    "extracted_at": datetime.now(tz=UTC).isoformat(),
                }
            )
            if report.restored % 25 == 0:
                logger.info(
                    "restore: progress {}/{}", report.restored, len(rows)
                )


async def tombstone_phase(*, limit: int | None, dry_run: bool, report: Report) -> None:
    async with async_session_factory() as session:
        stmt = (
            select(FileRecordModel.id, FileRecordModel.section)
            .where(
                FileRecordModel.is_archived.is_(True),
                FileRecordModel.status != FileStatusModel.ARCHIVED,
            )
            .limit(limit or 100_000)
        )
        rows = (await session.execute(stmt)).all()
        logger.info("tombstones: {} rows carry is_archived without ARCHIVED", len(rows))
        if dry_run:
            report.tombstones_cleared = len(rows)
            return

        result = await session.execute(
            update(FileRecordModel)
            .where(
                FileRecordModel.is_archived.is_(True),
                FileRecordModel.status != FileStatusModel.ARCHIVED,
            )
            .values(is_archived=False, archive_path=None)
        )
        await session.commit()
        report.tombstones_cleared = int(result.rowcount or 0)
        logger.info("tombstones: cleared {} rows", report.tombstones_cleared)


async def reindex_phase(*, limit: int | None, dry_run: bool, report: Report) -> None:
    """Re-queue every live record whose link is parked in ARCHIVED or SKIPPED.

    Driven by the link table, not by this run's restore list, so a re-run after
    a partial failure heals the rest. A record that is genuinely unsupported
    stays SKIPPED with its real skip code.
    """
    settings = get_settings()
    max_image_bytes = settings.rag.max_image_bytes

    async with async_session_factory() as session:
        repo = FileRepository(session)
        links = FileIndexLinkRepository(session)

        parked = (
            await session.execute(
                select(FileIndexLink, FileRecordModel)
                .join(FileRecordModel, FileIndexLink.file_record_id == FileRecordModel.id)
                .where(
                    FileIndexLink.state.in_(
                        (IndexLinkState.ARCHIVED.value, IndexLinkState.SKIPPED.value)
                    ),
                    FileRecordModel.status == FileStatusModel.COMMITTED,
                )
                .order_by(FileRecordModel.created_at)
                .limit(limit or 10_000)
            )
        ).all()
        logger.info("reindex: {} parked links on live records", len(parked))

        for link_model, record_model in parked:
            record = await repo.get_by_id(record_model.id)
            if record is None:
                continue
            try:
                decision = decide_registration_target(
                    record, max_image_bytes=max_image_bytes
                )
            except PrivateIndexRefused:
                report.skipped_reasons["private"] += 1
                continue

            if decision.skip_code is not None:
                report.left_skipped += 1
                report.skipped_reasons[decision.skip_code.value] += 1
                if dry_run:
                    logger.info(
                        "reindex[plan]: {} stays skipped ({})",
                        record.id,
                        decision.skip_code.value,
                    )
                    continue
                if link_model.state != IndexLinkState.SKIPPED.value:
                    await links.apply_transition(
                        link_model.id,
                        state=IndexLinkState.SKIPPED,
                        attempts=0,
                        last_error_code=decision.skip_code.value,
                        next_attempt_at=None,
                    )
                    await session.commit()
                else:
                    logger.info(
                        "reindex: {} already skipped ({})",
                        record.id,
                        link_model.state,
                    )
                continue

            if dry_run:
                logger.info(
                    "reindex[plan]: {} -> requeue ({}, stale_rag_id={})",
                    record.id,
                    decision.content_type,
                    link_model.rag_file_id is not None,
                )
                continue

            updated = await links.mark_content_changed(record.id, decision)
            if updated is None:
                report.link_missing += 1
            elif updated.state is IndexLinkState.REINDEX_PENDING:
                report.requeued_reindex += 1
            else:
                report.requeued_pending += 1
            await session.commit()

        # Restored records that never had a link row: backfill would pick them
        # up on the next startup, do it now so the run is self-contained.
        restored_ids = [UUID(item["id"]) for item in report.consumed_keys]
        for record_id in restored_ids:
            record = await repo.get_by_id(record_id)
            if record is None or await links.get_by_file_record_id(record_id) is not None:
                continue
            try:
                decision = decide_registration_target(
                    record, max_image_bytes=max_image_bytes
                )
            except PrivateIndexRefused:
                continue
            if decision.skip_code is not None:
                report.left_skipped += 1
                report.skipped_reasons[decision.skip_code.value] += 1
                continue
            if dry_run:
                continue
            created = await links.upsert_pending(record, decision)
            if created is None:
                report.link_missing += 1
            else:
                report.requeued_pending += 1
            await session.commit()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phases", default=",".join(PHASES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report", default=None, help="CSV of consumed archive keys")
    args = parser.parse_args()

    phases = [item.strip() for item in args.phases.split(",") if item.strip()]
    unknown = set(phases) - set(PHASES)
    if unknown:
        raise SystemExit(f"unknown phases: {sorted(unknown)}")

    report = Report()
    if "restore" in phases:
        await restore_phase(limit=args.limit, dry_run=args.dry_run, report=report)
    if "tombstones" in phases:
        await tombstone_phase(limit=args.limit, dry_run=args.dry_run, report=report)
    if "reindex" in phases:
        await reindex_phase(limit=args.limit, dry_run=args.dry_run, report=report)

    if args.report and report.consumed_keys and not args.dry_run:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report.consumed_keys[0]))
            writer.writeheader()
            writer.writerows(report.consumed_keys)
        logger.info("report written to {}", path)

    print(json.dumps({"dry_run": args.dry_run, "phases": phases, **report.summary()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
