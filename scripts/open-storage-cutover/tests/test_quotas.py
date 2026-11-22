from pathlib import Path

from cutover.quotas import FileByte, QuotaUsage, reconcile_quotas

REPO = Path(__file__).resolve().parents[3]
MAINTENANCE = (
    REPO
    / "src/open-storage/app/app/application/maintenance_service.py"
)


def test_reconcile_matches_committed_sections() -> None:
    files = (
        FileByte("old-user-1", "FILES", 10, "COMMITTED"),
        FileByte("old-user-1", "PHOTOS", 7, "COMMITTED"),
        FileByte("old-user-1", "PRIVATE", 5, "COMMITTED"),
        FileByte("old-user-1", "SHARED", 3, "COMMITTED"),
        FileByte("old-user-1", "FILES", 100, "PENDING"),
        FileByte("old-user-1", "PHOTOS", 50, "DELETED"),
        FileByte("old-user-2", "RESUMES", 4, "COMMITTED"),
        FileByte("old-user-2", "GENERATED", 6, "COMMITTED"),
    )
    usages = (
        QuotaUsage("old-user-1", total_bytes=1, private_bytes=0, photos_bytes=0),
        QuotaUsage("old-user-2", total_bytes=10, private_bytes=9, photos_bytes=8),
        QuotaUsage("old-user-3", total_bytes=2, private_bytes=2, photos_bytes=2),
    )

    report = reconcile_quotas(files, usages)

    by_user = {row.user_id: row for row in report.rows}
    assert by_user["old-user-1"].total_bytes == 25
    assert by_user["old-user-1"].private_bytes == 5
    assert by_user["old-user-1"].photos_bytes == 7
    assert by_user["old-user-2"].total_bytes == 10
    assert by_user["old-user-2"].private_bytes == 0
    assert by_user["old-user-2"].photos_bytes == 0
    assert by_user["old-user-3"].total_bytes == 0
    assert by_user["old-user-3"].private_bytes == 0
    assert by_user["old-user-3"].photos_bytes == 0
    assert report.fixed == 3
    assert report.consistent is False

    corrected = tuple(
        QuotaUsage(row.user_id, row.total_bytes, row.private_bytes, row.photos_bytes)
        for row in report.rows
    )
    again = reconcile_quotas(files, corrected)
    assert again.consistent is True
    assert again.fixed == 0
    assert all(row.changed is False for row in again.rows)


def test_admin_reconcile_rewrites_total_bytes_only_past_one_megabyte() -> None:
    text = MAINTENANCE.read_text(encoding="utf-8")
    assert "QUOTA_MISMATCH_THRESHOLD_BYTES = 1_000_000" in text
    start = text.index("async def reconcile_quotas")
    body = text[start : text.index("async def get_stats")]
    assert "update_total_bytes" in body
    assert "private_bytes" not in body
    assert "photos_bytes" not in body
