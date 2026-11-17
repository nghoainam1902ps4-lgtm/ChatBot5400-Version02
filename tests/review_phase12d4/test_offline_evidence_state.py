"""Phase 12D4 re-review: REPRODUCTION tests for the offline update tool (interruption / state machine / source sync).

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
from pathlib import Path

import pytest

import test_offline_package as T
from test_offline_package import (  # noqa: F401
    completed, deployment, fake_docker, git_deployment, health_server, package, repo,
)

OP = T.OP


def test_kill_between_source_merge_and_K_step_defeats_the_resume_guard(
    git_deployment, fake_docker, repo, tmp_path, monkeypatch, capsys
):
    conf, pkg_dir, server = git_deployment
    v120 = T._git(server, "rev-parse", "HEAD")
    release = T._git(repo, "rev-parse", "HEAD")
    real_step = OP.Journal.step

    def dying(self, name, **info):
        if name == "K_source":
            raise KeyboardInterrupt  # power loss right after `git merge --ff-only`
        return real_step(self, name, **info)

    monkeypatch.setattr(OP.Journal, "step", dying)
    with pytest.raises(KeyboardInterrupt):
        T._apply(conf, pkg_dir, "--sync-source")
    monkeypatch.setattr(OP.Journal, "step", real_step)
    assert T._git(server, "rev-parse", "HEAD") == release  # the source HAS moved
    j = T._journal(tmp_path)
    assert j["status"] == OP.IN_PROGRESS and "K_source" not in [s["step"] for s in j["steps"]]
    # resume: the guard "this attempt already synchronised the source" does not fire
    rc = T._apply(conf, pkg_dir, "--sync-source")
    j = T._journal(tmp_path)
    line = ("PROOF resume rc %s status %s recorded previous_commit %s real previous %s"
            % (rc, j["status"], j["source"]["previous_commit"][:12], v120[:12]))
    assert rc == 0 and j["status"] == OP.AWAITING
    assert j["source"]["previous_commit"] == release  # the real previous commit is lost
    capsys.readouterr()
    assert T._rollback(conf) == 0
    out = capsys.readouterr().out
    with capsys.disabled():
        print(line)
        print("PROOF", [l for l in out.splitlines() if "source:" in l])
    # old image now runs from the RELEASE checkout; rollback reported success
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert T._git(server, "rev-parse", "HEAD") == release != v120
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK


def test_existing_release_tag_on_another_commit_is_silently_kept(git_deployment, fake_docker, repo, tmp_path):
    conf, pkg_dir, server = git_deployment
    v120 = T._git(server, "rev-parse", "HEAD")
    T._git(server, "tag", "v1.3.0-rc.1", v120)  # e.g. an earlier rc of the same name
    assert T._apply(conf, pkg_dir, "--sync-source") == 0
    release = T._git(repo, "rev-parse", "HEAD")
    print("PROOF HEAD", T._git(server, "rev-parse", "HEAD")[:12], "tag v1.3.0-rc.1 ->",
          T._git(server, "rev-parse", "v1.3.0-rc.1")[:12])
    assert T._git(server, "rev-parse", "HEAD") == release
    assert T._git(server, "rev-parse", "v1.3.0-rc.1") == v120 != release


def test_kill_between_archive_and_first_save_loses_the_journal(completed, fake_docker, repo, tmp_path, monkeypatch):
    """start_attempt archives (= deletes journal.json and .bak) and only then writes the
    new journal. A kill in between leaves NO journal: status says 'no update recorded',
    drift detection of the completed deployment is gone."""
    conf, pkg_dir, deploy = completed
    real_save = OP.Journal.save
    state = {"armed": True}

    def dying(self):
        if state["armed"] and self.data.get("status") == OP.IN_PROGRESS and not self.data.get("steps"):
            raise KeyboardInterrupt
        return real_save(self)

    monkeypatch.setattr(OP.Journal, "save", dying)
    with pytest.raises(KeyboardInterrupt):
        T._apply(conf, pkg_dir, "--allow-version-mismatch")
    state["armed"] = False
    sd = tmp_path / "state"
    print("PROOF files", sorted(p.name for p in sd.iterdir()))
    assert not (sd / "journal.json").exists() and not (sd / "journal.json.bak").exists()
    T._plain_compose_up(deploy)  # the old image comes back
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert T._status(conf) == 0 and OP.main(["health", "--config", str(conf)]) == 0


def test_kill_after_compose_up_in_finish_leaves_normal_mode_unchecked_and_unreported(
    deployment, fake_docker, tmp_path, monkeypatch
):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    real_step = OP.Journal.step

    def dying(self, name, **info):
        if name == "Q_normal_mode":
            raise KeyboardInterrupt
        return real_step(self, name, **info)

    monkeypatch.setattr(OP.Journal, "step", dying)
    with pytest.raises(KeyboardInterrupt):
        T._finish(conf)
    monkeypatch.setattr(OP.Journal, "step", real_step)
    j = T._journal(tmp_path)
    ports = fake_docker.app()["ports"]
    print("PROOF status", j["status"], "journal maintenance", j["maintenance"], "ports", ports, "status rc", T._status(conf))
    assert j["status"] == OP.AWAITING and j["maintenance"] is True
    assert ports["8502/tcp"][0]["HostIp"] == "0.0.0.0"  # public, never health-checked
    assert T._status(conf) == 0


def _next_package(fake_docker, repo, tmp_path):
    (repo / "VERSION").write_text("1.3.1\n")
    T._git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = T._build(repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2")
    return T._unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")


def test_refused_second_update_leaves_the_recorded_command_starting_the_unapproved_image(
    completed, fake_docker, repo, tmp_path, capsys
):
    """v1.3.0 completed: compose-command.txt is 'the ONLY command that may recreate the
    application'. The update to v1.3.1 is refused BEFORE the recreate (RapidOCR check) but
    it has already overwritten STATE_DIR/image-override.yml. The recorded command now
    starts v1.3.1 in normal mode: no maintenance, no DB reference, no health check, no
    approval - and status / health report nothing (journal in_progress)."""
    import subprocess

    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    command = (state / "compose-command.txt").read_text()
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    ups = len(T._ups(fake_docker))
    assert T._apply(conf, pkg_dir2) == OP.EXIT_UPDATE
    assert len(T._ups(fake_docker)) == ups and fake_docker.app()["image_id"] == T.IMAGE_ID  # nothing recreated
    assert (state / "compose-command.txt").read_text() == command  # the operator's command is unchanged
    subprocess.run(["bash", "-c", command], check=True)  # reboot script / operator, as instructed
    capsys.readouterr()
    rc_s, rc_h = T._status(conf), OP.main(["health", "--config", str(conf)])
    with capsys.disabled():
        print("PROOF running", fake_docker.app()["image_id"][:19], "= 1.3.1:", fake_docker.app()["image_id"] == T.NEXT_ID,
              "| ports", fake_docker.app()["ports"], "| journal", T._journal(tmp_path)["status"],
              "| status rc", rc_s, "health rc", rc_h)
    assert fake_docker.app()["image_id"] == T.NEXT_ID
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert rc_s == 0 and rc_h == 0


def test_refused_rollback_leaves_the_override_on_the_rollback_image(completed, fake_docker, tmp_path, capsys):
    """rollback writes image-override.yml BEFORE the checks that can refuse. After a
    refused rollback the journal still says 'completed' (new image) but the recorded
    command starts the OLD image."""
    import subprocess

    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    evil = tmp_path / "evil-app-maintenance.yml"  # any reason for compare_configs to refuse
    evil.write_text("services: {}\n")
    T._set_conf(conf, MAINTENANCE_OVERRIDE=evil)
    ups = len(T._ups(fake_docker))
    assert T._rollback(conf) == OP.EXIT_UPDATE
    assert len(T._ups(fake_docker)) == ups and T._journal(tmp_path)["status"] == OP.COMPLETED
    override = (state / "image-override.yml").read_text()
    subprocess.run(["bash", "-c", (state / "compose-command.txt").read_text()], check=True)
    with capsys.disabled():
        print("PROOF override:", override.splitlines()[2].strip(), "| journal", T._journal(tmp_path)["status"],
              "| after the recorded command the app runs the OLD image:", fake_docker.app()["image_id"] == T.OLD_ID)
    assert "rollback-" in override and fake_docker.app()["image_id"] == T.OLD_ID


def test_closing_the_refused_attempt_does_not_repair_the_override(completed, fake_docker, repo, tmp_path, capsys):
    import subprocess

    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert T._apply(conf, pkg_dir2) == OP.EXIT_UPDATE
    assert T._rollback(conf, "interrupted") == 0  # "left running, untouched"; status rolled_back
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK and T._status(conf) == 0
    override = (state / "image-override.yml").read_text()
    subprocess.run(["bash", "-c", (state / "compose-command.txt").read_text()], check=True)
    with capsys.disabled():
        print("PROOF override after closing the attempt:", override.splitlines()[2].strip(),
              "| recorded command now runs 1.3.1:", fake_docker.app()["image_id"] == T.NEXT_ID)
    assert fake_docker.app()["image_id"] == T.NEXT_ID
