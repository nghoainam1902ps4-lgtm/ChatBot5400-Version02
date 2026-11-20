"""Phase 12D4 re-review: REGRESSION tests for the offline update tool (interruption / state machine / source sync).

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
import subprocess
import sys
from pathlib import Path

import pytest

import test_offline_package as T
from test_offline_package import (  # noqa: F401
    completed, deployment, fake_docker, git_deployment, health_server, package, repo,
)

OP = T.OP


# was: test_kill_between_source_merge_and_K_step_defeats_the_resume_guard (PHASE12D4 evidence, R2-15)
def test_kill_between_source_merge_and_K_step_keeps_the_resume_guard(
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
    steps = [s["step"] for s in j["steps"]]
    assert j["status"] == OP.IN_PROGRESS and "K_source" not in steps and "K_intent" in steps
    assert j["source"]["previous_commit"] == v120  # recorded BEFORE git moved anything
    # resume: the guard holds (K_intent, not K_source) and nothing is overwritten
    rc = T._apply(conf, pkg_dir, "--sync-source")
    j = T._journal(tmp_path)
    line = ("PROOF resume rc %s status %s recorded previous_commit %s real previous %s"
            % (rc, j["status"], j["source"]["previous_commit"][:12], v120[:12]))
    assert rc == OP.EXIT_UPDATE and j["status"] == OP.IN_PROGRESS
    assert j["source"]["previous_commit"] == v120
    assert not T._update_ups(fake_docker)
    assert T._status(conf) == OP.EXIT_UNDECIDED  # the interrupted transition is reported
    capsys.readouterr()
    assert T._rollback(conf, "interrupted") == 0
    out = capsys.readouterr().out
    with capsys.disabled():
        print(line)
        print("PROOF", [l for l in out.splitlines() if "source:" in l])
    # the approved image runs from the PREVIOUS checkout again
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert T._git(server, "rev-parse", "HEAD") == v120
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK


# was: test_existing_release_tag_on_another_commit_is_silently_kept (PHASE12D4 evidence, R2-09)
def test_existing_release_tag_on_another_commit_is_refused(git_deployment, fake_docker, repo, tmp_path):
    conf, pkg_dir, server = git_deployment
    v120 = T._git(server, "rev-parse", "HEAD")
    T._git(server, "tag", "v1.3.0-rc.1", v120)  # e.g. an earlier rc of the same name
    rc = T._apply(conf, pkg_dir, "--sync-source")
    print("PROOF rc", rc, "HEAD", T._git(server, "rev-parse", "HEAD")[:12], "tag v1.3.0-rc.1 ->",
          T._git(server, "rev-parse", "v1.3.0-rc.1")[:12])
    assert rc == OP.EXIT_UPDATE
    assert T._git(server, "rev-parse", "HEAD") == v120  # nothing moved
    assert T._git(server, "rev-parse", "v1.3.0-rc.1") == v120  # the tag is left alone
    assert not T._update_ups(fake_docker) and fake_docker.app()["image_id"] == T.OLD_ID


# was: test_kill_between_archive_and_first_save_loses_the_journal (PHASE12D4 evidence, R2-13)
def test_kill_between_archive_and_first_save_keeps_a_journal(completed, fake_docker, repo, tmp_path, monkeypatch):
    """A new attempt writes the history copy first and then REPLACES journal.json: a kill
    in between leaves the previous journal readable, and the approved deployment is
    still compared with what runs."""
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
    assert (sd / "journal.json").exists() and (sd / "journal.json.bak").exists()
    assert T._journal(tmp_path)["status"] == OP.COMPLETED  # the previous attempt, intact
    T._plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID  # the approved image (was: the old one came back)
    assert T._status(conf) == 0 and OP.main(["health", "--config", str(conf)]) == 0
    fake_docker.edit(lambda s: s["containers"]["c1"].update(image_id=T.OLD_ID))  # and if it does come back:
    assert T._status(conf) == OP.EXIT_DRIFT


# was: test_kill_after_compose_up_in_finish_leaves_normal_mode_unchecked_and_unreported (PHASE12D4 evidence, R2-13)
def test_kill_after_compose_up_in_finish_is_reported_and_recoverable(
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
    rc = T._status(conf)
    print("PROOF status", j["status"], "ports", ports, "status rc", rc)
    assert j["status"] == OP.AWAITING
    assert ports["8502/tcp"][0]["HostIp"] == "0.0.0.0"  # public: the scenario
    assert rc == OP.EXIT_UNDECIDED  # never 0: an interrupted transition (Q_intent / UP_intent)
    assert [s for s in j["steps"] if s["step"] == "UP_intent" and s["purpose"] == "finish"]
    # recovery: finish again completes the checked transition
    assert T._finish(conf) == 0 and T._status(conf) == 0


def _next_package(fake_docker, repo, tmp_path):
    (repo / "VERSION").write_text("1.3.1\n")
    T._git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = T._build(repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2")
    return T._unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")


# was: test_refused_second_update_leaves_the_recorded_command_starting_the_unapproved_image (PHASE12D4 evidence, R2-12)
def test_refused_second_update_leaves_the_recorded_command_starting_the_approved_image(
    completed, fake_docker, repo, tmp_path, capsys
):
    """v1.3.0 completed. The update to v1.3.1 is refused BEFORE the new image runs
    (RapidOCR check). No shared file changed: the recorded command - like any other start
    path - starts the APPROVED v1.3.0, and status / health report the open attempt."""
    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    command = (state / "compose-command.txt").read_text()
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    start = len(fake_docker.calls())
    assert T._apply(conf, pkg_dir2) == OP.EXIT_UPDATE
    assert not T._update_ups(fake_docker, start) and fake_docker.app()["image_id"] == T.IMAGE_ID  # the new image never ran
    assert (state / "compose-command.txt").read_text() == command  # the operator's command is unchanged
    subprocess.run(["bash", "-c", command], check=True)  # reboot script / operator, as instructed
    capsys.readouterr()
    rc_s, rc_h = T._status(conf), OP.main(["health", "--config", str(conf)])
    with capsys.disabled():
        print("PROOF running", fake_docker.app()["image_id"][:19], "= 1.3.0 approved:", fake_docker.app()["image_id"] == T.IMAGE_ID,
              "| ports", fake_docker.app()["ports"], "| journal", T._journal(tmp_path)["status"],
              "| status rc", rc_s, "health rc", rc_h)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert rc_s == OP.EXIT_UNDECIDED and rc_h == OP.EXIT_UNDECIDED


# was: test_refused_rollback_leaves_the_override_on_the_rollback_image (PHASE12D4 evidence, R2-12)
def test_refused_rollback_changes_nothing(completed, fake_docker, tmp_path, capsys):
    """Every check that can refuse a rollback runs before anything changes: after a refused
    rollback the deploy tag, approved.json and the recorded command still name the
    approved image."""
    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    evil = tmp_path / "evil-app-maintenance.yml"  # any reason for compare_configs to refuse
    evil.write_text("services: {}\n")
    T._set_conf(conf, MAINTENANCE_OVERRIDE=evil)
    ups = len(T._ups(fake_docker))
    approved = (state / "approved.json").read_text()
    assert T._rollback(conf) == OP.EXIT_UPDATE
    assert len(T._ups(fake_docker)) == ups and T._journal(tmp_path)["status"] == OP.COMPLETED
    assert not (state / "image-override.yml").exists()
    assert (state / "approved.json").read_text() == approved
    assert fake_docker.get()["images"]["chatbot5400:local"] == T.IMAGE_ID
    subprocess.run(["bash", "-c", (state / "compose-command.txt").read_text()], check=True)
    with capsys.disabled():
        print("PROOF journal", T._journal(tmp_path)["status"],
              "| after the recorded command the app runs the APPROVED image:", fake_docker.app()["image_id"] == T.IMAGE_ID)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID


# was: test_closing_the_refused_attempt_does_not_repair_the_override (PHASE12D4 evidence, R2-12)
def test_closing_the_refused_attempt_keeps_the_approved_image(completed, fake_docker, repo, tmp_path, capsys):
    conf, _, deploy = completed
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    pkg_dir2 = _next_package(fake_docker, repo, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert T._apply(conf, pkg_dir2) == OP.EXIT_UPDATE
    assert T._rollback(conf, "interrupted") == 0  # back to normal mode on the approved image
    assert T._journal(tmp_path)["status"] == OP.ROLLED_BACK and T._status(conf) == 0
    assert not (state / "image-override.yml").exists()
    subprocess.run(["bash", "-c", (state / "compose-command.txt").read_text()], check=True)
    with capsys.disabled():
        print("PROOF after closing the attempt the recorded command runs 1.3.0:", fake_docker.app()["image_id"] == T.IMAGE_ID)
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
