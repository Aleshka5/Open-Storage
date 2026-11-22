"""Bucket copy plan. mc mirror between endpoints; listings are compared in memory."""

from collections.abc import Sequence
from dataclasses import dataclass

from cutover.errors import CutoverRefused

BUCKET = "storage"
REQUIRED_PREFIXES: tuple[str, ...] = ("users/", "shared/", "files/", "_meta/")
_HOST_MARKERS = ("/media/", "HardDisk/minio", "xl.meta")


@dataclass(frozen=True)
class ObjectEntry:
    key: str
    size_bytes: int


@dataclass(frozen=True)
class ListingSummary:
    object_count: int
    total_bytes: int


@dataclass(frozen=True)
class SummaryComparison:
    source: ListingSummary
    target: ListingSummary

    @property
    def matches(self) -> bool:
        return self.source == self.target


@dataclass(frozen=True)
class MirrorPlan:
    command: tuple[str, ...]
    summarize_commands: tuple[tuple[str, ...], ...]
    source_endpoint: str
    target_endpoint: str
    bucket: str
    required_prefixes: tuple[str, ...]


def plan_mirror(*, source_endpoint: str, target_endpoint: str, bucket: str = BUCKET) -> MirrorPlan:
    """Plan `mc mirror --preserve` from one endpoint alias to the other.

    A host path is refused. This function does not run mc.
    """
    _require_endpoint(source_endpoint)
    _require_endpoint(target_endpoint)
    if bucket != BUCKET:
        raise CutoverRefused("bucket copy is the storage bucket")
    source_alias = f"legacy/{bucket}"
    target_alias = f"namespace/{bucket}"
    command = ("mc", "mirror", "--preserve", source_alias, target_alias)
    _reject_host_copy(command)
    summarize = tuple(
        ("mc", "ls", "--recursive", "--summarize", alias)
        for alias in (source_alias, target_alias)
    )
    return MirrorPlan(
        command=command,
        summarize_commands=summarize,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        bucket=bucket,
        required_prefixes=REQUIRED_PREFIXES,
    )


def summarize_listing(objects: Sequence[ObjectEntry]) -> ListingSummary:
    total = 0
    for item in objects:
        if item.size_bytes < 0:
            raise CutoverRefused("object size is negative")
        total += item.size_bytes
    return ListingSummary(object_count=len(objects), total_bytes=total)


def compare_listings(
    source: Sequence[ObjectEntry],
    target: Sequence[ObjectEntry],
) -> SummaryComparison:
    """Compare object count and total bytes. Key order does not matter."""
    return SummaryComparison(
        source=summarize_listing(source),
        target=summarize_listing(target),
    )


def missing_required_prefixes(keys: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        prefix for prefix in REQUIRED_PREFIXES if not any(key.startswith(prefix) for key in keys)
    )


def _require_endpoint(url: str) -> None:
    if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
        raise CutoverRefused(
            "bucket copy is mc mirror between endpoints, never a host-directory cp"
        )
    for marker in _HOST_MARKERS:
        if marker in url:
            raise CutoverRefused("bucket copy does not read the MinIO host directory")


def _reject_host_copy(command: Sequence[str]) -> None:
    if command[:3] != ("mc", "mirror", "--preserve"):
        raise CutoverRefused("bucket copy is mc mirror --preserve")
    for part in command:
        if part.split("/", 1)[0] in {"cp", "rsync"} or part.startswith("/"):
            raise CutoverRefused("bucket copy is not a host-directory cp")
        for marker in _HOST_MARKERS:
            if marker in part:
                raise CutoverRefused("bucket copy does not carry xl.meta by hand")
