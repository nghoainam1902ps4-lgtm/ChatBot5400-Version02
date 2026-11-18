"""Phase 12D4 re-review: REGRESSION tests for the offline update tool (pin / drift / legal gate / resume).

Written by a fresh-context sub-reviewer of this session (it was given the code
of scripts/offline/offline_package.py, not the Phase 12D3 conclusions), then
re-run and read by the main reviewer. Each test first REPRODUCED a defect (it
asserted the unsafe outcome and passed while the defect existed). Phase 12D5
fixed the defects with the deployment contract (DEPLOY_IMAGE_TAG moved only by a
verified finish / rollback, environment and Legal gate in the operator's own
files, approved.json compared in every state); every test is now INVERTED into a
regression test: same scenario, it asserts the SAFE outcome, and a `# was:`
comment names the former reproduction. Findings: docs/review/PHASE12D4_NEW_FINDINGS.json.

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


def _gate(fake_docker, value):
    """The operator's procedure: the gate in the local override (contract step 2)."""
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"]["environment"].update(
            OCR_LEGAL_NORMALIZATION_ENABLED=value
        )
    )


# was: test_pin_twice_then_undo_leaves_the_name_on_the_new_image (PHASE12D4 evidence, R2-16)
def test_pin_twice_is_idempotent_and_undo_cannot_strand_the_tag(completed, fake_docker, tmp_path):
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    assert PIN(conf, "--apply") == 0  # e.g. re-run: nothing to repair
    j = T._journal(tmp_path)
    assert "pin" not in j and not (deploy / OP.PIN_FILE).exists()  # no bookkeeping, no file
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID  # the approved image
    assert PIN(conf, "--undo") == OP.EXIT_USAGE  # an approval is undone with rollback app
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID
    # rollback: the deployment's own image name follows the rollback
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.OLD_ID
    T._plain_compose_up(deploy)  # reboot script / operator
    print("PROOF after rollback + plain compose up the app runs", fake_docker.app()["image_id"][:19], "(the approved previous image)")
    assert fake_docker.app()["image_id"] == T.OLD_ID


# was: test_pin_killed_after_docker_tag_cannot_be_undone (PHASE12D4 evidence, R2-16)
def test_kill_during_a_pin_repair_is_reported_and_recoverable(completed, fake_docker, tmp_path, monkeypatch):
    """The deploy tag is the only state of the pin now. A kill right after the `docker
    tag` of a repair is reported; repeating the repair closes it; a rollback still moves
    the deployment's name back."""
    conf, _, deploy = completed
    fake_docker.edit(lambda s: s["images"].update({"chatbot5400:local": T.OLD_ID}))  # moved by hand
    real = OP.run

    def dying(cmd, *a, **k):
        out = real(cmd, *a, **k)
        if cmd[:2] == ["docker", "tag"] and cmd[-1] == "chatbot5400:local":
            raise KeyboardInterrupt  # kill -9 / power loss right after `docker tag`
        return out

    monkeypatch.setattr(OP, "run", dying)
    with pytest.raises(KeyboardInterrupt):
        PIN(conf, "--apply")
    monkeypatch.setattr(OP, "run", real)
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID  # the name was moved
    assert T._status(conf) == OP.EXIT_UNDECIDED  # the unfinished repair is reported
    assert PIN(conf, "--apply") == 0  # repeated: nothing to move, the repair is closed
    assert T._status(conf) == 0
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    print("PROOF rolled back, deployment name ->", fake_docker.get()["images"]["chatbot5400:local"][:19])
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.OLD_ID


