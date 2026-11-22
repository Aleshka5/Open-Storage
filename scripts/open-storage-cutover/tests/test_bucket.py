import pytest

from cutover.bucket import (
    REQUIRED_PREFIXES,
    ObjectEntry,
    compare_listings,
    missing_required_prefixes,
    plan_mirror,
)
from cutover.errors import CutoverRefused


def test_mirror_plan_preserves_between_endpoints() -> None:
    plan = plan_mirror(
        source_endpoint="http://minio:9000",
        target_endpoint="http://open-storage-minio:9000",
    )

    assert plan.command[:3] == ("mc", "mirror", "--preserve")
    assert plan.command[3:] == ("legacy/storage", "namespace/storage")
    assert "cp" not in plan.command
    assert plan.summarize_commands[0][:4] == ("mc", "ls", "--recursive", "--summarize")
    assert plan.summarize_commands[0][-1] == "legacy/storage"
    assert plan.summarize_commands[1][-1] == "namespace/storage"
    assert plan.required_prefixes == REQUIRED_PREFIXES


def test_host_directory_is_refused() -> None:
    with pytest.raises(CutoverRefused, match="host-directory"):
        plan_mirror(
            source_endpoint="/media/aleksey/HardDisk/minio/storage",
            target_endpoint="http://open-storage-minio:9000",
        )


def test_compare_listings_uses_count_and_total_bytes() -> None:
    source = (
        ObjectEntry("users/old-user-1/files/a", 10),
        ObjectEntry("shared/note", 5),
        ObjectEntry("files/root", 7),
        ObjectEntry("_meta/backups/db_backup_fixture.sql.zst", 3),
    )
    same = (
        ObjectEntry("_meta/backups/db_backup_fixture.sql.zst", 3),
        ObjectEntry("files/root", 7),
        ObjectEntry("shared/note", 5),
        ObjectEntry("users/old-user-1/files/a", 10),
    )
    shorter = source[:-1]
    lighter = (
        ObjectEntry("users/old-user-1/files/a", 9),
        ObjectEntry("shared/note", 5),
        ObjectEntry("files/root", 7),
        ObjectEntry("_meta/backups/db_backup_fixture.sql.zst", 3),
    )

    match = compare_listings(source, same)
    assert match.matches is True
    assert match.source.object_count == 4
    assert match.source.total_bytes == 25

    count_gap = compare_listings(source, shorter)
    assert count_gap.matches is False
    assert count_gap.source.object_count != count_gap.target.object_count

    byte_gap = compare_listings(source, lighter)
    assert byte_gap.matches is False
    assert byte_gap.source.object_count == byte_gap.target.object_count
    assert byte_gap.source.total_bytes != byte_gap.target.total_bytes


def test_required_prefixes() -> None:
    keys = (
        "users/old-user-1/files/a",
        "shared/note",
        "files/root",
        "_meta/backups/db_backup_fixture.sql.zst",
    )
    assert missing_required_prefixes(keys) == ()
    assert missing_required_prefixes(("users/only",)) == ("shared/", "files/", "_meta/")
