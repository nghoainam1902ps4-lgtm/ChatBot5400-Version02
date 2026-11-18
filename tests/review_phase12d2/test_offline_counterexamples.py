"""Counter-examples for scripts/offline/offline_package.py (Phase 12D2 review).

Same means as tests/test_offline_package.py: ``docker`` is the recording fake of
that module (no daemon in Cloud), git / tar / SHA-256 are real. What only a real
Docker engine can show is listed in docs/review/PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md.
"""

# ruff: noqa: F811 - pytest fixtures imported from tests/test_offline_package.py are used as parameters
from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path

import offline_package as OP
import pytest
import test_offline_package as T
from test_offline_package import (  # noqa: F401 - pytest fixtures
    deployment,
    fake_docker,
    health_server,
    package,
    repo,
)


def _git(checkout: Path, *a: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), *a], check=True, capture_output=True, text=True
    ).stdout.strip()


# --------------------------------------------------------------------------- #
# F-04: the documented build command cannot create the git bundle
# --------------------------------------------------------------------------- #


# PHASE12D2 F-04 (audit counter-example by the Phase 12D2 review: build-package.sh/.ps1 pass --git-ref <sha>; git refuses an empty bundle).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f04_build_with_commit_sha_as_the_wrappers_pass_it(fake_docker, repo, tmp_path):
    sha = _git(repo, "rev-parse", "HEAD")
    # Phase 12D5 (R2-08): the image must carry the revision label of the commit, as the
    # wrappers' build step adds it
    T._label_image(repo)
    rc = OP.main(
        ["build", "--version", "1.3.0-rc.1", "--image", "chatbot5400:1.3.0-rc.1", "--repo", str(repo),
         "--out", str(tmp_path / "dist"), "--git-ref", sha]
    )  # fmt: skip
    assert rc == 0


def test_f04_wrappers_really_pass_a_commit_sha():
    """Evidence for F-04: both wrappers resolve HEAD to a SHA and never pass a ref name."""
    sh = (T.ROOT / "scripts" / "offline" / "build-package.sh").read_text()
    ps = (T.ROOT / "scripts" / "offline" / "build-package.ps1").read_text()
    assert 'COMMIT="$(git rev-parse HEAD)"' in sh and '--git-ref "$COMMIT"' in sh
    assert (
        "$commit = (& git rev-parse HEAD).Trim()" in ps and "'--git-ref', $commit" in ps
    )


# PHASE12D2 F-05 (audit counter-example by the Phase 12D2 review: a bundle built from HEAD carries no refs/*; --sync-source cannot fetch the release commit).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f05_sync_source_from_a_default_package(deployment, repo, tmp_path):
    conf, pkg_dir, _ = deployment
    manifest = OP.load_package(str(pkg_dir))
    # The server checkout: a clone that stopped at v1.2.0 (what an offline server has).
    server = tmp_path / "server-checkout"
    server.mkdir()
    _git(server, "init", "-q", "-b", "deploy")
    _git(server, "fetch", "-q", str(repo), "refs/tags/v1.2.0:refs/tags/v1.2.0")
    _git(server, "merge", "-q", "--ff-only", "v1.2.0")
    missing = subprocess.run(
        [
            "git",
            "-C",
            str(server),
            "cat-file",
            "-e",
            manifest["source"]["commit"] + "^{commit}",
        ],
        capture_output=True,
    )
    if missing.returncode == 0:
        pytest.skip("test setup: the server checkout already has the release commit")
    cfg = OP.load_config(str(conf))
    cfg["DEPLOY_DIR"] = str(server)
    OP.sync_source(OP.Deployment(cfg), Path(pkg_dir), manifest)  # raises Refused today
    assert _git(server, "rev-parse", "HEAD") == manifest["source"]["commit"]


# --------------------------------------------------------------------------- #
# F-08: the backup of an earlier attempt is reused after a rollback
# --------------------------------------------------------------------------- #


# PHASE12D2 F-08 (audit counter-example by the Phase 12D2 review: journal steps of the first attempt are reused, the second attempt takes no new backup).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f08_second_attempt_after_rollback_takes_a_new_backup(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = tmp_path / "backups.log"
    with open(conf, "a") as f:
        f.write(f"\nBACKUP_CMD=echo backup >> {marker}\nBACKUP_VERIFY_CMD=true\n")
    assert T._server("update", conf, pkg_dir, "--apply") == 0
    assert (
        OP.main(
            ["rollback", "app", "--config", str(conf), "--package-dir", str(pkg_dir)]
        )
        == 0
    )
    assert marker.read_text().count("backup") == 1
    # ... the database keeps changing; days later the same package is applied again
    assert T._server("update", conf, pkg_dir, "--apply") == 0
    assert marker.read_text().count("backup") == 2


# --------------------------------------------------------------------------- #
# F-09: finish / rollback report success without checking the application
# --------------------------------------------------------------------------- #


# PHASE12D2 F-09 (audit counter-example by the Phase 12D2 review: finish marks the update 'completed' without any health check).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f09_finish_checks_health_before_reporting_completed(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert (
        T._server(
            "update",
            conf,
            pkg_dir,
            "--apply",
            "--backup-reference",
            "bk",
            "--backup-verified",
        )
        == 0
    )
    # The application does not come back after the second recreate (normal mode).
    text = conf.read_text().splitlines()
    conf.write_text(
        "\n".join(x for x in text if not x.startswith("HEALTH_URL="))
        + "\nHEALTH_URL=http://127.0.0.1:9/health\n"
    )
    rc = OP.main(["finish", "--config", str(conf), "--approve", "owner"])
    journal = json.loads((tmp_path / "state" / "journal.json").read_text())
    assert rc != 0 and journal["status"] != "completed"


