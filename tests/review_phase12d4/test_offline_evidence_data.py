"""Phase 12D4 re-review: REGRESSION tests for the offline update tool (data-preservation checks and backup validity).

Written by a fresh-context sub-reviewer of this session (it was given the code
of scripts/offline/offline_package.py, not the Phase 12D3 conclusions), then
re-run and read by the main reviewer. Each test first REPRODUCED a defect (it
asserted the unsafe outcome and passed while the defect existed). Phase 12D5
fixed the defects; every test is now INVERTED into a regression test: same
scenario, it asserts the SAFE outcome, and a `# was:` comment names the former
reproduction. Findings: docs/review/PHASE12D4_NEW_FINDINGS.json.

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
ZERO = {"source": 0, "notebook": 0, "note": 0, "source_embedding": 0, "source_insight": 0}
ONE = {"source": 1, "notebook": 1, "note": 1, "source_embedding": 1, "source_insight": 1}


# was: test_loss_between_update_and_finish_is_not_detected (PHASE12D4 evidence, R2-05)
def test_loss_between_update_and_finish_stops_the_finish(deployment, fake_docker, tmp_path):
    """update -> awaiting approval; then the DB container is replaced by another one with
    another volume and all tables are empty; finish must NOT report completed."""
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
    ups = len(T._ups(fake_docker))
    rc = T._finish(conf)
    j = T._journal(tmp_path)
    print("PROOF ", "finish rc", rc, "status", j["status"], "baseline counts", j["baseline"]["counts"],
          "db_changed", j.get("db_changed"), "data_changed", j.get("data_changed"))
    assert rc != 0 and j["status"] != OP.COMPLETED
    assert j["db_changed"] is True and j["data_changed"] is True
    assert len(T._ups(fake_docker)) == ups  # nothing was recreated
    assert fake_docker.get()["images"][T.DEPLOY_TAG] == T.OLD_ID  # nothing was approved
    assert T._status(conf) == OP.EXIT_DRIFT  # and it is reported
    assert T._finish(conf) != 0  # sticky: a second finish does not complete either


# was: test_partial_loss_during_the_finish_recreate_is_not_detected (PHASE12D4 evidence, R2-05)
def test_partial_loss_during_the_finish_recreate_fails_the_finish(deployment, fake_docker, tmp_path):
    """The finish recreate itself loses 99 % of the rows: a FAIL, not 'informational'."""
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    fake_docker.set(on_up={"counts": ONE})
    rc = T._finish(conf)
    j = T._journal(tmp_path)
    print("PROOF ", "finish rc", rc, j["status"], "before", j["reference"]["counts"], "after", fake_docker.get()["counts"])
    assert rc == OP.EXIT_UPDATE and j["status"] == OP.FINISH_FAILED and j["data_changed"] is True
    assert fake_docker.get()["images"][T.DEPLOY_TAG] == T.OLD_ID  # the tag went back


# was: test_partial_loss_during_update_no_maintenance_is_not_detected (PHASE12D4 evidence, R2-05)
def test_partial_loss_during_update_no_maintenance_fails_the_update(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    fake_docker.set(on_up={"counts": ONE})
    # --no-maintenance is refused unless the operator attests that writes are stopped (R2-20a)
    assert T._apply(conf, pkg_dir, "--no-maintenance") == OP.EXIT_PREFLIGHT
    rc = T._apply(conf, pkg_dir, "--no-maintenance", "--writes-stopped-confirmed")
    j = T._journal(tmp_path)
    print("PROOF ", "update rc", rc, j["status"])
    assert rc == OP.EXIT_UPDATE and j["status"] == OP.FAILED and j["data_changed"] is True


# was: test_unreadable_row_counts_skip_the_check (PHASE12D4 evidence, R2-05)
def test_unreadable_data_refuses_to_start_the_update(deployment, fake_docker, tmp_path):
    """When the records cannot be read BEFORE anything changes (query error), the update
    does not start: 'database unreadable' is a FAIL, never 'nothing to compare'."""
    conf, pkg_dir, _ = deployment
    # records unreadable in the OLD container only (e.g. old image lacks the helper / DB error)
    fake_docker.set(fail_on_image={T.OLD_ID: ["TABLES ="]}, on_up={"counts": ZERO})
    rc = T._apply(conf, pkg_dir)
    print("PROOF ", "update rc", rc)
    assert rc == OP.EXIT_PREFLIGHT
    assert not (tmp_path / "state" / "journal.json").exists()  # no attempt was started
    assert not [c for c in fake_docker.calls() if c[0] == "load"] and not T._ups(fake_docker)
    assert OP.data_verdict({"source": ["source:1"]}, None)[0] is False
    assert T._finish(conf) == OP.EXIT_UPDATE


# was: test_db_change_reported_at_finish_is_forgotten_by_a_second_finish (PHASE12D4 evidence, R2-05)
def test_db_change_reported_at_finish_blocks_a_second_finish(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    fake_docker.set(up_recreates_db=True)  # the finish recreate replaces the DB container
    assert T._finish(conf) == OP.EXIT_UPDATE
    j = T._journal(tmp_path)
    assert j["db_changed"] is True and j["status"] == OP.FINISH_FAILED
    fake_docker.set(up_recreates_db=False)
    rc = T._finish(conf)  # no acknowledgement, no investigation
    j = T._journal(tmp_path)
    print("PROOF ", "second finish rc", rc, j["status"], "db_changed", j.get("db_changed"),
          "db", fake_docker.get()["containers"]["db1"]["id"])
    assert rc == OP.EXIT_UPDATE and j["status"] != OP.COMPLETED and j["db_changed"] is True
    assert T._status(conf) == OP.EXIT_DRIFT
    # after the investigation: an explicit, recorded decision (nothing is restored)
    assert OP.main(["finish", "--config", str(conf), "--approve", "owner",
                    "--acknowledge-data-change"]) == 0
    j = T._journal(tmp_path)
    assert j["status"] == OP.COMPLETED and j["acknowledged"]["by"] == "owner"
    assert j["acknowledged"]["flags"]["db_changed"] is True


# was: test_resume_reuses_a_backup_that_predates_new_user_data (PHASE12D4 evidence, R2-04)
def test_resume_takes_a_new_backup_of_the_data_as_it_is_now(deployment, fake_docker, tmp_path):
    """Run 1 takes the backup and stops (RapidOCR). The data changes. Run 2 (same attempt)
    takes its OWN backup and binds it to the data it recreates over."""
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
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"  # writes stopped (was: public)
    fake_docker.edit(lambda s: s["counts"].update(source=500, note=300))
    assert T._server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    j = T._journal(tmp_path)
    print("PROOF ", "backups:", marker.read_text().strip(), "| rows at recreate:", j["reference"]["counts"]["source"],
          "| baseline rows:", j["baseline"]["counts"]["source"], "| steps", [s["step"] for s in j["steps"]])
    assert marker.read_text().strip().splitlines() == ["backup 120", "backup 500"]
    assert j["reference"]["counts"]["source"] == 500 and j["status"] == OP.AWAITING
    f1 = [s for s in j["steps"] if s["step"] == "F1_fingerprint"][-1]
    f3 = [s for s in j["steps"] if s["step"] == "F3_fingerprint"][-1]
    assert j["backup"]["fingerprint_sha256"] == f1["sha256"] == f3["sha256"]
    assert f1["counts"]["source"] == 500


# was: test_same_backup_reference_is_accepted_for_two_attempts (PHASE12D4 evidence, R2-04)
def test_same_backup_reference_is_refused_for_a_second_attempt(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._server("update", conf, pkg_dir, "--apply", "--backup-reference", "bk", "--backup-verified") == 0
    first = T._journal(tmp_path)
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    fake_docker.edit(lambda s: s["counts"].update(source=999))
    loads = sum(1 for c in fake_docker.calls() if c[0] == "load")
    rc = T._server("update", conf, pkg_dir, "--apply", "--backup-reference", "bk", "--backup-verified")  # days later
    registry = json.loads((tmp_path / "state" / "backup-references.json").read_text())
    print("PROOF ", "second update rc", rc, "registry", registry)
    assert rc != 0 and sum(1 for c in fake_docker.calls() if c[0] == "load") == loads
    assert T._journal(tmp_path)["attempt_id"] == first["attempt_id"]  # no new attempt
    assert [e["reference"] for e in registry] == ["bk"]
    assert registry[0]["attempt_id"] == first["attempt_id"]
    assert registry[0]["fingerprint_sha256"] == first["backup"]["fingerprint_sha256"]


# was: test_backup_from_the_future_is_always_fresh (PHASE12D4 evidence, R2-04)
def test_backup_age_is_no_longer_a_criterion(deployment, fake_docker, tmp_path):
    """The time-to-live is gone: no backup is ever reused, a step dated in the future
    changes nothing, and the obsolete key (even `inf`) is accepted and ignored."""
    conf, pkg_dir, _ = deployment
    assert not hasattr(OP, "backup_is_fresh")
    T._set_conf(conf, BACKUP_MAX_AGE_MINUTES="inf")
    OP.load_config(str(conf))  # no OverflowError, no crash
    marker = T._with_backup_cmd(conf, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert T._server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    path = tmp_path / "state" / "journal.json"
    j = json.loads(path.read_text())
    for s in j["steps"]:
        if s["step"] in ("I_backup", "J_backup_verified"):
            s["at"] = "2099-01-01T00:00:00"  # clock set back / DST
    path.write_text(json.dumps(j))
    (tmp_path / "state" / "journal.json.bak").write_text(json.dumps(j))
    assert T._server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    print("PROOF ", "backups", T._backups(marker))
    assert T._backups(marker) == 2


# was: test_data_written_while_the_backup_is_verified_is_in_no_backup (PHASE12D4 evidence, R2-04)
def test_data_written_while_the_backup_is_verified_stops_the_update(deployment, fake_docker, tmp_path):
    """Single uninterrupted run. Something writes during BACKUP_VERIFY_CMD (restore test):
    the fingerprint after the backup differs from the one before -> no recreate."""
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
    rc = T._server("update", conf, pkg_dir, "--apply")
    j = T._journal(tmp_path)
    print("PROOF ", marker.read_text().strip(), "| status", j["status"], "| rc", rc)
    assert rc == OP.EXIT_UPDATE and marker.read_text().strip() == "backup 120"
    assert not T._update_ups(fake_docker) and fake_docker.app()["image_id"] == T.OLD_ID
    assert "F2_fingerprint" not in [s["step"] for s in j["steps"]]


# was: test_rollback_of_a_broken_version_skips_the_data_check (PHASE12D4 evidence, R2-05)
def test_rollback_of_a_broken_version_checks_the_data_with_the_old_image(deployment, fake_docker, tmp_path):
    """The new version cannot query the database (the usual reason to roll back). Its
    'before' fingerprint is unreadable (expected); after the rollback recreate the OLD
    image must read the data, and it sees EMPTY tables -> the rollback is NOT confirmed."""
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail_on_image={T.IMAGE_ID: ["TABLES =", "get_latest_version"]})
    assert T._apply(conf, pkg_dir) == OP.EXIT_UPDATE and T._journal(tmp_path)["status"] == OP.FAILED
    fake_docker.set(on_up={"counts": ZERO})
    rc = T._rollback(conf)
    j = T._journal(tmp_path)
    print("PROOF  rollback rc", rc, j["status"], "| baseline", j["baseline"]["counts"], "| now", fake_docker.get()["counts"])
    assert rc == OP.EXIT_UPDATE and j["status"] == OP.ROLLBACK_FAILED and j["data_changed"] is True
    assert T._status(conf) == OP.EXIT_DRIFT
