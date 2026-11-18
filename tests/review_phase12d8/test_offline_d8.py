"""Phase 12D8 final audit - offline update package tooling (review only).

Scope: scripts/offline/offline_package.py (cross-platform lock of commit
4622376, atomic package output), scripts/offline/build-package.ps1,
scripts/windows/phase12-test.ps1, docs/deployment/OFFLINE_UPDATE_*.md (the
manual fallback procedure is the production path), the release notes draft.

Conventions (tests/review_phase12d8/conftest.py): ``xfail(strict=True)`` =
EXPECTED safe behaviour that fails today (finding D8-OFF-xx); ``test_control_*``
/ ``test_verified_*`` = something this review checked for itself and that holds.

What is REAL here: processes, flock(), SIGKILL, git, tar, sha256sum, the text of
the shipped documents and scripts. What is NOT: ``docker`` is the stateful fake
of tests/test_offline_package.py; the Windows branch of the lock is exercised
only as a SIMULATION (``sys.platform`` forced to ``win32`` in a child process
with a stand-in ``msvcrt`` built on POSIX record locks) - that is no evidence
for Windows; PowerShell cannot run here, the .ps1 checks are STATIC text checks.
"""

# ruff: noqa

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import test_offline_package as T
from test_offline_package import fake_docker, package, repo  # noqa: F401

OP = T.OP
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "offline"
DOCS = ROOT / "docs" / "deployment"
MANUAL = DOCS / "OFFLINE_UPDATE_MANUAL_FALLBACK.md"
BUILD_PS1 = SCRIPTS / "build-package.ps1"
TEST_PS1 = ROOT / "scripts" / "windows" / "phase12-test.ps1"
RELEASE_NOTES = ROOT / "docs" / "ocr" / "OCR_RELEASE_NOTES_V1.3.0_RC1.md"
NAME = "ChatBot5400-1.3.0-rc.1-linux-amd64-offline"

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX processes / fake docker")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

HOLDER = textwrap.dedent(
    """\
    import os, subprocess, sys, time
    from pathlib import Path
    sys.path.insert(0, {scripts!r})
    import offline_package as OP
    {prelude}
    target, mark, hold, spawn = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    try:
        with OP.build_lock(target, {name!r}):
            if spawn == "child":   # what the tool does inside the lock: a child process (docker save)
                child = subprocess.Popen(["sleep", "120"])
                Path(str(mark) + ".child").write_text(str(child.pid))
            mark.write_text("GOT")
            time.sleep(hold)
    except OP.Refused as e:
        mark.write_text("REFUSED " + str(e) + " code=" + str(e.code))
    """
)

# SIMULATION of the Windows branch: a stand-in `msvcrt` on POSIX record locks
# (fcntl.lockf locks the byte range at the current file position, like _locking).
FAKE_MSVCRT = textwrap.dedent(
    """\
    import fcntl, json, types
    _m = types.ModuleType("msvcrt")
    _m.LK_NBLCK, _m.LK_UNLCK, _m.LK_LOCK = 2, 0, 1
    def _locking(fd, mode, nbytes):
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        with open(os.environ["D8_MSVCRT_LOG"], "a") as log:
            log.write(json.dumps([os.getpid(), mode, pos, nbytes]) + "\\n")
        fcntl.lockf(fd, fcntl.LOCK_UN if mode == _m.LK_UNLCK else fcntl.LOCK_EX | fcntl.LOCK_NB, nbytes, 0, os.SEEK_CUR)
    _m.locking = _locking
    sys.modules["msvcrt"] = _m
    sys.modules["fcntl_real"] = fcntl
    sys.platform = "win32"
    """
)


def _holder(tmp_path, target, tag, hold=120.0, spawn="-", prelude="", env=None):
    mark = tmp_path / f"mark-{tag}"
    code = HOLDER.format(scripts=str(SCRIPTS), name=NAME, prelude=prelude)
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(target), str(mark), str(hold), spawn],
        stdin=subprocess.DEVNULL,
        env=env,
    )
    return proc, mark


def _wait_for(path: Path, timeout: float = 30.0) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.02)
    raise AssertionError(f"{path} never written")


def _section(doc: Path, start: str, end: str) -> str:
    text = doc.read_text(encoding="utf-8")
    return text[text.index(start) : text.index(end)]


def _bash_blocks(section: str) -> list:
    return re.findall(r"```bash\n(.*?)```", section, flags=re.S)


