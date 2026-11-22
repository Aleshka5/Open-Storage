"""Reconcile quota counters from committed file sizes. No HTTP call."""

from collections.abc import Sequence
from dataclasses import dataclass

from cutover.errors import CutoverRefused

SECTIONS = frozenset({"PHOTOS", "FILES", "PRIVATE", "SHARED", "RESUMES", "GENERATED"})
STATUSES = frozenset({"PENDING", "COMMITTED", "DELETED"})


@dataclass(frozen=True)
class FileByte:
    user_id: str
    section: str
    size_bytes: int
    status: str


@dataclass(frozen=True)
class QuotaUsage:
    user_id: str
    total_bytes: int
    private_bytes: int
    photos_bytes: int


@dataclass(frozen=True)
class ReconciledQuota:
    user_id: str
    total_bytes: int
    private_bytes: int
    photos_bytes: int
    changed: bool


@dataclass(frozen=True)
class QuotaReport:
    checked: int
    fixed: int
    rows: tuple[ReconciledQuota, ...]

    @property
    def consistent(self) -> bool:
        return self.fixed == 0


def reconcile_quotas(
    files: Sequence[FileByte],
    usages: Sequence[QuotaUsage],
) -> QuotaReport:
    """Set each user's counters from committed rows.

    total_bytes is the sum of committed size_bytes. private_bytes sums section
    PRIVATE. photos_bytes sums section PHOTOS. Other sections add only to
    total_bytes. PENDING and DELETED rows are ignored.
    """
    expected: dict[str, list[int]] = {}
    for item in files:
        if item.section not in SECTIONS:
            raise CutoverRefused(f"unknown section {item.section}")
        if item.status not in STATUSES:
            raise CutoverRefused(f"unknown status {item.status}")
        if item.size_bytes < 0:
            raise CutoverRefused("size_bytes is negative")
        if item.status != "COMMITTED":
            continue
        bucket = expected.setdefault(item.user_id, [0, 0, 0])
        bucket[0] += item.size_bytes
        if item.section == "PRIVATE":
            bucket[1] += item.size_bytes
        elif item.section == "PHOTOS":
            bucket[2] += item.size_bytes

    usage_by: dict[str, QuotaUsage] = {}
    for usage in usages:
        if usage.user_id in usage_by:
            raise CutoverRefused(f"duplicate quota row for {usage.user_id}")
        usage_by[usage.user_id] = usage
        expected.setdefault(usage.user_id, [0, 0, 0])

    rows: list[ReconciledQuota] = []
    fixed = 0
    for user_id in sorted(expected):
        total, private, photos = expected[user_id]
        current = usage_by.get(user_id)
        changed = (
            current is None
            or current.total_bytes != total
            or current.private_bytes != private
            or current.photos_bytes != photos
        )
        if changed:
            fixed += 1
        rows.append(
            ReconciledQuota(
                user_id=user_id,
                total_bytes=total,
                private_bytes=private,
                photos_bytes=photos,
                changed=changed,
            )
        )
    return QuotaReport(checked=len(rows), fixed=fixed, rows=tuple(rows))
