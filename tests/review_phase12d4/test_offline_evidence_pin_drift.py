"""Phase 12D4 re-review: REPRODUCTION tests for the offline update tool (pin / drift / legal gate / resume).

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
import subprocess
import sys
from pathlib import Path

import pytest

import test_offline_package as T
from test_offline_package import (  # noqa: F401
    completed, deployment, fake_docker, git_deployment, health_server, package, repo,
)

OP = T.OP
PIN = lambda conf, *a: OP.main(["pin", "--config", str(conf), *a])  # noqa: E731


def test_pin_twice_then_undo_leaves_the_name_on_the_new_image(completed, fake_docker, tmp_path):
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    assert PIN(conf, "--apply") == 0  # e.g. re-run after editing APP_ENV_OVERRIDES
    j = T._journal(tmp_path)
    print("PROOF previous_target after 2nd pin:", j["pin"]["previous_target"][:19], "new image:", T.IMAGE_ID[:19])
    assert j["pin"]["previous_target"] == T.IMAGE_ID
    assert PIN(conf, "--undo") == 0  # "undone"
    # the tool's own first pin file was taken as "the operator's file" and restored
    assert (deploy / OP.PIN_FILE).exists() and "OCR_OFFLINE" in (deploy / OP.PIN_FILE).read_text()
    assert T._journal(tmp_path)["pin"]["applied"] is False
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID  # NOT undone
    # rollback: reported successful, but the deployment's own image name keeps the NEW image
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID
    T._plain_compose_up(deploy)  # reboot script / operator
    print("PROOF after rollback + plain compose up the app runs", fake_docker.app()["image_id"][:19], "(new image)")
    assert fake_docker.app()["image_id"] == T.IMAGE_ID


def test_pin_killed_after_docker_tag_cannot_be_undone(completed, fake_docker, tmp_path, monkeypatch):
    conf, _, deploy = completed
    real = OP.atomic_write

    def dying(path, text, private=False):
        if Path(path).name == OP.PIN_FILE:
            raise KeyboardInterrupt  # kill -9 / power loss right after `docker tag`
        return real(path, text, private)

    monkeypatch.setattr(OP, "atomic_write", dying)
    with pytest.raises(KeyboardInterrupt):
        PIN(conf, "--apply")
    monkeypatch.setattr(OP, "atomic_write", real)
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID  # the name was moved
    assert T._journal(tmp_path)["pin"]["applied"] is False
    assert PIN(conf, "--undo") == 0  # "no pin recorded: nothing to undo"
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    print("PROOF rolled back, deployment name still ->", fake_docker.get()["images"]["chatbot5400:local"][:19])
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID


def _next_package(fake_docker, repo, tmp_path):
    (repo / "VERSION").write_text("1.3.1\n")
    T._git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = T._build(repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2")
    return T._unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")


def test_pin_of_first_update_is_stale_after_the_second_and_cannot_be_renewed(
    completed, fake_docker, repo, tmp_path, capsys
):
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    assert T._apply(conf, pkg_dir2) == 0 and T._finish(conf) == 0
    assert fake_docker.app()["image_id"] == T.NEXT_ID
    capsys.readouterr()
    rc = PIN(conf, "--apply")
    out = capsys.readouterr().out
    print("PROOF pin after 2nd update rc", rc, [l for l in out.splitlines() if "REFUSED" in l])
    assert rc == OP.EXIT_UPDATE and "cannot pin automatically" in out
    # status is clean and says nothing about the stale pin...
    assert T._status(conf) == 0
    assert "pin" not in T._journal(tmp_path)
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID  # previous version
    # ...and the "pinned" plain command (with the pin file in COMPOSE_FILE) downgrades
    T._plain_compose_up(deploy, "docker-compose.yml", OP.PIN_FILE)
    print("PROOF plain compose up with the pin file runs", fake_docker.app()["image_id"][:19], "= 1.3.0, expected 1.3.1")
    assert fake_docker.app()["image_id"] == T.IMAGE_ID


def test_no_drift_report_while_a_later_attempt_is_unfinished(completed, fake_docker, repo, tmp_path, capsys):
    """v1.3.0 completed. The next update stops at the backup step (status in_progress).
    A plain `docker compose up -d` then brings v1.2.0 back: status and health are silent."""
    conf, _, deploy = completed
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    T._set_conf(conf, BACKUP_CMD="false")
    assert T._server("update", conf, pkg_dir2, "--apply") == OP.EXIT_UPDATE
    assert T._journal(tmp_path)["status"] == OP.IN_PROGRESS
    T._plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == T.OLD_ID and "OCR_OFFLINE" not in fake_docker.app()["env"]
    capsys.readouterr()
    rc_status = T._status(conf)
    rc_health = OP.main(["health", "--config", str(conf)])
    out = capsys.readouterr().out
    print("PROOF status rc", rc_status, "health rc", rc_health, "DRIFT in output:", "DRIFT" in out)
    assert rc_status == 0 and rc_health == 0 and "DRIFT" not in out


def test_legal_gate_on_a_drifted_container_repoints_the_override_to_the_old_image(completed, fake_docker, tmp_path):
    conf, _, deploy = completed
    T._plain_compose_up(deploy)  # drift: old image is back
    assert fake_docker.app()["image_id"] == T.OLD_ID
    rc = T._rollback(conf, "legal-off")
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    override = (state / "image-override.yml").read_text()
    print("PROOF legal-off rc", rc, "| override now:", override.splitlines()[2].strip(),
          "| journal status", T._journal(tmp_path)["status"])
    assert rc == 0 and 'image: "chatbot5400:local"' in override
    # "the ONLY command that may recreate the application" now starts the OLD image
    subprocess.run(["bash", "-c", (state / "compose-command.txt").read_text()], check=True)
    assert fake_docker.app()["image_id"] == T.OLD_ID
    # and a later `finish`-style check of the override is gone: journal says completed 1.3.0
    assert T._journal(tmp_path)["status"] == OP.COMPLETED


def test_resume_uses_a_stale_legal_gate_decision(deployment, fake_docker, tmp_path):
    """Attempt starts (gate not set), stops at the backup. The operator switches the
    Legal gate OFF (rollback.sh legal-off). The resumed attempt deploys without it and
    finish overwrites the record: the gate is silently back to the image default."""
    conf, pkg_dir, _ = deployment
    T._set_conf(conf, BACKUP_CMD="false")
    assert T._server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert T._rollback(conf, "legal-off") == 0
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    T._set_conf(conf, BACKUP_CMD="true", BACKUP_VERIFY_CMD="true")
    assert T._server("update", conf, pkg_dir, "--apply") == 0  # resumed
    j = T._journal(tmp_path)
    print("PROOF resumed attempt carried_env", j["carried_env"], "| env of the new container",
          fake_docker.app()["env"])
    assert "OCR_LEGAL_NORMALIZATION_ENABLED" not in fake_docker.app()["env"]
    assert T._finish(conf) == 0
    assert "OCR_LEGAL_NORMALIZATION_ENABLED" not in fake_docker.app()["env"]
    assert T._status(conf) == 0  # no drift reported after finish


def test_rolled_back_deployment_loses_gate_and_offline_env_silently(completed, fake_docker, repo, tmp_path, capsys):
    """v1.3.0 completed + pinned, Legal gate switched OFF by the operator. v1.3.1 is tried
    and rolled back (-> v1.3.0 with gate OFF, offline variables). A plain compose up then
    recreates v1.3.0 WITHOUT the gate decision and WITHOUT the offline variables;
    status / health (journal: rolled_back) only compare the image ID."""
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    assert T._rollback(conf, "legal-off") == 0
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    assert T._apply(conf, pkg_dir2) == 0
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    env = fake_docker.app()["env"]
    assert env["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false" and env["OCR_OFFLINE"] == "true"
    T._plain_compose_up(deploy)  # explicit -f docker-compose.yml: the pin file is not used
    env = fake_docker.app()["env"]
    capsys.readouterr()
    rc_s, rc_h = T._status(conf), OP.main(["health", "--config", str(conf)])
    out = capsys.readouterr().out
    with capsys.disabled():
        print("PROOF image", fake_docker.app()["image_id"][:19], "env", env, "| status rc", rc_s, "health rc", rc_h,
              "| DRIFT mentioned:", "DRIFT" in out)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
    assert "OCR_OFFLINE" not in env and "OCR_LEGAL_NORMALIZATION_ENABLED" not in env
    assert rc_s == 0 and rc_h == 0


def test_rollback_without_a_journal_accepts_any_local_image(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    sd = tmp_path / "state"
    for n in ("journal.json", "journal.json.bak"):
        (sd / n).rename(sd / (n + ".aside"))  # the documented recovery of a damaged journal
    rc = T._rollback(conf, "app", "--to-image", "chatbot5400:1.3.1", "--no-maintenance")  # not the previous image
    print("PROOF rc", rc, "running", fake_docker.app()["image_id"] == T.NEXT_ID, T._journal(tmp_path)["status"])
    assert rc == 0 and fake_docker.app()["image_id"] == T.NEXT_ID
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK and T._status(conf) == 0


def test_maintenance_is_claimed_for_a_service_without_published_ports(deployment, fake_docker, tmp_path, capsys):
    """Application reached through a reverse proxy / shared network (no `ports:`): the
    maintenance override has nothing to bind to loopback, the check loop is empty, and the
    update is still recorded and announced as 'deployed in maintenance mode'."""
    conf, pkg_dir, _ = deployment

    def no_ports(s):
        s["config"]["services"]["open_notebook"]["ports"] = []
        s["containers"]["c1"]["ports"] = {}

    fake_docker.edit(no_ports)
    capsys.readouterr()
    rc = T._apply(conf, pkg_dir)
    out = capsys.readouterr().out
    j = T._journal(tmp_path)
    with capsys.disabled():
        print("PROOF rc", rc, "journal maintenance", j["maintenance"], "container ports", fake_docker.app()["ports"],
              [l.split("] ", 1)[1] for l in out.splitlines() if "maintenance mode" in l])
    assert rc == 0 and j["maintenance"] is True and fake_docker.app()["ports"] == {}