def _ps_code(path: Path) -> str:
    """Script text without the help block and # comments (STATIC checks only)."""
    text = re.sub(r"<#.*?#>", "", path.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(
        line.split(" #")[0] for line in text.splitlines() if not line.lstrip().startswith("#")
    )


# --------------------------------------------------------------------------- #
# 1. Lock - Linux flock branch, REAL processes
# --------------------------------------------------------------------------- #


@posix_only
def test_control_flock_second_process_refused_then_kill9_frees_the_lock(tmp_path):
    """Two real processes; the refused one changes nothing in the lock file
    (bytes, size, inode); SIGKILL of the holder frees the lock at once; the lock
    file is never deleted and never truncated."""
    out = tmp_path / "dist"
    out.mkdir()
    lock_file = out / f".{NAME}.lock"
    holder, mark = _holder(tmp_path, out, "a")
    try:
        assert _wait_for(mark) == "GOT"
        before = (lock_file.read_bytes(), lock_file.stat().st_ino, lock_file.stat().st_size)
        assert before[0] == f"{holder.pid:<19}\n".encode() and before[2] == 20
        second, mark2 = _holder(tmp_path, out, "b", hold=0)
        second.wait(timeout=30)
        said = _wait_for(mark2)
        assert said.startswith("REFUSED") and f"held by process {holder.pid}" in said
        assert f"code={OP.EXIT_LOCK}" in said
        assert (lock_file.read_bytes(), lock_file.stat().st_ino, lock_file.stat().st_size) == before
    finally:
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=30)
    started = time.monotonic()
    with OP.build_lock(out, NAME):
        assert lock_file.read_bytes() == f"{os.getpid():<19}\n".encode()
    assert time.monotonic() - started < 5 and lock_file.exists()
    assert lock_file.stat().st_ino == before[1]  # same file: never unlinked / recreated


@posix_only
def test_control_lock_is_not_inherited_by_the_tools_child_processes(tmp_path):
    """The lock descriptor is close-on-exec: a child the tool started inside the
    lock (docker save, git) that OUTLIVES a killed builder does not keep the lock.
    (flock belongs to the open file description: an inherited descriptor would.)"""
    out = tmp_path / "dist"
    out.mkdir()
    holder, mark = _holder(tmp_path, out, "a", spawn="child")
    child_pid = None
    try:
        assert _wait_for(mark) == "GOT"
        child_pid = int(_wait_for(Path(str(mark) + ".child")))
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=30)
        os.kill(child_pid, 0)  # the orphan is still alive ...
        with OP.build_lock(out, NAME):  # ... and the lock is free
            pass
    finally:
        holder.kill()
        if child_pid:
            with contextlib.suppress(OSError):
                os.kill(child_pid, signal.SIGKILL)


@posix_only
def test_verified_limitation_an_unlinked_lock_file_gives_two_holders(tmp_path):
    """Recorded LIMITATION (inherent to a lock FILE, not a defect of this change):
    the tool never deletes the lock file, but if somebody else removes it while a
    build holds it (cleaning --out by hand on Linux), the next build creates a new
    file and BOTH hold "the" lock. On Windows the open handle prevents the delete
    (static reasoning, not run)."""
    out = tmp_path / "dist"
    out.mkdir()
    holder, mark = _holder(tmp_path, out, "a")
    try:
        assert _wait_for(mark) == "GOT"
        (out / f".{NAME}.lock").unlink()
        with OP.build_lock(out, NAME):  # a second holder while the first is alive
            assert holder.poll() is None
    finally:
        holder.kill()
        holder.wait(timeout=30)


@posix_only
# was: xfail(strict) D8-OFF-09 - fixed in Phase 12D9
def test_a_lock_that_cannot_be_taken_for_another_reason_is_not_reported_as_held(tmp_path, monkeypatch):
    import fcntl

    out = tmp_path / "dist"
    out.mkdir()
    with OP.build_lock(out, NAME):  # an earlier, finished build left its PID in the file
        pass

    def no_locks(fd, op):
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(fcntl, "flock", no_locks)
    with pytest.raises(OP.Refused) as refused:
        with OP.build_lock(out, NAME):
            pass
    said = str(refused.value)
    assert "held by" not in said and "another build" not in said, said


# --------------------------------------------------------------------------- #
# 1b. Lock - Windows branch, SIMULATION ONLY (no evidence for Windows)
# --------------------------------------------------------------------------- #


