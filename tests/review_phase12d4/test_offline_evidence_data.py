"""Phase 12D4 re-review: REPRODUCTION tests for the offline update tool (data-preservation checks and backup validity).

Written by a fresh-context sub-reviewer of this session (it was given the code
of scripts/offline/offline_package.py, not the Phase 12D3 conclusions), then
re-run and read by the main reviewer. Convention of THIS file: every test
REPRODUCES a defect - it asserts the unsafe outcome and therefore PASSES while
the defect exists. When a later phase fixes a defect its test fails and must be
inverted into a regression test. Findings: docs/review/PHASE12D4_NEW_FINDINGS.json.

``docker`` is the stateful fake of tests/test_offline_package.py (no Docker
daemon in Cloud); git, tar and SHA-256 are real.
"""

# ruff: noqa

import json
import sys

import test_offline_package as T
from test_offline_package import (  # noqa: F401
    completed, deployment, fake_docker, git_deployment, health_server, package, repo,
)

OP = T.OP


def test_loss_between_update_and_finish_is_not_detected(deployment, fake_docker, tmp_path):
    """update -> awaiting approval; then the DB container is replaced by another one with
    another volume and all tables are empty; finish still reports COMPLETED."""
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    assert T._journal(tmp_path)["status"] == OP.AWAITING

    def wipe(s):
        s["counts"] = {k: 0 for k in s["counts"]}
        s["containers"]["db1"].update(
            id="db-container-ANOTHER",
            started_at="2026-11-19T00:00:00Z",
            mounts=[{"Type": "volume", "Name": "brand_new_empty_volume", "Destination": "/mydata"}],
        )

    fake_docker.edit(wipe)
    rc = T._finish(conf)
    j = T._journal(tmp_path)
    print("PROOF ", "finish rc", rc, "status", j["status"], "baseline counts", j["baseline"]["counts"],
          "reference counts", j["reference"]["counts"], "baseline db", j["baseline"]["db"]["container_id"],
          "now", j["reference"]["db"]["container_id"])
    assert rc == 0 and j["status"] == OP.COMPLETED
    assert T._status(conf) == 0  # and no drift is reported either


def test_partial_loss_during_the_finish_recreate_is_not_detected(deployment, fake_docker, tmp_path):
    """The finish recreate itself loses 99 % of the rows: 'informational' only."""
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    fake_docker.set(on_up={"counts": {"source": 1, "notebook": 1, "note": 1, "source_embedding": 1, "source_insight": 1}})
    rc = T._finish(conf)
    j = T._journal(tmp_path)
    print("PROOF ", "finish rc", rc, j["status"], "before", j["reference"]["counts"], "after", fake_docker.get()["counts"])
    assert rc == 0 and j["status"] == OP.COMPLETED


def test_partial_loss_during_update_no_maintenance_is_not_detected(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    fake_docker.set(on_up={"counts": {"source": 1, "notebook": 1, "note": 1, "source_embedding": 1, "source_insight": 1}})
    rc = T._apply(conf, pkg_dir, "--no-maintenance")
    j = T._journal(tmp_path)
    print("PROOF ", "update rc", rc, j["status"])
    assert rc == 0 and j["status"] == OP.AWAITING


def test_unreadable_row_counts_skip_the_check(deployment, fake_docker, tmp_path):
    """When the row counts cannot be read BEFORE the recreate (query error), the update
    goes on and the comparison is silently skipped, even if every table is empty after."""
    conf, pkg_dir, _ = deployment
    # counts unreadable in the OLD container only (e.g. old image lacks the helper / DB error)
    fake_docker.set(
        fail_on_image={T.OLD_ID: ["TABLES ="]},
        on_up={"counts": {"source": 0, "notebook": 0, "note": 0, "source_embedding": 0, "source_insight": 0}},
    )
    rc = T._apply(conf, pkg_dir)
    j = T._journal(tmp_path)
    print("PROOF ", "update rc", rc, j["status"], "baseline counts", j["baseline"]["counts"], "reference", j["reference"]["counts"])
    assert j["baseline"]["counts"] is None and j["reference"]["counts"] is None
    assert rc == 0 and j["status"] == OP.AWAITING
    assert T._finish(conf) == 0 and T._journal(tmp_path)["status"] == OP.COMPLETED


def test_db_change_reported_at_finish_is_forgotten_by_a_second_finish(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    fake_docker.set(up_recreates_db=True)  # the finish recreate replaces the DB container
    assert T._finish(conf) == OP.EXIT_UPDATE
    j = T._journal(tmp_path)
    assert j["db_changed"] is True and j["status"] == OP.AWAITING
    fake_docker.set(up_recreates_db=False)
    rc = T._finish(conf)  # no acknowledgement, no investigation
    j = T._journal(tmp_path)
    print("PROOF ", "second finish rc", rc, j["status"], "db_changed", j.get("db_changed"),
          "db", fake_docker.get()["containers"]["db1"]["id"])
    assert rc == 0 and j["status"] == OP.COMPLETED and j["db_changed"] is True
    assert T._status(conf) == 0


def test_resume_reuses_a_backup_that_predates_new_user_data(deployment, fake_docker, tmp_path):
    """Run 1 takes the backup and stops (RapidOCR). The application is NOT in maintenance:
    users keep writing. Run 2 (same attempt, < BACKUP_MAX_AGE_MINUTES) recreates the
    application with the stale backup as its only backup."""
    conf, pkg_dir, _ = deployment
    marker = tmp_path / "backups.log"
    counts_file = tmp_path / "docker_state.json"
    # the backup command records the row count of `source` at backup time
    T._set_conf(
        conf,
        BACKUP_CMD=f"{sys.executable} -c \"import json;print('backup', json.load(open('{counts_file}'))['counts']['source'])\" >> {marker}",
        BACKUP_VERIFY_CMD="true",
    )
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={"det.onnx": "skipped (checksum mismatch)"}, on_volume=[]))
    assert T._server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"  # still public
    fake_docker.edit(lambda s: s["counts"].update(source=500, note=300))  # users work for an hour
    assert T._server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    j = T._journal(tmp_path)
    print("PROOF ", "backups:", marker.read_text().strip(), "| rows at recreate:", j["reference"]["counts"]["source"],
          "| baseline rows:", j["baseline"]["counts"]["source"], "| steps", [s["step"] for s in j["steps"]])
    assert marker.read_text().strip() == "backup 120"
    assert j["reference"]["counts"]["source"] == 500 and j["status"] == OP.AWAITING


