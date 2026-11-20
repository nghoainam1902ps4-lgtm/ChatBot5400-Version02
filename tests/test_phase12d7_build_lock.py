"""E1-04 (Phase 12D7): the offline package lock works on Windows and Linux.

``build_lock`` imported ``fcntl``, which does not exist on Windows: the package
build stopped on Windows PowerShell 5.1 and 7. ``exclusive_lock`` uses flock()
on Linux / macOS and msvcrt.locking() on Windows. These tests use REAL
processes (no mocked platform): exclusivity, a race of many processes, release
when the holder is killed, a refused process leaves the holder's file alone, an
interrupted build keeps the previous package and frees the lock, a failed final
rename keeps the previous package WITH its hash.

On Linux they exercise the flock() branch. The lock tests are written to run
unchanged on Windows (``python -m pytest tests/test_phase12d7_build_lock.py``
in PowerShell, msvcrt branch); the build tests need the POSIX fake ``docker``
and are skipped there. Passing here is NOT evidence that Windows passes.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "offline"
sys.path.insert(0, str(SCRIPTS))

import offline_package as OP  # noqa: E402

POSIX = sys.platform != "win32"
if POSIX:  # the fake docker of the build tests is a POSIX script
    import test_offline_package as T
    from test_offline_package import fake_docker, repo  # noqa: F401

NAME = "ChatBot5400-1.3.0-rc.1-linux-amd64-offline"

CHILD = textwrap.dedent(
    """\
    import sys, time
    from pathlib import Path
    sys.path.insert(0, {scripts!r})
    import offline_package as OP
    kind, target, go, mark, hold = sys.argv[1:6]
    target, go, mark = Path(target), Path(go), Path(mark)
    while not go.exists():
        time.sleep(0.01)
    lock = OP.build_lock(target, {name!r}) if kind == "build" else OP.update_lock(target)
    try:
        with lock:
            mark.write_text("GOT")
            time.sleep(float(hold))
    except OP.Refused as e:
        mark.write_text("REFUSED " + str(e) + " code=" + str(e.code))
    """
)


def _child(tmp_path, kind, target, go, i, hold=30.0):
    mark = tmp_path / f"mark-{i}"
    code = CHILD.format(scripts=str(SCRIPTS), name=NAME)
    proc = subprocess.Popen(
        [sys.executable, "-c", code, kind, str(target), str(go), str(mark), str(hold)],
        stdin=subprocess.DEVNULL,
    )
    return proc, mark


def _wait_for(path: Path, timeout: float = 60.0) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.02)
    raise AssertionError(f"{path} never written")


def _target(tmp_path, kind):
    target = tmp_path / ("dist" if kind == "build" else "state")
    target.mkdir(exist_ok=True)
    return target


def _lock_file(target, kind):
    return target / (f".{NAME}.lock" if kind == "build" else "update.lock")


def _lock(target, kind):
    return OP.build_lock(target, NAME) if kind == "build" else OP.update_lock(target)


@pytest.mark.parametrize("kind", ["build", "update"])
def test_a_second_process_is_refused_while_the_first_holds_the_lock(tmp_path, kind):
    target = _target(tmp_path, kind)
    go = tmp_path / "go"
    go.write_text("go")
    holder, mark = _child(tmp_path, kind, target, go, 0)
    try:
        assert _wait_for(mark) == "GOT"
        with pytest.raises(OP.Refused) as refused:
            with _lock(target, kind):
                pass
        assert refused.value.code == OP.EXIT_LOCK
        assert f"held by process {holder.pid}" in str(refused.value)
        # the refused process did not touch what the holder wrote (no truncation)
        assert _lock_file(target, kind).read_text().strip() == str(holder.pid)
    finally:
        holder.kill()
        holder.wait(timeout=30)


@pytest.mark.parametrize("kind", ["build", "update"])
def test_the_lock_is_released_when_the_holder_is_killed(tmp_path, kind):
    target = _target(tmp_path, kind)
    go = tmp_path / "go"
    go.write_text("go")
    holder, mark = _child(tmp_path, kind, target, go, 0, hold=600)
    assert _wait_for(mark) == "GOT"
    holder.kill()  # SIGKILL / TerminateProcess: no cleanup code runs
    holder.wait(timeout=30)
    started = time.monotonic()
    with _lock(target, kind):  # taken at once: the operating system released it
        assert _lock_file(target, kind).read_text().strip() == str(os.getpid())
    assert time.monotonic() - started < 5
    assert _lock_file(target, kind).exists()  # never deleted


@pytest.mark.parametrize("kind", ["build", "update"])
def test_many_processes_racing_exactly_one_wins(tmp_path, kind):
    target = _target(tmp_path, kind)
    go = tmp_path / "go"
    procs = [_child(tmp_path, kind, target, go, i, hold=4.0) for i in range(8)]
    try:
        time.sleep(0.5)  # every child is waiting for the start signal
        go.write_text("go")
        results = [_wait_for(mark) for _, mark in procs]
    finally:
        for proc, _ in procs:
            proc.kill()
            proc.wait(timeout=30)
    assert results.count("GOT") == 1, results
    refused = [r for r in results if r.startswith("REFUSED")]
    assert len(refused) == 7
    assert all(f"code={OP.EXIT_LOCK}" in r and "held by" in r for r in refused)


def test_after_release_the_next_holder_gets_it(tmp_path):
    target = _target(tmp_path, "build")
    for _ in range(3):
        with OP.build_lock(target, NAME):
            with pytest.raises(
                OP.Refused
            ):  # same process, second open file: refused too
                with OP.build_lock(target, NAME):
                    pass


def test_a_lock_file_that_cannot_be_opened_is_a_clear_refusal(tmp_path):
    missing = tmp_path / "no-such-folder"
    with pytest.raises(OP.Refused, match="cannot open the lock file"):
        with OP.build_lock(missing, NAME):
            pass


def test_no_module_level_posix_only_import():
    """The tool must import on Windows: no fcntl / pwd / grp at module level."""
    import ast

    tree = ast.parse((SCRIPTS / "offline_package.py").read_text(encoding="utf-8"))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert not top & {"fcntl", "pwd", "grp", "termios", "resource", "msvcrt"}


# --------------------------------------------------------------------------- #
# Interrupted and failed builds (fake docker: POSIX only)
# --------------------------------------------------------------------------- #

posix_only = pytest.mark.skipif(not POSIX, reason="the fake docker is a POSIX script")


def _stage_and_pair(out):
    pkg = out / f"{NAME}.tar.gz"
    sha = out / f"{NAME}.tar.gz.sha256"
    return out / NAME, pkg, sha


@posix_only
def test_interrupted_build_keeps_the_previous_package_and_frees_the_lock(
    fake_docker, repo, tmp_path, capsys
):
    old_pkg, old_digest = T._build(repo, tmp_path)
    out = old_pkg.parent
    stage, pkg, sha = _stage_and_pair(out)
    old_bytes, old_sha = pkg.read_bytes(), sha.read_text()
    assert old_sha.startswith(old_digest)
    import shutil

    shutil.rmtree(stage)  # the operator's own step before a rebuild of the same version
    hang = tmp_path / "save-started"
    fake_docker.set(save_hang=str(hang))
    T._label_image(repo)
    builder = subprocess.Popen(
        [sys.executable, str(SCRIPTS / "offline_package.py"), "build", "--version", "1.3.0-rc.1",
         "--image", "chatbot5400:1.3.0-rc.1", "--repo", str(repo), "--out", str(out)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )  # fmt: skip
    try:
        _wait_for(hang)  # the second build is inside `docker save`
        with pytest.raises(OP.Refused, match=f"held by process {builder.pid}"):
            with OP.build_lock(out, NAME):
                pass
    finally:
        os.killpg(builder.pid, signal.SIGKILL)  # the builder AND its docker child
        builder.wait(timeout=30)
    # the previous package and its hash are untouched; the lock is free again
    assert pkg.read_bytes() == old_bytes and sha.read_text() == old_sha
    with OP.build_lock(out, NAME):
        pass
    # what the killed build left: its stage. The next build says what it is.
    assert stage.is_dir()
    fake_docker.set(save_hang=None)
    capsys.readouterr()
    assert T._build_rc(repo, out) == OP.EXIT_USAGE
    said = capsys.readouterr()
    assert "interrupted build" in said.out + said.err
    assert pkg.read_bytes() == old_bytes and sha.read_text() == old_sha
    # stale partial archives of THIS name are removed by the next build (it holds the
    # lock, so they belong to dead builds); another package's partial is not touched
    shutil.rmtree(stage)
    stale = out / f".{NAME}.tar.gz.partial-424242"
    stale.write_bytes(b"half an archive")
    other = out / ".ChatBot5400-9.9.9-linux-amd64-offline.tar.gz.partial-424242"
    other.write_bytes(b"another build")
    T._label_image(repo)
    assert T._build_rc(repo, out) == 0
    assert not stale.exists() and other.read_bytes() == b"another build"
    new_digest = OP.sha256_file(pkg)
    assert sha.read_text() == f"{new_digest}  {pkg.name}\n"
    assert not list(out.glob("*.previous-*"))


@posix_only
def test_a_failed_final_rename_keeps_the_previous_package_with_its_hash(
    fake_docker, repo, tmp_path, monkeypatch
):
    """Windows refuses to replace a file another program holds open (antivirus,
    Explorer): the previous package must keep its .sha256 (it was deleted first)."""
    old_pkg, _ = T._build(repo, tmp_path)
    out = old_pkg.parent
    stage, pkg, sha = _stage_and_pair(out)
    old_bytes, old_sha = pkg.read_bytes(), sha.read_text()
    import shutil

    shutil.rmtree(stage)
    real_replace = os.replace

    def replace(src, dst, *a, **kw):
        if Path(dst) == pkg:
            raise PermissionError(13, "The process cannot access the file")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(OP.os, "replace", replace)
    T._label_image(repo)
    with pytest.raises(PermissionError):
        T._build_rc(repo, out)
    monkeypatch.setattr(OP.os, "replace", real_replace)
    assert pkg.read_bytes() == old_bytes
    assert sha.read_text() == old_sha  # put back
    assert not stage.exists()  # only what this run created is removed
    assert not list(out.glob(".*partial-*")) and not list(out.glob("*.previous-*"))


@posix_only
def test_build_outputs_are_written_with_lf(fake_docker, repo, tmp_path):
    """Byte-identical outputs on Windows: the build writes its text files with LF
    (Python's text mode would write CRLF there)."""
    import tarfile

    pkg, digest = T._build(repo, tmp_path)
    sha = pkg.with_name(pkg.name + ".sha256")
    assert sha.read_bytes() == f"{digest}  {pkg.name}\n".encode()
    with tarfile.open(pkg) as tar:
        for member in (f"{NAME}/manifest.json", f"{NAME}/SHA256SUMS"):
            data = tar.extractfile(member).read()  # type: ignore[union-attr]
            assert b"\r" not in data and data.endswith(b"\n")
    src = (SCRIPTS / "offline_package.py").read_text(encoding="utf-8")
    build = src.split("def _build_stage(", 1)[1].split("\ndef ", 1)[0]
    assert (
        "write_text(" not in build
    )  # every text write of the stage goes through _write_lf
    assert 'newline="\\n"' in src.split("def atomic_write(", 1)[1].split("\ndef ", 1)[0]


if __name__ == "__main__":  # pragma: no cover - for a run on Windows
    sys.exit(pytest.main([__file__, "-q"]))