@posix_only
def test_control_windows_branch_simulated_with_a_stand_in_msvcrt(tmp_path):
    """SIMULATION: sys.platform forced to win32 in child processes, msvcrt replaced
    by a stand-in on POSIX record locks. Checks the CONTROL FLOW of the msvcrt
    branch only: non-blocking mode (LK_NBLCK, never the 10 s LK_LOCK retry), ONE
    byte at offset 2**30 - disjoint from the 20-byte PID text at offset 0, so the
    refused process can read the holder's PID although Windows byte-range locks
    are mandatory - the PID text is written after the lock is taken, the refused
    process writes nothing, and a killed holder frees the lock."""
    out = tmp_path / "dist"
    out.mkdir()
    log = tmp_path / "msvcrt.log"
    env = dict(os.environ, D8_MSVCRT_LOG=str(log))
    lock_file = out / f".{NAME}.lock"
    holder, mark = _holder(tmp_path, out, "a", prelude=FAKE_MSVCRT, env=env)
    try:
        assert _wait_for(mark) == "GOT"
        assert lock_file.read_bytes() == f"{holder.pid:<19}\n".encode()
        second, mark2 = _holder(tmp_path, out, "b", hold=0, prelude=FAKE_MSVCRT, env=env)
        second.wait(timeout=30)
        said = _wait_for(mark2)
        assert said.startswith("REFUSED") and f"held by process {holder.pid}" in said
        assert lock_file.read_bytes() == f"{holder.pid:<19}\n".encode()
    finally:
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=30)
    third, mark3 = _holder(tmp_path, out, "c", hold=0, prelude=FAKE_MSVCRT, env=env)
    third.wait(timeout=30)
    assert _wait_for(mark3) == "GOT"
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls and all(pos == OP.LOCK_BYTE_OFFSET == 1 << 30 and n == 1 for _, _, pos, n in calls)
    assert {mode for _, mode, _, _ in calls} == {2, 0}  # LK_NBLCK and LK_UNLCK only
    assert [mode for pid, mode, _, _ in calls if pid == third.pid] == [2, 0]  # lock, then unlock


# --------------------------------------------------------------------------- #
# 2. Atomic output of `build`
# --------------------------------------------------------------------------- #


def _pair(out):
    return out / NAME, out / f"{NAME}.tar.gz", out / f"{NAME}.tar.gz.sha256"


@posix_only
def test_control_every_rename_of_build_stays_inside_out(fake_docker, repo, tmp_path, monkeypatch):
    """os.replace is never asked to cross a filesystem: the partial archive, the
    set-aside hash and the hash's temporary file all live in --out itself."""
    seen = []
    real = os.replace

    def replace(src, dst, *a, **kw):
        seen.append((Path(src), Path(dst)))
        return real(src, dst, *a, **kw)

    old_pkg, _ = T._build(repo, tmp_path)
    out = old_pkg.parent
    shutil.rmtree(out / NAME)
    monkeypatch.setattr(OP.os, "replace", replace)
    T._label_image(repo)
    assert T._build_rc(repo, out) == 0
    inside = [(s, d) for s, d in seen if d.parent == out]
    # was: == 3 (old hash set aside, package, new hash .tmp -> .sha256). Phase 12D9
    # (D8-OFF-03): the new hash is first written beside the package (.tmp ->
    # .sha256.partial-<pid>) before anything is replaced - one rename more, in --out.
    assert len(inside) == 4
    assert all(s.parent == out for s, _ in inside)
    stage, pkg, sha = _pair(out)
    assert sha.read_text() == f"{OP.sha256_file(pkg)}  {pkg.name}\n"
    assert not list(out.glob(".*partial-*")) and not list(out.glob("*.previous-*"))


@posix_only
# was: xfail(strict) D8-OFF-03 - fixed in Phase 12D9
def test_a_build_that_fails_after_the_package_rename_leaves_a_consistent_pair(
    fake_docker, repo, tmp_path, monkeypatch
):
    old_pkg, _ = T._build(repo, tmp_path)
    out = old_pkg.parent
    stage, pkg, sha = _pair(out)
    old_sha = sha.read_text()
    shutil.rmtree(stage)
    real = OP.atomic_write

    def atomic_write(path, text, private=False):
        if Path(path) == sha:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(path, text, private)

    monkeypatch.setattr(OP, "atomic_write", atomic_write)
    T._label_image(repo)
    with pytest.raises(OSError):
        T._build_rc(repo, out)
    # EXPECTED after a failed build: a package WITH the hash that belongs to it
    # (the old pair kept, or the new pair complete) and nothing left lying around.
    assert pkg.is_file() and sha.is_file()
    assert sha.read_text() == f"{OP.sha256_file(pkg)}  {pkg.name}\n"
    assert not list(out.glob("*.previous-*"))
    assert old_sha  # (kept for the report: the old hash is what the orphan holds)


KILLED_BUILD = textwrap.dedent(
    """\
    import os, sys
    from pathlib import Path
    sys.path.insert(0, {scripts!r})
    import offline_package as OP
    pkg = Path(sys.argv[1])
    real = os.replace
    def replace(src, dst, *a, **kw):
        if Path(dst) == pkg:
            os._exit(137)          # SIGKILL / power loss exactly here: no cleanup code runs
        return real(src, dst, *a, **kw)
    os.replace = replace
    sys.exit(OP.main(sys.argv[2:]))
    """
)


