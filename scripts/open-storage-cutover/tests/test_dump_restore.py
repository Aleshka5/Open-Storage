import inspect

import pytest

from cutover import dump_restore
from cutover.dump_restore import plan_dump_restore, validate_dump_restore_plan
from cutover.errors import CutoverRefused


def test_plan_is_pg_dump_fc_then_restore_then_empty_upload_sessions() -> None:
    plan = plan_dump_restore(legacy_app_stopped=True, dump_path="/tmp/db_storage.dump")

    assert plan.steps[0][:4] == ("pg_dump", "-Fc", "-d", "db_storage")
    assert plan.steps[0][-2:] == ("-f", "/tmp/db_storage.dump")
    assert plan.steps[1][0] == "pg_restore"
    assert "-h" in plan.steps[1] and "open-storage-postgres" in plan.steps[1]
    assert "-d" in plan.steps[1] and "db_storage" in plan.steps[1]
    assert plan.steps[2][-1] == "TRUNCATE TABLE upload_sessions;"
    assert plan.empty_tables == ("upload_sessions",)
    assert plan.legacy_app_stopped is True


def test_legacy_app_must_be_stopped_before_the_dump() -> None:
    with pytest.raises(CutoverRefused, match="stopped"):
        plan_dump_restore(legacy_app_stopped=False, dump_path="/tmp/db_storage.dump")


def test_validator_rejects_carrying_upload_sessions_and_a_live_dump() -> None:
    plan = plan_dump_restore(legacy_app_stopped=True, dump_path="/tmp/db_storage.dump")
    live = type(plan)(
        legacy_app_stopped=False,
        dump_path=plan.dump_path,
        steps=plan.steps,
        baseline_count_sql=plan.baseline_count_sql,
        empty_tables=plan.empty_tables,
        source_database=plan.source_database,
        target_host=plan.target_host,
        target_database=plan.target_database,
    )
    with pytest.raises(CutoverRefused, match="stopped"):
        validate_dump_restore_plan(live)

    carried = plan.steps[2][:-1] + ("SELECT 1;",)
    with pytest.raises(CutoverRefused, match="not carried"):
        validate_dump_restore_plan(
            type(plan)(
                legacy_app_stopped=True,
                dump_path=plan.dump_path,
                steps=plan.steps[:2] + (carried,),
                baseline_count_sql=plan.baseline_count_sql,
                empty_tables=plan.empty_tables,
                source_database=plan.source_database,
                target_host=plan.target_host,
                target_database=plan.target_database,
            )
        )


def test_validator_rejects_a_host_directory_copy() -> None:
    plan = plan_dump_restore(legacy_app_stopped=True, dump_path="/tmp/db_storage.dump")
    copied = (("cp", "-a", "/media/aleksey/HardDisk/minio", "/tmp/minio"),) + plan.steps[1:]
    with pytest.raises(CutoverRefused):
        validate_dump_restore_plan(
            type(plan)(
                legacy_app_stopped=True,
                dump_path=plan.dump_path,
                steps=copied,
                baseline_count_sql=plan.baseline_count_sql,
                empty_tables=plan.empty_tables,
                source_database=plan.source_database,
                target_host=plan.target_host,
                target_database=plan.target_database,
            )
        )


def test_baseline_queries_name_tables_and_do_not_invent_counts() -> None:
    plan = plan_dump_restore(legacy_app_stopped=True, dump_path="/tmp/db_storage.dump")
    joined = "\n".join(plan.baseline_count_sql)
    for table in ("users", "file_records", "user_quota_usage", "file_index_links", "upload_sessions"):
        assert table in joined
    for query in plan.baseline_count_sql:
        assert not any(character.isdigit() for character in query)


def test_planner_does_not_call_subprocess() -> None:
    assert "subprocess" not in inspect.getsource(dump_restore)
    plan_dump_restore(legacy_app_stopped=True, dump_path="/tmp/db_storage.dump")