def _next_package(fake_docker, repo, tmp_path):
    (repo / "VERSION").write_text("1.3.1\n")
    T._git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = T._build(repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2")
    return T._unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")


# was: test_pin_of_first_update_is_stale_after_the_second_and_cannot_be_renewed (PHASE12D4 evidence, R2-16)
def test_deploy_tag_follows_every_finished_update(completed, fake_docker, repo, tmp_path, capsys):
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    assert T._apply(conf, pkg_dir2) == 0 and T._finish(conf) == 0
    assert fake_docker.app()["image_id"] == T.NEXT_ID
    capsys.readouterr()
    rc = PIN(conf, "--apply")
    print("PROOF pin after 2nd update rc", rc)
    assert rc == 0  # nothing stale, nothing to renew
    assert T._status(conf) == 0
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.NEXT_ID  # the second update
    T._plain_compose_up(deploy)  # the operator's / boot script's plain command
    print("PROOF plain compose up runs", fake_docker.app()["image_id"][:19], "= 1.3.1")
    assert fake_docker.app()["image_id"] == T.NEXT_ID


# was: test_no_drift_report_while_a_later_attempt_is_unfinished (PHASE12D4 evidence, R2-13)
def test_drift_is_reported_while_a_later_attempt_is_unfinished(completed, fake_docker, repo, tmp_path, capsys):
    """v1.3.0 completed. The next update stops at the backup step (status in_progress).
    A plain `docker compose up -d` starts the APPROVED v1.3.0; when the old v1.2.0 does
    come back (tag moved by hand) without OCR_OFFLINE, status and health say so."""
    conf, _, deploy = completed
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    T._set_conf(conf, BACKUP_CMD="false")
    assert T._server("update", conf, pkg_dir2, "--apply") == OP.EXIT_UPDATE
    assert T._journal(tmp_path)["status"] == OP.IN_PROGRESS
    T._plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID  # the approved image
    assert T._status(conf) == OP.EXIT_UNDECIDED  # no drift, an undecided attempt
    fake_docker.edit(lambda s: s["images"].update({"chatbot5400:local": T.OLD_ID}))
    fake_docker.edit(lambda s: s["config"]["services"]["open_notebook"]["environment"].pop("OCR_OFFLINE"))
    T._plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == T.OLD_ID and "OCR_OFFLINE" not in fake_docker.app()["env"]
    capsys.readouterr()
    rc_status = T._status(conf)
    rc_health = OP.main(["health", "--config", str(conf)])
    out = capsys.readouterr().out
    print("PROOF status rc", rc_status, "health rc", rc_health, "DRIFT in output:", "DRIFT" in out)
    assert rc_status == OP.EXIT_DRIFT and rc_health == OP.EXIT_DRIFT
    assert "IMAGE DRIFT" in out and "DEPLOY TAG DRIFT" in out and "ENVIRONMENT DRIFT" in out


# was: test_legal_gate_on_a_drifted_container_repoints_the_override_to_the_old_image (PHASE12D4 evidence, R2-12)
def test_legal_gate_on_a_drifted_container_changes_nothing(completed, fake_docker, tmp_path):
    conf, _, deploy = completed
    fake_docker.edit(lambda s: s["images"].update({"chatbot5400:local": T.OLD_ID}))  # moved by hand
    T._plain_compose_up(deploy)  # drift: old image is back
    assert fake_docker.app()["image_id"] == T.OLD_ID
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    command = (state / "compose-command.txt").read_text()
    rc = T._rollback(conf, "legal-off")
    print("PROOF legal-off rc", rc, "| journal status", T._journal(tmp_path)["status"])
    assert rc == OP.EXIT_USAGE and not (state / "image-override.yml").exists()
    assert (state / "compose-command.txt").read_text() == command
    assert T._journal(tmp_path)["status"] == OP.COMPLETED
    assert T._status(conf) == OP.EXIT_DRIFT  # the drift is reported
    assert PIN(conf, "--apply") == 0  # and repaired
    subprocess.run(["bash", "-c", command], check=True)  # the recorded command
    assert fake_docker.app()["image_id"] == T.IMAGE_ID  # the approved image again


# was: test_resume_uses_a_stale_legal_gate_decision (PHASE12D4 evidence, R2-17)
def test_resume_uses_the_legal_gate_of_the_operator_configuration(deployment, fake_docker, tmp_path):
    """Attempt starts, stops at the backup. The operator switches the Legal gate OFF -
    with the documented procedure (own file + operations script; `rollback legal-off`
    refuses). The resumed attempt and finish keep the operator's decision."""
    conf, pkg_dir, deploy = deployment
    T._set_conf(conf, BACKUP_CMD="false")
    assert T._server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert T._rollback(conf, "legal-off") == OP.EXIT_USAGE
    _gate(fake_docker, "false")
    T._plain_compose_up(deploy)
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    T._set_conf(conf, BACKUP_CMD="true", BACKUP_VERIFY_CMD="true")
    assert T._server("update", conf, pkg_dir, "--apply") == 0  # resumed
    j = T._journal(tmp_path)
    print("PROOF resumed attempt", j["attempt_id"], "| env of the new container", fake_docker.app()["env"])
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    assert T._finish(conf) == 0
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    assert T._status(conf) == 0


# was: test_rolled_back_deployment_loses_gate_and_offline_env_silently (PHASE12D4 evidence, R2-13)
def test_rolled_back_deployment_keeps_gate_and_offline_env(completed, fake_docker, repo, tmp_path, capsys):
    """v1.3.0 completed, Legal gate OFF in the operator's files. v1.3.1 is tried and rolled
    back (-> v1.3.0). A plain compose up recreates v1.3.0 WITH the gate decision and the
    offline variables; if the operator's files lose one, status reports it."""
    conf, _, deploy = completed
    assert PIN(conf, "--apply") == 0
    assert T._rollback(conf, "legal-off") == OP.EXIT_USAGE
    _gate(fake_docker, "false")
    T._plain_compose_up(deploy)
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    assert T._apply(conf, pkg_dir2) == 0
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    env = fake_docker.app()["env"]
    assert env["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false" and env["OCR_OFFLINE"] == "true"
    T._plain_compose_up(deploy)  # explicit -f docker-compose.yml
    env = fake_docker.app()["env"]
    capsys.readouterr()
    rc_s, rc_h = T._status(conf), OP.main(["health", "--config", str(conf)])
    out = capsys.readouterr().out
    with capsys.disabled():
        print("PROOF image", fake_docker.app()["image_id"][:19], "env", env, "| status rc", rc_s, "health rc", rc_h)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
    assert env["OCR_OFFLINE"] == "true" and env["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    assert rc_s == 0 and rc_h == 0
    fake_docker.edit(lambda s: s["config"]["services"]["open_notebook"]["environment"].pop("OCR_OFFLINE"))
    T._plain_compose_up(deploy)
    assert T._status(conf) == OP.EXIT_DRIFT  # rolled_back is checked for environment too


# was: test_rollback_without_a_journal_accepts_any_local_image (PHASE12D4 evidence, R2-20)
def test_rollback_without_a_journal_needs_force_for_another_image(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    sd = tmp_path / "state"
    for n in ("journal.json", "journal.json.bak"):
        (sd / n).rename(sd / (n + ".aside"))  # the documented recovery of a damaged journal
    ups = len(T._ups(fake_docker))
    rc = T._rollback(conf, "app", "--to-image", "chatbot5400:1.3.1", "--no-maintenance")  # not the previous image
    print("PROOF rc", rc, "running the new image still:", fake_docker.app()["image_id"] == T.IMAGE_ID)
    assert rc == OP.EXIT_UPDATE and fake_docker.app()["image_id"] == T.IMAGE_ID
    assert len(T._ups(fake_docker)) == ups
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.OLD_ID
    # the approved previous image (approved.json) needs no force
    assert T._rollback(conf, "app", "--to-image", "chatbot5400:local", "--no-maintenance") == 0
    assert fake_docker.app()["image_id"] == T.OLD_ID


# was: test_maintenance_is_claimed_for_a_service_without_published_ports (PHASE12D4 evidence, R2-20)
def test_maintenance_is_not_claimed_for_a_service_without_published_ports(deployment, fake_docker, tmp_path, capsys):
    """Application reached through a reverse proxy / shared network (no `ports:`): loopback
    ports cannot prove that users are locked out. The update refuses unless the operator
    attests it, records that attestation as the proof, and claims no maintenance mode."""
    conf, pkg_dir, _ = deployment

    def no_ports(s):
        s["config"]["services"]["open_notebook"]["ports"] = []
        s["containers"]["c1"]["ports"] = {}

    fake_docker.edit(no_ports)
    capsys.readouterr()
    rc = T._apply(conf, pkg_dir)
    out = capsys.readouterr().out
    assert rc == OP.EXIT_PREFLIGHT and "--writes-stopped-confirmed" in out
    assert not (tmp_path / "state" / "journal.json").exists() and not T._ups(fake_docker)
    rc = T._apply(conf, pkg_dir, "--writes-stopped-confirmed")
    out = capsys.readouterr().out
    j = T._journal(tmp_path)
    with capsys.disabled():
        print("PROOF rc", rc, "quiesce", j["quiesce"]["proven_by"])
    assert rc == 0 and j["quiesce"]["proven_by"].startswith("operator attestation")
    assert "update deployed in maintenance mode" not in out