@posix_only
# was: xfail(strict) D8-OFF-04 - fixed in Phase 12D9
def test_a_build_killed_in_the_rename_window_keeps_the_previous_pair(fake_docker, repo, tmp_path):
    old_pkg, _ = T._build(repo, tmp_path)
    out = old_pkg.parent
    stage, pkg, sha = _pair(out)
    old_bytes, old_sha = pkg.read_bytes(), sha.read_text()
    shutil.rmtree(stage)
    T._label_image(repo)
    proc = subprocess.run(
        [sys.executable, "-c", KILLED_BUILD.format(scripts=str(SCRIPTS)), str(pkg),
         "build", "--version", "1.3.0-rc.1", "--image", "chatbot5400:1.3.0-rc.1",
         "--repo", str(repo), "--out", str(out)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    assert proc.returncode == 137, proc.stdout + proc.stderr
    assert pkg.read_bytes() == old_bytes  # the previous package itself survives (true today)
    # EXPECTED: ... together with its hash, now or after the next build of this name
    if not sha.exists():
        shutil.rmtree(stage, ignore_errors=True)
        T._label_image(repo)
        T._build_rc(repo, out)  # the next build holds the lock: it could repair / clean up
    assert sha.is_file() and not list(out.glob("*.previous-*"))
    assert sha.read_text() in (old_sha, f"{OP.sha256_file(pkg)}  {pkg.name}\n")


# --------------------------------------------------------------------------- #
# 3. Package trust
# --------------------------------------------------------------------------- #


def test_control_a_sidecar_hash_next_to_the_package_authenticates_nothing(package, tmp_path):
    """`verify` never reads <package>.sha256: an unsigned package with its sidecar
    in place and no --expected-sha256 is refused and NOTHING is unpacked; the
    refusal says why. With the trusted-channel value it verifies."""
    pkg, digest = package
    sidecar = pkg.with_name(pkg.name + ".sha256")
    assert sidecar.read_text() == f"{digest}  {pkg.name}\n"
    dest = tmp_path / "unpacked"
    assert T._verify(pkg, dest) == OP.EXIT_VERIFY
    assert not dest.exists() and not list(tmp_path.glob("unpacked*"))
    src = (SCRIPTS / "offline_package.py").read_text(encoding="utf-8")
    assert "travelled with the package is NOT a trusted channel" in src
    assert T._verify(pkg, dest, "--expected-sha256", digest) == 0


def _manual_step_3_commands() -> str:
    """The commands of manual §3.4 - §3.5 exactly as the document gives them (the
    tar / cd / ssh-keygen lines are left out: no ssh-keygen in this environment;
    the tests keep manifest.json byte-identical, so a signature over it stays valid)."""
    blocks = _bash_blocks(_section(MANUAL, "## 3. ", "## 4. "))
    lines = blocks[1].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("sha256sum -c SHA256SUMS"))
    end = next(i for i, line in enumerate(lines) if line.startswith('cd "$DEPLOY_DIR"'))
    return "\n".join(lines[start:end])


def _unpack_like_the_manual(pkg: Path, work: Path) -> Path:
    work.mkdir()
    subprocess.run(
        ["tar", "-xzf", str(pkg), "-C", str(work), "--no-same-owner", "--no-same-permissions"],
        check=True,
    )
    return work / NAME


def _run_step_3(root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _manual_step_3_commands()],
        cwd=root, capture_output=True, text=True, timeout=60,
        env=dict(os.environ, NOTES=str(tmp_path / "notes.txt")),
    )  # fmt: skip


