import json
from pathlib import Path

import pytest

from cutover.cli import main, run
from cutover.errors import CutoverRefused


def test_run_refuses_live_actions() -> None:
    for action in ("pg_dump", "pg_restore", "mc", "dns", "decommission", "volume-rm"):
        with pytest.raises(CutoverRefused, match="refuses to run"):
            run(action)


def test_plan_dump_cli_prints_commands_only_when_stopped(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plan-dump", "--dump-path", "/tmp/db_storage.dump"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stopped" in captured.err

    assert (
        main(["plan-dump", "--legacy-stopped", "--dump-path", "/tmp/db_storage.dump"]) == 0
    )
    stdout = capsys.readouterr().out
    assert "pg_dump -Fc -d db_storage -f /tmp/db_storage.dump" in stdout
    assert "pg_restore" in stdout
    assert "open-storage-postgres" in stdout
    assert "TRUNCATE TABLE upload_sessions;" in stdout


def test_plan_mirror_cli_refuses_a_directory(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "plan-mirror",
                "--source-endpoint",
                "/media/aleksey/HardDisk/minio",
                "--target-endpoint",
                "http://open-storage-minio:9000",
            ]
        )
        == 2
    )
    assert capsys.readouterr().out == ""


def test_plan_subjects_and_requeue_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mapping = tmp_path / "subjects.json"
    mapping.write_text(
        json.dumps({"old-user-1": "subject-1"}),
        encoding="utf-8",
    )
    assert (
        main(["plan-subjects", "--mapping", str(mapping), "--user-id", "old-user-1"]) == 0
    )
    sql = capsys.readouterr().out
    assert "UPDATE users SET id" in sql
    assert "INSERT INTO users" not in sql

    assert main(["plan-requeue", "--enable-rag"]) == 2
    assert "RAG_ENABLED=true" not in capsys.readouterr().out

    assert main(["plan-requeue"]) == 0
    stdout = capsys.readouterr().out
    assert "RAG_ENABLED=false" in stdout
    assert "SET state = 'PENDING'" in stdout
    assert "rag_file_id" not in stdout