def test_same_backup_reference_is_accepted_for_two_attempts(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0  # --backup-reference bk --backup-verified
    first = T._journal(tmp_path)
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    fake_docker.edit(lambda s: s["counts"].update(source=999))
    assert T._apply(conf, pkg_dir) == 0  # same reference "bk", days later
    second = T._journal(tmp_path)
    refs = [OP.Journal.last.__get__(type("J", (), {"data": j})())("I_backup")["reference"] for j in (first, second)]
    print("PROOF ", "attempts", first["attempt_id"], second["attempt_id"], "references", refs)
    assert first["attempt_id"] != second["attempt_id"] and refs == ["bk", "bk"]


def test_backup_from_the_future_is_always_fresh(deployment, tmp_path):
    conf, _, _ = deployment
    cfg = OP.load_config(str(conf))
    OP.ensure_state_dir(tmp_path / "state")
    j = OP.Journal(tmp_path / "state")
    j.data = {"steps": [{"step": "I_backup", "at": "2026-01-01T00:00:00"},
                        {"step": "J_backup_verified", "at": "2099-01-01T00:00:00"}]}
    assert OP.backup_is_fresh(j, cfg) is True  # negative age (clock set back / DST) = fresh
    cfg["BACKUP_MAX_AGE_MINUTES"] = "inf"
    try:
        OP.backup_is_fresh(j, cfg)
    except OverflowError as e:
        print("PROOF ", "PROOF ", "uncaught:", type(e).__name__, e)
    else:
        raise AssertionError("no crash")


def test_data_written_while_the_backup_is_verified_is_in_no_backup(deployment, fake_docker, tmp_path):
    """Single uninterrupted run. The backup is taken while the application is public;
    users keep writing during BACKUP_VERIFY_CMD (restore test, timeout 6 h). The tool
    never compares the data at backup time with the data at the recreate."""
    conf, pkg_dir, _ = deployment
    marker = tmp_path / "backups.log"
    st = tmp_path / "docker_state.json"
    T._set_conf(
        conf,
        BACKUP_CMD=f"{sys.executable} -c \"import json;print('backup', json.load(open('{st}'))['counts']['source'])\" >> {marker}",
        BACKUP_VERIFY_CMD=f"{sys.executable} {tmp_path / 'users_write.py'}",
    )
    (tmp_path / "users_write.py").write_text(
        f"import json\ns=json.load(open('{st}'))\ns['counts']['source']=777\njson.dump(s,open('{st}','w'))\n"
    )
    assert T._server("update", conf, pkg_dir, "--apply") == 0
    j = T._journal(tmp_path)
    print("PROOF ", marker.read_text().strip(), "| rows at the recreate:", j["reference"]["counts"]["source"], "| status", j["status"])
    assert marker.read_text().strip() == "backup 120" and j["reference"]["counts"]["source"] == 777


def test_rollback_of_a_broken_version_skips_the_data_check(deployment, fake_docker, tmp_path):
    """The new version cannot query the database (the usual reason to roll back). The
    rollback reads its 'before' counts through that broken container, gets nothing, and
    silently skips the comparison: the old image then sees EMPTY tables and the rollback
    is reported as done and checked. The attempt's own baseline (120 sources) is not used."""
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail_on_image={T.IMAGE_ID: ["TABLES =", "get_latest_version"]})
    assert T._apply(conf, pkg_dir) == OP.EXIT_UPDATE and T._journal(tmp_path)["status"] == OP.FAILED
    fake_docker.set(on_up={"counts": {"source": 0, "notebook": 0, "note": 0, "source_embedding": 0, "source_insight": 0}})
    rc = T._rollback(conf)
    j = T._journal(tmp_path)
    print("PROOF  rollback rc", rc, j["status"], "| baseline", j["baseline"]["counts"], "| reference", j["reference"]["counts"],
          "| now", fake_docker.get()["counts"])
    assert rc == 0 and j["status"] == OP.ROLLED_BACK and T._status(conf) == 0