# --------------------------------------------------------------------------- #
# F-12: values from the manifest are written into YAML / passed to git unvalidated
# --------------------------------------------------------------------------- #


# PHASE12D2 F-12 (audit counter-example by the Phase 12D2 review: image reference is written unquoted into the compose override).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f12_image_reference_cannot_inject_yaml(deployment):
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    evil = "chatbot5400:1.3.0\n    privileged: true\n    volumes:\n      - /:/host"
    with pytest.raises(OP.Refused):
        OP.write_image_override(dep, evil, {})


# PHASE12D2 F-12 (audit counter-example by the Phase 12D2 review: manifest image.tag / source.commit / release_tag are not format-checked).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f12_manifest_rejects_malformed_tag_and_commit(deployment):
    _, pkg_dir, _ = deployment
    manifest = json.loads((Path(pkg_dir) / OP.MANIFEST).read_text())
    manifest["image"]["tag"] = "chatbot5400:1.3.0\n    privileged: true"
    manifest["source"]["commit"] = "--upload-pack=touch /tmp/x"
    manifest["application"]["release_tag"] = "-d"
    with pytest.raises(OP.Refused):
        OP.validate_manifest(manifest)


# --------------------------------------------------------------------------- #
# F-13: a damaged journal makes every command crash with a traceback
# --------------------------------------------------------------------------- #


# PHASE12D2 F-13 (audit counter-example by the Phase 12D2 review: json.JSONDecodeError escapes main(); status/rollback unusable after a torn write).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f13_truncated_journal_is_reported_not_a_traceback(deployment, tmp_path):
    conf, _, _ = deployment
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "journal.json").write_text(
        '{"version": "1.3.0-rc.1", "status": "in_pro'
    )  # power loss
    rc = OP.main(["status", "--config", str(conf)])
    assert rc in (OP.EXIT_UPDATE, OP.EXIT_USAGE)


# --------------------------------------------------------------------------- #
# F-14: duplicate archive entries are accepted
# --------------------------------------------------------------------------- #


# PHASE12D2 F-14 (audit counter-example by the Phase 12D2 review: two entries with the same name; the later one silently wins).
# Fixed in Phase 12D3: the xfail marker is removed, this is now a regression test.
def test_f14_duplicate_archive_entries_refused(tmp_path):
    pkg = tmp_path / "dup.tar.gz"
    with tarfile.open(pkg, "w:gz") as tar:
        for payload in (b"first" * 400, b"second" * 400):
            info = tarfile.TarInfo("pkg/scripts/update.sh")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(OP.Refused):
        OP.inspect_archive(pkg)


# --------------------------------------------------------------------------- #
# T-02: the safety oracle of the existing tests cannot fail on "compose down"
# --------------------------------------------------------------------------- #


# PHASE12D2 T-02 (fixed in Phase 12D3: xfail removed, this is now the regression test)
def test_t02_existing_safe_calls_oracle_rejects_compose_down():
    dangerous = [
        "compose",
        "-p",
        "x",
        "-f",
        "docker-compose.yml",
        "down",
        "--pull",
        "never",
    ]
    with pytest.raises(AssertionError):
        T._assert_safe_calls([dangerous])


# --------------------------------------------------------------------------- #
# Properties that DO hold (verified by this review, with the fake docker)
# --------------------------------------------------------------------------- #


def test_verified_every_compose_up_is_app_only_no_deps_no_build_pull_never(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    start = len(
        fake_docker.calls()
    )  # build + verify of the fixture are not server-side calls
    assert (
        T._server(
            "update",
            conf,
            pkg_dir,
            "--apply",
            "--backup-reference",
            "bk",
            "--backup-verified",
        )
        == 0
    )
    assert OP.main(["finish", "--config", str(conf), "--approve", "owner"]) == 0
    assert (
        OP.main(["rollback", "legal-off", "--config", str(conf), "--no-maintenance"])
        == 0
    )
    assert OP.main(["rollback", "app", "--config", str(conf)]) == 0
    calls = fake_docker.calls()[start:]
    ups = [c for c in calls if c[0] == "compose" and "up" in c]
    assert len(ups) == 4
    for c in ups:
        tail = c[c.index("up") :]
        assert tail == [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "open_notebook",
        ]
    verbs = set()
    for c in calls:
        if c[0] == "compose":
            rest = [x for x in c[1:] if not x.startswith("-")]
            verbs.update(
                v
                for v in (
                    "down",
                    "pull",
                    "build",
                    "rm",
                    "restart",
                    "stop",
                    "kill",
                    "run",
                    "create",
                )
                if v in rest
            )
        else:
            verbs.add(c[0])
    assert verbs <= {
        "image",
        "info",
        "load",
        "tag",
        "inspect",
    }  # strict version of the oracle


def test_verified_unsigned_package_without_trusted_hash_is_refused(package, tmp_path):
    pkg, _ = package
    assert T._verify(pkg, tmp_path / "x") == OP.EXIT_VERIFY
    assert not (tmp_path / "verify-report.json").exists()


def test_verified_source_repo_scripts_never_call_destructive_docker_commands():
    text = (T.ROOT / "scripts" / "offline" / "offline_package.py").read_text()
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(("#", '"'))
    )
    for forbidden in (
        '"down"',
        '"pull"',
        '"prune"',
        '"rm"',
        '"rmi"',
        '"--volumes"',
        '"restart"',
    ):
        assert forbidden not in code, forbidden