@posix_only
def test_control_manual_steps_3_1_and_3_4_on_an_untouched_package(package, tmp_path):
    """Manual §3.1 as written (`echo "<sha>  <file>" | sha256sum -c -`) accepts the
    package and refuses it after ONE flipped byte - before anything is unpacked;
    §3.4 / §3.5 as written pass on the untouched tree and §3.4 catches a changed
    file when SHA256SUMS is left alone."""
    pkg, digest = package
    check = f'echo "{digest}  {pkg.name}" | sha256sum -c -'
    ok = subprocess.run(["bash", "-c", check], cwd=pkg.parent, capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout.strip() == f"{pkg.name}: OK"
    bad = tmp_path / "bad"
    bad.mkdir()
    data = bytearray(pkg.read_bytes())
    data[len(data) // 2] ^= 1
    (bad / pkg.name).write_bytes(bytes(data))
    assert subprocess.run(["bash", "-c", check], cwd=bad, capture_output=True).returncode != 0
    root = _unpack_like_the_manual(pkg, tmp_path / "work")
    done = _run_step_3(root, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "provenance verified" in done.stdout and "readiness READY" in done.stdout
    (root / "images" / "chatbot5400-1.3.0-rc.1.tar").write_bytes(b"changed")
    assert _run_step_3(root, tmp_path).returncode != 0


@posix_only
# was: xfail(strict) D8-OFF-05 - fixed in Phase 12D9
def test_manual_step_3_binds_the_files_to_the_signed_manifest(package, tmp_path):
    pkg, _ = package
    root = _unpack_like_the_manual(pkg, tmp_path / "work")
    manifest_before = (root / "manifest.json").read_bytes()
    image = root / "images" / "chatbot5400-1.3.0-rc.1.tar"
    image.write_bytes(b"not the image that was built")
    (root / "scripts" / "json.py").write_text("raise SystemExit('planted module ran')\n")
    lines = []
    for line in (root / "SHA256SUMS").read_text().splitlines():
        rel = line.split("  ", 1)[1]
        lines.append(f"{OP.sha256_file(root / rel)}  {rel}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    assert (root / "manifest.json").read_bytes() == manifest_before  # §3.3 would still say Good
    done = _run_step_3(root, tmp_path)
    assert done.returncode != 0, "the manual checks accepted a swapped image and a planted file"


@posix_only
# was: xfail(strict) D8-OFF-06 - fixed in Phase 12D9
def test_build_notices_a_migration_added_since_the_base_ref(fake_docker, repo, tmp_path):
    migrations = repo / "open_notebook" / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "34.surrealql").write_text("DEFINE FIELD added ON source TYPE option<string>;\n")
    T._git(repo, "add", ".")
    T._git(repo, "commit", "-qm", "a release with a new migration")
    inventory = fake_docker.get()["inventory"]
    inventory["schema_version"] = 34
    fake_docker.set(inventory=inventory)
    out = tmp_path / "dist"
    T._label_image(repo)
    rc = T._build_rc(repo, out)  # exactly the arguments the official wrappers pass
    if rc == 0:
        manifest = T._manifest_of(next(out.glob("*.tar.gz")))
        assert manifest["database"]["migration_required"] is True
        assert manifest["rollback"]["app_rollback_without_restore"] is False


def test_control_wrappers_cannot_declare_a_migration():
    """Evidence for D8-OFF-06: neither official build script can pass the switch."""
    assert "--migration-required" not in (SCRIPTS / "build-package.sh").read_text()
    assert "migration" not in BUILD_PS1.read_text().lower()
    manual = MANUAL.read_text(encoding="utf-8")
    assert "migration_required" in _section(MANUAL, "## 3. ", "## 4. ")
    # no manual step reads the schema version of the running database
    assert "get_latest_version" not in manual and "--current-schema" not in manual


# --------------------------------------------------------------------------- #
# 4. Manual fallback procedure (the production path)
# --------------------------------------------------------------------------- #


def test_control_manual_compose_commands_never_build_pull_or_touch_the_database():
    """Every command of the manual procedure that goes through Docker Compose:
    read-only (`ps`, `logs`) or the one recreate, which carries --no-deps
    --no-build --pull never and names only the application. No `down`, no `-v`,
    no `pull`, no `build`, no `git pull`, no prune in any command block.
    ($OPS normal / maintenance is the operator's own script: LOCAL.)"""
    text = MANUAL.read_text(encoding="utf-8")
    commands = "\n".join(_bash_blocks(text))
    compose = [line for line in commands.splitlines() if "$DC" in line or "docker compose" in line]
    assert compose
    recreate = [line for line in compose if re.search(r"\bup\b", line)]
    assert len(recreate) == 1
    for flag in ("--no-deps", "--no-build", "--pull never", "--force-recreate", '"$APP"'):
        assert flag in recreate[0]
    for line in compose:
        if line in recreate or line.startswith("DC="):
            continue
        assert re.search(r"\$DC (ps -q|logs --tail)", line), line
    executed = "\n".join(  # without comments ("KHONG git pull" is a comment)
        line.split("  #")[0] for line in commands.splitlines() if not line.lstrip().startswith("#")
    )
    for bad in (" down", "compose pull", "compose build", "git pull", " prune", "volume rm",
                "--volumes", "docker pull", "pip install", "apt-get", "curl http"):  # fmt: skip
        assert bad not in executed, bad
    # order: authenticate (3.1) before unpacking (3.2); backup section before the tag moves
    assert commands.index("sha256sum -c -") < commands.index("tar -xzf")
    assert text.index("## 6. ") < text.index('docker tag "chatbot5400:$VER" "$DEPLOY_TAG"')
    assert commands.index("rollback-before-$VER") < commands.index('docker tag "chatbot5400:$VER" "$DEPLOY_TAG"')


@posix_only
# was: xfail(strict) D8-OFF-07 - fixed in Phase 12D9
def test_manual_work_folder_command_refuses_a_folder_somebody_else_prepared(tmp_path):
    if os.geteuid() != 0:
        pytest.skip("needs root to hand a folder to another uid")
    block = _bash_blocks(_section(MANUAL, "## 3. ", "## 4. "))[0]
    command = next(line for line in block.splitlines() if "$WORK" in line and "install" in line)
    work = tmp_path / "cb5400-1.3.0"
    work.mkdir()
    os.chown(work, 65534, 65534)  # prepared by another local user
    os.chmod(work, 0o777)
    done = subprocess.run(["bash", "-c", command], env=dict(os.environ, WORK=str(work)))
    assert done.returncode != 0 or work.stat().st_uid == 0


def _snapshot(updated_hash: str) -> dict:
    table = {"count": 2, "ids_sha256": "a" * 64, "updated_sha256": updated_hash}
    return {
        "schema": 1,
        "kind": "chatbot5400-offline-snapshot",
        "db": {"container_id": "db", "image_id": "i", "mounts": [], "volumes": {}, "binds": {},
               "started_at": "t0", "running": True},
        "app": {"image_id": "old"},
        "deploy_tag": {"image_id": "old"},
        "data": {"tables": {"source": table}, "sha256": updated_hash},
        "counts": {"source": 2},
        "records": {"source": ["source:1", "source:2"]},
        "artifacts": None,
        "unreadable": [],
    }  # fmt: skip


# was: xfail(strict) D8-OFF-08 - fixed in Phase 12D9
def test_snapshot_compare_reports_records_changed_in_place():
    before, after = _snapshot("1" * 64), _snapshot("2" * 64)
    rc, lines = OP.compare_snapshots(before, after)
    assert rc != OP.EXIT_OK or any("chang" in line.lower() for line in lines), (rc, lines)


def test_control_snapshot_compare_reports_a_lost_record_and_another_database():
    before, after = _snapshot("1" * 64), _snapshot("1" * 64)
    assert OP.compare_snapshots(before, after) == (OP.EXIT_OK, ["nothing was lost"])
    after["records"]["source"] = ["source:1"]
    rc, lines = OP.compare_snapshots(before, after)
    assert rc == OP.EXIT_UPDATE and "LOST source: 1 of 2" in lines[0]
    after = _snapshot("1" * 64)
    after["db"]["container_id"] = "another"
    assert OP.compare_snapshots(before, after)[0] == OP.EXIT_UPDATE
    after = _snapshot("1" * 64)
    after["records"] = None
    assert OP.compare_snapshots(before, after)[0] == OP.EXIT_VERIFY  # unreadable is never "ok"


# was: xfail(strict) D8-OFF-10 - fixed in Phase 12D9
def test_manual_rollback_restores_the_source_before_recreating_the_application():
    section = _section(MANUAL, "## 10. ", "## 11. ")
    assert section.index("reset --keep") < section.index("$OPS maintenance")


DOCKER_SHIM = """#!/usr/bin/env python3
import sys
argv = sys.argv[1:]
if "-c" in argv:  # `docker exec <container> /app/.venv/bin/python -c <code>`: is <code> Python at all?
    compile(argv[argv.index("-c") + 1], "<manual>", "exec")
    print("0")
"""


def _job_wait_block(dedent: bool) -> str:
    section = _section(MANUAL, "## 6. ", "## 7. ")
    block = re.search(r"^ *```bash\n(.*?)^ *```", section, flags=re.S | re.M).group(1)
    assert "FROM command WHERE status IN" in block
    return textwrap.dedent(block) if dedent else block


def _run_with_docker_shim(tmp_path: Path, script: str) -> subprocess.CompletedProcess:
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "docker").write_text(DOCKER_SHIM)
    (shim / "docker").chmod(0o755)
    env = dict(os.environ, PATH=f"{shim}{os.pathsep}{os.environ['PATH']}", DC="true", APP="app")
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)


@posix_only
def test_control_manual_job_wait_command_is_valid_when_copied_from_a_rendered_page(tmp_path):
    done = _run_with_docker_shim(tmp_path, _job_wait_block(dedent=True))
    assert done.returncode == 0 and done.stdout.strip() == "0", done.stderr


@posix_only
# was: xfail(strict) D8-OFF-13 - fixed in Phase 12D9
def test_manual_job_wait_command_works_when_copied_from_the_shipped_file(tmp_path):
    done = _run_with_docker_shim(tmp_path, _job_wait_block(dedent=False))
    assert done.returncode == 0 and done.stdout.strip() == "0", done.stderr.strip().splitlines()[-1:]


@posix_only
# was: xfail(strict) D8-OFF-14 - fixed in Phase 12D9
def test_manual_f1_f2_comparison_fails_when_the_data_was_not_read(tmp_path):
    section = _section(MANUAL, "## 6. ", "## 7. ")
    line = next(l.strip() for l in section.splitlines() if "F1 == F2" in l and "python3" in l)
    unread = {"kind": "chatbot5400-offline-snapshot", "data": None, "records": None,
              "unreadable": ["data fingerprint"]}  # fmt: skip
    for name in ("f1.json", "f2.json"):
        (tmp_path / name).write_text(json.dumps(unread))
    done = subprocess.run(["bash", "-c", line], env=dict(os.environ, WORK=str(tmp_path)),
                          capture_output=True, text=True, timeout=60)  # fmt: skip
    assert done.returncode != 0 and "F1 == F2" not in done.stdout, done.stdout


@posix_only
def test_control_manual_f1_f2_comparison_on_read_data(tmp_path):
    section = _section(MANUAL, "## 6. ", "## 7. ")
    line = next(l.strip() for l in section.splitlines() if "F1 == F2" in l and "python3" in l)

    def run(a, b):
        (tmp_path / "f1.json").write_text(json.dumps({"data": a, "taken_at": "t1"}))
        (tmp_path / "f2.json").write_text(json.dumps({"data": b, "taken_at": "t2"}))
        return subprocess.run(["bash", "-c", line], env=dict(os.environ, WORK=str(tmp_path)),
                              capture_output=True, text=True, timeout=60)  # fmt: skip

    same, other = OP.make_fingerprint({t: {"ids": ["x:1"], "updated": ["u1"]} for t in OP.RECORD_TABLES}), None
    other = OP.make_fingerprint({t: {"ids": ["x:1"], "updated": ["u2"]} for t in OP.RECORD_TABLES})
    ok = run(same["summary"], same["summary"])
    assert ok.returncode == 0 and ok.stdout.strip() == "F1 == F2"  # taken_at is not compared
    changed = run(same["summary"], other["summary"])  # same ids, another `updated`
    assert changed.returncode == 1 and "DIFFERENT" in changed.stdout


# was: xfail(strict) D8-OFF-15 - fixed in Phase 12D9
def test_adapter_contract_requires_no_deps_for_the_operations_script():
    contract = (DOCS / "OFFLINE_UPDATE_INTEGRATION_CONTRACT.md").read_text(encoding="utf-8")
    adapter = contract[contract.index("## 3. ") : contract.index("## 4. ")]
    normal = next(line for line in adapter.splitlines() if line.lstrip().startswith("1. `normal`"))
    following = adapter[adapter.index(normal) :].split("\n2. ")[0]
    assert "--no-deps" in following and "có thể kèm" not in following


# --------------------------------------------------------------------------- #
# 5. The automatic updater is EXPERIMENTAL - where is that said?
# --------------------------------------------------------------------------- #


def test_control_deployment_documents_mark_the_automatic_updater_experimental():
    for name in ("OFFLINE_UPDATE_UBUNTU_GUIDE.md", "OFFLINE_UPDATE_ROLLBACK.md",
                 "OFFLINE_UPDATE_PACKAGE.md", "OFFLINE_UPDATE_SECURITY.md",
                 "OFFLINE_UPDATE_MANUAL_FALLBACK.md"):  # fmt: skip
        head = "\n".join((DOCS / name).read_text(encoding="utf-8").splitlines()[:14])
        assert "EXPERIMENTAL" in head and "OFFLINE_UPDATE_MANUAL_FALLBACK" in head.replace(
            "Cập nhật offline thủ công", "OFFLINE_UPDATE_MANUAL_FALLBACK"
        ), name
    # the production procedure itself never calls the automatic commands
    commands = "\n".join(_bash_blocks(MANUAL.read_text(encoding="utf-8")))
    for auto in ("update.sh", "finish.sh", "rollback.sh", "preflight.sh", " update ", " finish ",
                 "offline_package.py verify"):  # fmt: skip
        assert auto not in commands, auto
    assert set(re.findall(r"offline_package\.py\" (\w+)", commands)) == {"snapshot"}


# was: xfail(strict) D8-OFF-01 - fixed in Phase 12D9
def test_the_tool_itself_says_the_automatic_updater_is_experimental():
    helps = [
        subprocess.run(
            [sys.executable, str(SCRIPTS / "offline_package.py"), *argv],
            capture_output=True, text=True, timeout=60,
        ).stdout
        for argv in (["--help"], ["update", "--help"], ["finish", "--help"], ["rollback", "--help"])
    ]  # fmt: skip
    assert all(h.strip() for h in helps)
    assert all("experimental" in h.lower() for h in helps)
    for wrapper in ("update.sh", "finish.sh", "rollback.sh"):
        assert "experimental" in (SCRIPTS / wrapper).read_text().lower(), wrapper


# was: xfail(strict) D8-OFF-02 - fixed in Phase 12D9
def test_release_notes_send_production_to_the_manual_procedure():
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    assert "OFFLINE_UPDATE_MANUAL_FALLBACK" in notes
    assert "EXPERIMENTAL" in notes


# --------------------------------------------------------------------------- #
# 6. PowerShell - STATIC text checks only (no PowerShell here; nothing below is
#    evidence of behaviour on Windows PowerShell 5.1 or PowerShell 7)
# --------------------------------------------------------------------------- #


def test_control_ps1_static_ascii_no_remaining_args_exit_codes_checked():
    """STATIC: both scripts are pure ASCII (Windows PowerShell 5.1 reads a file
    without BOM as ANSI: a UTF-8 dash or quote inside would change the parse);
    no ValueFromRemainingArguments; no `2>&1` on a native command; in
    build-package.ps1 no redirected stderr at all (R2-22) and $LASTEXITCODE is
    tested after every native command whose failure matters; files are written
    with an explicit -Encoding ascii (5.1 would write UTF-16 by default)."""
    for path in (BUILD_PS1, TEST_PS1):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf") and all(b < 0x80 for b in raw), path
        code = _ps_code(path)
        assert "ValueFromRemainingArguments" not in code and "2>&1" not in code
        assert "$ErrorActionPreference = 'Stop'" in code
        for line in code.splitlines():
            if re.search(r"\b(Set-Content|Out-File|Add-Content)\b", line):
                assert "-Encoding ascii" in line, line
    build = _ps_code(BUILD_PS1)
    assert "2>$null" not in build
    lines = build.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"^\s*& (\$exe|docker buildx|git rev-parse -q|git merge-base|docker image ls)", line):
            j = i
            while lines[j].rstrip().endswith("`"):
                j += 1
            assert "$LASTEXITCODE" in lines[j] + lines[j + 1], line
    # every compose call of phase12-test.ps1 goes through the ONE checked function
    test = _ps_code(TEST_PS1)
    body = test.split("function Invoke-Compose", 1)[1].split("\nfunction ", 1)[0]
    assert "@ComposeArgs" in body and "$LASTEXITCODE -ne 0" in body


