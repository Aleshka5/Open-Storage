from cutover.verify_objects import CommittedRow, StoredObject, verify_committed


def test_zero_mismatches_passes() -> None:
    rows = (
        CommittedRow("users/old-user-1/files/a", 10),
        CommittedRow("users/old-user-1/photos/originals/b.jpg", 20),
    )
    objects = (
        StoredObject("users/old-user-1/photos/originals/b.jpg", 20),
        StoredObject("users/old-user-1/files/a", 10),
    )

    report = verify_committed(rows, objects)

    assert report.passed is True
    assert report.missing_objects == ()
    assert report.extra_objects == ()
    assert report.size_mismatches == ()
    assert report.committed_count == report.object_count == 2


def test_missing_extra_and_size_are_reported() -> None:
    rows = (
        CommittedRow("users/old-user-1/files/kept", 10),
        CommittedRow("users/old-user-1/files/missing", 4),
        CommittedRow("users/old-user-1/files/wrong-size", 8),
    )
    objects = (
        StoredObject("users/old-user-1/files/kept", 10),
        StoredObject("users/old-user-1/files/wrong-size", 9),
        StoredObject("users/old-user-1/files/extra", 1),
    )

    report = verify_committed(rows, objects)

    assert report.passed is False
    assert report.missing_objects == ("users/old-user-1/files/missing",)
    assert report.extra_objects == ("users/old-user-1/files/extra",)
    assert len(report.size_mismatches) == 1
    mismatch = report.size_mismatches[0]
    assert mismatch.key == "users/old-user-1/files/wrong-size"
    assert mismatch.size_bytes == 8
    assert mismatch.object_size == 9
    assert report.committed_count == 3
    assert report.object_count == 3
