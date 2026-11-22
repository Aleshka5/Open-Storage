"""Compare committed file_records with bucket objects. Both lists are fixtures."""

from collections.abc import Sequence
from dataclasses import dataclass

from cutover.errors import CutoverRefused


@dataclass(frozen=True)
class CommittedRow:
    """One COMMITTED file_records row. `key` is relative_path."""

    key: str
    size_bytes: int


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int


@dataclass(frozen=True)
class SizeMismatch:
    key: str
    size_bytes: int
    object_size: int


@dataclass(frozen=True)
class VerifyReport:
    committed_count: int
    object_count: int
    missing_objects: tuple[str, ...]
    extra_objects: tuple[str, ...]
    size_mismatches: tuple[SizeMismatch, ...]

    @property
    def passed(self) -> bool:
        return (
            self.committed_count == self.object_count
            and not self.missing_objects
            and not self.extra_objects
            and not self.size_mismatches
        )


def verify_committed(
    rows: Sequence[CommittedRow],
    objects: Sequence[StoredObject],
) -> VerifyReport:
    """Report missing objects, extra objects, and size mismatches.

    Zero of each, and equal counts, is the pass condition. The caller passes
    only COMMITTED rows. This function does not call mc.
    """
    by_row = _index(rows, "file_records")
    by_object = _index(objects, "object")
    missing = tuple(sorted(set(by_row) - set(by_object)))
    extra = tuple(sorted(set(by_object) - set(by_row)))
    mismatches: list[SizeMismatch] = []
    for key in sorted(set(by_row) & set(by_object)):
        row = by_row[key]
        obj = by_object[key]
        if row.size_bytes != obj.size_bytes:
            mismatches.append(
                SizeMismatch(
                    key=key,
                    size_bytes=row.size_bytes,
                    object_size=obj.size_bytes,
                )
            )
    return VerifyReport(
        committed_count=len(rows),
        object_count=len(objects),
        missing_objects=missing,
        extra_objects=extra,
        size_mismatches=tuple(mismatches),
    )


def _index(items: Sequence[CommittedRow] | Sequence[StoredObject], label: str) -> dict[str, object]:
    found: dict[str, object] = {}
    for item in items:
        if item.size_bytes < 0:
            raise CutoverRefused(f"negative size for {label} {item.key}")
        if item.key in found:
            raise CutoverRefused(f"duplicate {label} key {item.key}")
        found[item.key] = item
    return found