# was: xfail(strict) D8-OFF-11 - fixed in Phase 12D9
def test_build_package_ps1_keeps_a_one_element_python_command_an_array():
    code = _ps_code(BUILD_PS1)
    assign = re.search(r"^.*\$python\s*=.*$", code, flags=re.M)
    assert assign, "no $python assignment found"
    line = assign.group(0)
    indexed = "$python[0]" in code
    protected = (
        "[string[]]$python" in line  # typed: a scalar is converted back to an array
        or re.search(r"\$python\s*=\s*@\(\s*if", line)  # @( if ... ) keeps an array
        or ",@('python')" in code.replace(" ", "")  # unary comma survives the pipeline
        or "@($python)[0]" in code
    )
    assert not indexed or protected, line.strip()


# was: xfail(strict) D8-OFF-12 - fixed in Phase 12D9
def test_phase12_test_ps1_has_no_native_command_with_redirected_stderr():
    assert "2>$null" not in _ps_code(TEST_PS1)


# --------------------------------------------------------------------------- #
# 7. What tests/test_phase12d7_build_lock.py does and does not prove
# --------------------------------------------------------------------------- #


def test_verified_the_d7_lock_tests_would_fail_without_a_lock(tmp_path, monkeypatch):
    """The D7 exclusivity tests are real: with the lock primitive disabled (flock
    always succeeds) two holders coexist, i.e. `pytest.raises(Refused)` of
    test_a_second_process_is_refused... / the 'exactly one wins' count would fail.
    What the D7 file does NOT cover: the msvcrt branch (never executed), a kill
    inside the rename window (D8-OFF-04), a failure after the package rename
    (D8-OFF-03)."""
    import fcntl

    out = tmp_path / "dist"
    out.mkdir()
    with OP.build_lock(out, NAME):
        with pytest.raises(OP.Refused):  # the real lock refuses a second open file
            with OP.build_lock(out, NAME):
                pass
        monkeypatch.setattr(fcntl, "flock", lambda fd, op: None)  # a lock that does nothing
        with OP.build_lock(out, NAME):  # ... is noticed: no Refused any more
            pass
    d7 = (ROOT / "tests" / "test_phase12d7_build_lock.py").read_text(encoding="utf-8")
    assert "msvcrt" not in d7.split('"""', 2)[2].replace('{"fcntl", "pwd", "grp", "termios", "resource", "msvcrt"}', "")
    assert "save_hang" in d7  # the only interruption point it exercises: inside `docker save`
