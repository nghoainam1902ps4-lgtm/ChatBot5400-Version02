"""Phase 12D8 final audit - Tesseract orientation gate (D-25 / D-40 / E1-05).

Review only: no runtime file is modified. Conventions (see conftest.py):

* ``xfail(strict=True)`` = EXPECTED safe behaviour that fails today
  (finding D8-ORI-xx);
* ``test_control_*`` / ``test_verified_*`` = something this audit checked for
  itself and that holds today.

Real Tesseract experiments skip when the binary (with ``vie`` + ``osd``) or the
fonts are missing. No Docker, no network, nothing written outside ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "open_notebook" / "ocr" / "tesseract_gate.py"
DOCKERFILE = ROOT / "Dockerfile"
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LONG = "Ngân hàng Nông nghiệp và Phát triển Nông thôn Việt Nam chi nhánh"
# An UPRIGHT three-line header for which Tesseract 5.3.4 answers "180 degrees"
# with a confidence of about 0.1 (found by this audit: 28 such crops out of 864
# synthetic upright crops, none with a confidence >= 2.0).
HEADER = ["NGÂN HÀNG NÔNG NGHIỆP", "VÀ PHÁT TRIỂN NÔNG THÔN", "VIỆT NAM"]

from open_notebook.ocr import options, tesseract_gate  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "phase12_orientation_diagnose_d8",
    ROOT / "scripts" / "ocr" / "phase12_orientation_diagnose.py",
)
assert _spec is not None and _spec.loader is not None
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)


def _tessdata() -> str | None:
    exe = shutil.which("tesseract")
    if not exe:
        return None
    env = {k: v for k, v in os.environ.items() if k != "TESSDATA_PREFIX"}
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, env=env)
    text = out.stdout + out.stderr
    where = re.search(r'"([^"]+)"', text)
    langs = set(text.split())
    if not where or "vie" not in langs or "osd" not in langs:
        return None
    return where.group(1)


REAL = shutil.which("tesseract")
TESSDATA = _tessdata()
needs_tesseract = pytest.mark.skipif(
    TESSDATA is None or not Path(DEJAVU).is_file(),
    reason="needs tesseract with 'vie' + 'osd' and the DejaVu font",
)


@pytest.fixture(autouse=True)
def _isolated_gate_env(monkeypatch, tmp_path):
    """tesseract_command() writes os.environ; OCR paths must stay in tmp_path."""
    monkeypatch.setenv(
        tesseract_gate.REAL_ENV, os.environ.get(tesseract_gate.REAL_ENV, "")
    )
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    monkeypatch.delenv(tesseract_gate.MIN_CONFIDENCE_ENV, raising=False)
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr-data"))
    monkeypatch.setenv("OCR_MODELS_DIR", str(tmp_path / "ocr-data" / "models"))
    # One OpenMP thread: same output, and no spin-wait collapse when other test
    # runs load the machine (Tesseract with 4 busy-waiting threads crawls then).
    monkeypatch.setenv("OMP_THREAD_LIMIT", "1")
    if TESSDATA:
        monkeypatch.setenv("TESSDATA_PREFIX", TESSDATA)
    else:
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)


def _crlf_copy(dest: Path, mode: int = 0o755) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(GATE.read_bytes().replace(b"\n", b"\r\n"))
    dest.chmod(mode)
    return dest


def _strip(path: Path, text: str, rotate: int = 0, font_px: int = 44) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(DEJAVU, font_px)
    img = Image.new("L", (int(font.getlength(text)) + 2 * font_px, 2 * font_px), 255)
    ImageDraw.Draw(img).text((font_px, font_px // 3), text, font=font, fill=0)
    img.rotate(rotate, expand=True).save(path)
    return path


def _header_crop(path: Path, px: int = 26, pad: int = 20) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(DEJAVU, px)
    w = int(max(font.getlength(line) for line in HEADER)) + 2 * pad
    h = int(px * 1.45 * len(HEADER)) + 2 * pad
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(HEADER):
        draw.text((pad, pad + int(i * px * 1.45)), line, font=font, fill=0)
    img.save(path)
    return path


def _osd(cmd: str, image: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [cmd, "--psm", "0", "-l", "osd", str(image), "stdout"],
        capture_output=True,
        env={**os.environ, tesseract_gate.REAL_ENV: str(REAL), **env},
        timeout=120,
    )


# --------------------------------------------------------------------------- #
# 1. Line endings, Dockerfile self-test
# --------------------------------------------------------------------------- #


def _runtime_base() -> str:
    text = DOCKERFILE.read_text(encoding="utf-8")
    return text.split("AS runtime-base", 1)[1].split("AS single", 1)[0]


def _gate_run_instruction() -> str:
    """The one RUN instruction of the Dockerfile that mentions the gate, joined."""
    joined = _runtime_base().replace("\\\n", " ")
    runs = [
        line
        for line in joined.splitlines()
        if line.startswith("RUN") and "tesseract_gate.py" in line
    ]
    assert len(runs) == 1
    return runs[0][len("RUN") :].strip()


def test_verified_dockerfile_gate_step_cannot_swallow_a_failure():
    """The D7 tests only look for the three commands. They would still pass with
    `|| true` appended, a pipe, or a later COPY that overwrites the repaired
    file. Checked here on the real Dockerfile: none of that is present."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    run = _gate_run_instruction()
    assert "||" not in run and ";" not in run and "|" not in run
    steps = [s.strip() for s in run.split("&&")]
    assert steps[-1] == (
        "OCR_TESSERACT_REAL=/bin/true /app/open_notebook/ocr/tesseract_gate.py "
        "--version >/dev/null"
    )  # the self-test is the last command: its status is the RUN status
    sed = steps.index("sed -i 's/\\r$//' /app/open_notebook/ocr/tesseract_gate.py")
    chmod = steps.index("chmod 0755 /app/open_notebook/ocr/tesseract_gate.py")
    assert sed < len(steps) - 1 and chmod < len(steps) - 1
    # both published targets are built on the stage that holds the step ...
    assert re.search(r"^FROM runtime-base AS single$", text, re.MULTILINE)
    assert text.rstrip().splitlines()[-1] == "FROM runtime-base AS runtime"
    # ... and nothing copies application sources over the repaired file later
    after = text.split("tesseract_gate.py --version", 1)[1]
    copies = [ln for ln in after.splitlines() if ln.startswith(("COPY", "ADD"))]
    assert copies == [
        "COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf",
        "COPY --from=surreal-binary /surreal /usr/local/bin/surreal",
    ]


def test_control_dockerfile_selftest_fails_on_a_crlf_or_non_executable_gate(tmp_path):
    """The exact self-test command of the Dockerfile (paths adapted), WITHOUT the
    sed / chmod repair before it: the build stops (127 for CRLF, 126 without the
    executable bit)."""
    selftest = _gate_run_instruction().split("&&")[-1].strip()
    app = tmp_path / "app"
    crlf = _crlf_copy(app / "open_notebook" / "ocr" / "tesseract_gate.py")
    cmd = selftest.replace("/app/", f"{app}/")
    proc = subprocess.run(["sh", "-c", f"true && {cmd}"], capture_output=True)
    assert proc.returncode == 127
    assert b"python3\\r" in proc.stderr or b"python3\r" in proc.stderr
    crlf.write_bytes(GATE.read_bytes())
    crlf.chmod(0o644)
    assert subprocess.run(["sh", "-c", cmd], capture_output=True).returncode == 126


def test_control_whole_dockerfile_run_instruction_repairs_a_windows_copy(tmp_path):
    """The complete RUN instruction as ONE `sh -c` (as Docker runs it), on a
    CRLF copy without the executable bit."""
    app = tmp_path / "app"
    copy = _crlf_copy(app / "open_notebook" / "ocr" / "tesseract_gate.py", 0o644)
    (app / "scripts").mkdir()
    for name in ("wait-for-api.sh", "docker-entrypoint.sh"):
        (app / "scripts" / name).write_text("#!/bin/sh\n")
    run = (
        _gate_run_instruction()
        .replace("/app/", f"{app}/")
        .replace("/var/log/supervisor", str(tmp_path / "log"))
    )
    assert subprocess.run(["sh", "-c", run], capture_output=True).returncode == 0
    assert copy.read_bytes() == GATE.read_bytes() and os.access(copy, os.X_OK)


def test_control_gitattributes_does_not_repair_an_existing_crlf_checkout(tmp_path):
    """D8-ORI-03. `.gitattributes` acts on checkout only. A Windows working tree
    cloned BEFORE Phase 12D7 keeps its CRLF gate after pulling the new
    `.gitattributes` (the blob did not change, Git does not rewrite the file,
    `git status` is clean). Only the Dockerfile's sed protects such a build."""
    if not shutil.which("git"):
        pytest.skip("git is not installed")

    def git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            env={
                **os.environ,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.invalid",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.invalid",
            },
        ).stdout

    origin = tmp_path / "origin"
    (origin / "open_notebook" / "ocr").mkdir(parents=True)
    git(origin, "init", "-q", "-b", "main", ".")
    rel = "open_notebook/ocr/tesseract_gate.py"
    (origin / rel).write_bytes(GATE.read_bytes())
    (origin / ".gitattributes").write_text("*.sh text eol=lf\n")  # as in v1.2.0
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "before 12D7")
    git(tmp_path, "-c", "core.autocrlf=true", "clone", "-q", "origin", "win")
    win = tmp_path / "win"
    git(win, "config", "core.autocrlf", "true")  # Git for Windows default
    assert "w/crlf" in git(win, "ls-files", "--eol", rel)
    (origin / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "12D7: gate eol=lf")
    git(win, "pull", "-q")
    eol = git(win, "ls-files", "--eol", rel)
    assert "attr/text eol=lf" in eol and "w/crlf" in eol  # still CRLF on disk
    assert (win / rel).read_bytes().startswith(b"#!/usr/bin/env python3\r\n")
    assert git(win, "status", "--short") == ""  # nothing tells the operator
    # a fresh clone at the new commit is fine
    git(tmp_path, "-c", "core.autocrlf=true", "clone", "-q", "origin", "win2")
    assert "w/lf" in git(tmp_path / "win2", "ls-files", "--eol", rel)


# --------------------------------------------------------------------------- #
# 2. Gate logic
# --------------------------------------------------------------------------- #

OSD = (
    "Page number: 0\nOrientation in degrees: {deg}\nRotate: {rot}\n"
    "Orientation confidence: {conf}\nScript: Latin\nScript confidence: 1.11\n"
)


def test_verified_threshold_is_2_and_unchanged_since_v1_2_0():
    assert tesseract_gate.DEFAULT_MIN_CONFIDENCE == 2.0
    assert tesseract_gate.min_confidence() == 2.0
    if not shutil.which("git") or not (ROOT / ".git").exists():
        return
    known = subprocess.run(
        ["git", "cat-file", "-e", "f2fdf27^{commit}"], cwd=ROOT, capture_output=True
    )
    if known.returncode != 0:
        return  # shallow checkout without the release baseline
    diff = subprocess.run(
        ["git", "diff", "--quiet", "f2fdf27", "HEAD", "--", str(GATE)], cwd=ROOT
    )
    assert diff.returncode == 0  # the gate file is byte-identical to v1.2.0


@pytest.mark.parametrize(
    "conf,gated",
    [
        ("2.00", False),  # exactly the threshold: Tesseract's answer is kept
        ("1.99", True),
        ("0.00", True),
        ("15.30", False),
        ("nan", True),  # unreadable confidence: never trusted
        ("inf", True),
        ("-1.00", True),
        ("0,71", True),  # decimal comma (foreign locale): not trusted either
    ],
)
def test_control_gate_decision_at_the_edges(conf, gated):
    out = tesseract_gate.gate_osd(OSD.format(deg=180, rot=180, conf=conf), 2.0)
    assert ("Orientation in degrees: 0\nRotate: 0\n" in out) is gated
    assert f"Orientation confidence: {conf}\nScript: Latin\n" in out  # rest intact
    assert out.count("\n") == 6


def test_control_gate_only_touches_psm_0_calls():
    assert tesseract_gate.is_osd_call(["--psm", "0", "-l", "osd", "a.png", "stdout"])
    for other in (
        ["--psm", "3", "a.png", "stdout", "tsv"],
        ["--psm", "06", "a.png", "stdout"],
        ["-l", "vie", "--tessdata-dir", "/x y", "0", "stdout", "tsv"],
        ["--version"],
        ["--list-langs"],
    ):
        assert not tesseract_gate.is_osd_call(other)


@needs_tesseract
def test_control_gate_through_its_shebang_equals_raw_tesseract(tmp_path):
    """Real Tesseract, the gate started the way Docling starts it (exec of the
    file): identical stdout / stderr / exit code for confident answers at 0, 90,
    180 and 270 degrees, for a failed OSD ("Too few characters"), for a
    recognition call with --tessdata-dir, -l a+b and a Unicode path with spaces,
    for --version / --list-langs and for a missing input file."""
    assert os.access(GATE, os.X_OK)
    seen = {}
    for name, rot in (("up", 0), ("ccw90", 90), ("r180", 180), ("ccw270", 270)):
        image = _strip(tmp_path / f"{name}.png", LONG, rotate=rot)
        raw, gated = _osd(str(REAL), image), _osd(str(GATE), image)
        assert raw.returncode == 0
        parsed = tesseract_gate.parse_osd(raw.stdout.decode())
        assert parsed is not None and parsed[1] >= 2.0
        seen[name] = parsed[0]
        assert (gated.returncode, gated.stdout, gated.stderr) == (
            raw.returncode,
            raw.stdout,
            raw.stderr,
        )
    # Tesseract's "Orientation in degrees" is the opposite of PIL's CCW angle
    assert seen == {"up": 0, "ccw90": 270, "r180": 180, "ccw270": 90}
    tiny = _strip(tmp_path / "tiny.png", "Trang 2")
    raw, gated = _osd(str(REAL), tiny), _osd(str(GATE), tiny)
    assert raw.returncode != 0 and b"Too few characters" in raw.stderr
    assert (gated.returncode, gated.stdout, gated.stderr) == (
        raw.returncode,
        raw.stdout,
        raw.stderr,
    )
    odd = tmp_path / "thư mục có dấu" / "tệp ảnh số 1.png"
    odd.parent.mkdir()
    shutil.copyfile(tmp_path / "up.png", odd)
    env = {**os.environ, tesseract_gate.REAL_ENV: str(REAL)}
    for args in (
        ["-l", "vie+eng", "--tessdata-dir", str(TESSDATA), str(odd), "stdout", "tsv"],
        ["--psm", "6", str(odd), "stdout"],
        ["--version"],
        ["--list-langs"],
        [str(tmp_path / "missing.png"), "stdout"],
        ["--psm", "0", "-l", "osd", str(tmp_path / "missing.png"), "stdout"],
    ):
        raw = subprocess.run([str(REAL), *args], capture_output=True, env=env)
        gated = subprocess.run([str(GATE), *args], capture_output=True, env=env)
        assert (gated.returncode, gated.stdout, gated.stderr) == (
            raw.returncode,
            raw.stdout,
            raw.stderr,
        ), args
    assert "Nông" in subprocess.run(
        [str(GATE), "-l", "vie", str(odd), "stdout"], capture_output=True, env=env
    ).stdout.decode("utf-8")


def test_control_gate_timeout_kills_tesseract_and_exits_124(tmp_path):
    """A REAL hanging child (the D7 test replaces subprocess.run): the gate
    returns 124 after its timeout and the child is gone."""
    pidfile = tmp_path / "pid"
    fake = tmp_path / "slow-tesseract"
    fake.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 60\n")
    fake.chmod(0o755)
    code = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(GATE.parent)!r})
        import tesseract_gate as g
        g.OSD_TIMEOUT_SECONDS = 1
        sys.exit(g.main(["--psm", "0", "-l", "osd", "x.png", "stdout"]))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env={**os.environ, tesseract_gate.REAL_ENV: str(fake)},
        timeout=30,
    )
    assert proc.returncode == 124 and b"timed out" in proc.stderr
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def _docling_model(cmd: str) -> Any:
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions
    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm

    return tm.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], path=TESSDATA, tesseract_cmd=cmd),
        accelerator_options=AcceleratorOptions(),
    )


@needs_tesseract
def test_control_doclings_own_osd_code_is_gated_and_a_crlf_gate_is_not(
    tmp_path, monkeypatch
):
    """End to end on Docling's real `_perform_osd` + `_parse_orientation`, real
    Tesseract, a REAL low-confidence wrong answer (the D7 stage test only uses a
    confident 180, which reads the same with and without the gate):

    * ungated  -> Docling would turn the upright header upside down (E1-05);
    * gate     -> 0 degrees, also with the E0-07 patch installed;
    * CRLF gate-> tesseract_command() hands Docling the real binary again."""
    pytest.importorskip("docling")
    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm

    from open_notebook.ocr import docling_patches

    crop = _header_crop(tmp_path / "header.png")
    raw = tesseract_gate.parse_osd(_osd(str(REAL), crop).stdout.decode())
    if raw is None or raw[0] != 180 or raw[1] >= 2.0:
        pytest.skip(f"this Tesseract build answers {raw} for the header crop")
    docling_patches.apply()  # E0-07: replaces _run_tesseract, not _perform_osd
    assert docling_patches.is_applied()
    assert tm.TesseractOcrCliModel._perform_osd.__module__ == tm.__name__

    def docling_rotation(cmd: str) -> int:
        model = _docling_model(cmd)
        return tm._parse_orientation(model._perform_osd(str(crop)))

    gate_cmd = options.tesseract_command(str(REAL))
    assert gate_cmd == str(GATE.resolve())
    assert docling_rotation(str(REAL)) == 180  # what an ungated image does
    assert docling_rotation(gate_cmd) == 0
    gated_words = " ".join(
        str(t) for t in _docling_model(gate_cmd)._run_tesseract(str(crop), None)["text"]
    )
    assert "NGÂN" in gated_words and "VIỆT NAM" in gated_words
    # the E1-05 mechanism: a CRLF copy cannot start -> silent fallback, ungated
    bad = _crlf_copy(tmp_path / "crlf" / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(bad))
    fallback = options.tesseract_command(str(REAL))
    assert fallback == str(REAL)
    assert docling_rotation(fallback) == 180


@needs_tesseract
def test_control_every_tesseract_engine_gets_the_gate(monkeypatch):
    """Fast, Best and the custom Agri engine: `tesseract_cmd` is the gate, and
    Docling's OSD call uses that same command (Standard and Legal share
    convert_document, so there is one place only)."""
    pytest.importorskip("docling")
    import inspect

    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm

    from open_notebook.ocr import catalog

    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    engines = [e for e, s in catalog.ENGINES.items() if s.docling_kind == "tesseract"]
    assert set(engines) >= {"tesseract_fast", "tesseract_best", "tesseract_agri"}
    for engine in engines:
        custom = "v1" if catalog.ENGINES[engine].custom is not None else None
        opts = options.build_ocr_options(engine, custom_version=custom)
        assert opts.tesseract_cmd == str(GATE.resolve()), engine
        assert opts.psm is None
    assert os.environ[tesseract_gate.REAL_ENV] == REAL
    # E0-07 replaced _run_tesseract by docling_patches._run_tesseract; the OSD
    # call is still upstream's. Both start `self._safe_tesseract_cmd`.
    from open_notebook.ocr import docling_patches

    assert docling_patches.is_applied()
    assert tm.TesseractOcrCliModel._perform_osd.__module__ == tm.__name__
    for method in (
        tm.TesseractOcrCliModel._perform_osd,
        docling_patches._run_tesseract,
    ):
        assert "cmd = [self._safe_tesseract_cmd]" in inspect.getsource(
            method
        ) or "self._safe_tesseract_cmd," in inspect.getsource(method)


# --------------------------------------------------------------------------- #
# 3. Is a gate that does not run visible?
# --------------------------------------------------------------------------- #


@needs_tesseract
def test_control_ocr_status_executes_the_gate_for_real(tmp_path, monkeypatch, capsys):
    """`ocr.cli status` (not a mocked state as in the D7 test): the last line
    comes from really starting the gate file."""
    from open_notebook.ocr import cli

    assert cli.main(["status", "--no-db"]) == 0
    assert capsys.readouterr().out.rstrip().splitlines()[-1] == (
        "orientation gate: active (min confidence 2.0)"
    )
    bad = _crlf_copy(tmp_path / "crlf" / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(bad))
    assert cli.main(["status", "--no-db"]) == 0  # still exit code 0
    last = capsys.readouterr().out.rstrip().splitlines()[-1]
    assert last.startswith("orientation gate: NOT ACTIVE") and "CRLF" in last


@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-02: readiness' quality fingerprint reports osd_gate=True from "
    "the environment variable alone, also when the gate cannot start",
)
def test_readiness_quality_reports_the_gate_that_really_runs(tmp_path, monkeypatch):
    from open_notebook.ocr import readiness

    bad = _crlf_copy(tmp_path / "crlf" / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(bad))
    state = options.tesseract_gate_state("/bin/true")
    assert state["enabled"] is True and state["active"] is False  # precondition
    # pdf_prep.orientation_status(): "never reported as working because of
    # configuration alone" - the same must hold for the gate
    assert readiness.quality_config("tesseract_best")["osd_gate"] is False


@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-02: `ocr.cli status --json` carries no orientation-gate state "
    "(text mode only), so automation cannot see an inactive gate",
)
def test_status_json_carries_the_gate_state(tmp_path, monkeypatch, capsys):
    from open_notebook.ocr import cli

    bad = _crlf_copy(tmp_path / "crlf" / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(bad))
    assert cli.main(["status", "--no-db", "--json"]) == 0
    out = capsys.readouterr().out
    json.loads(out)  # the JSON itself is valid
    assert "gate" in out.lower()


# --------------------------------------------------------------------------- #
# 4. The diagnostic tool and sideways crops (D8-ORI-01)
# --------------------------------------------------------------------------- #


def _docling_way(image: Any, tesseract_degrees: int) -> Any:
    """What Docling 2.129.0 does with Tesseract's "Orientation in degrees"."""
    from docling.models.stages.ocr.tesseract_utils import parse_tesseract_orientation

    doc_orientation = parse_tesseract_orientation(str(tesseract_degrees))
    return image.rotate(-doc_orientation, expand=True)


@pytest.mark.parametrize(
    "degrees",
    [
        pytest.param(
            90,
            marks=pytest.mark.xfail(
                strict=True,
                reason="D8-ORI-01: rotated_copy() turns a 90-degree answer the "
                "opposite way to Docling (the result is upside down)",
            ),
        ),
        180,
        pytest.param(
            270,
            marks=pytest.mark.xfail(
                strict=True,
                reason="D8-ORI-01: rotated_copy() turns a 270-degree answer the "
                "opposite way to Docling (the result is upside down)",
            ),
        ),
    ],
)
def test_tool_rotates_a_crop_exactly_like_docling(tmp_path, degrees):
    """The tool passes Tesseract's raw "Orientation in degrees" to rotated_copy()
    (crops mode: the applied rotation; both modes: the refused alternative)."""
    pytest.importorskip("docling")
    from PIL import Image

    src = tmp_path / "src.png"
    img = Image.new("L", (40, 20), 255)
    img.putpixel((3, 2), 0)  # an asymmetric mark
    img.save(src)
    TOOL.rotated_copy(src, degrees, tmp_path / "tool.png")
    with Image.open(tmp_path / "tool.png") as tool:
        expected = _docling_way(img, degrees)
        assert tool.size == expected.size
        assert tool.tobytes() == expected.tobytes()


def _run_crops(tmp_path: Path, crops: Path) -> tuple[list, dict]:
    out = tmp_path / "out"
    rc = TOOL.main(
        [
            "--crops",
            str(crops),
            "--out",
            str(out),
            "--lang",
            "vie",
            "--tessdata",
            str(TESSDATA),
        ]
    )
    assert rc == 0
    return (
        json.loads((out / "orientation_crops.json").read_text(encoding="utf-8")),
        json.loads((out / "orientation_summary.json").read_text(encoding="utf-8")),
    )


def _sideways(tmp_path: Path, pil_ccw: int) -> tuple[Path, int]:
    """A confidently detected sideways crop + Tesseract's answer for it; skips
    unless the Docling rotation of that answer reads the Vietnamese text."""
    from PIL import Image

    from open_notebook.ocr import docling_patches

    crops = tmp_path / "crops"
    crops.mkdir()
    image = _strip(crops / "sideways.png", LONG, rotate=pil_ccw)
    parsed = tesseract_gate.parse_osd(_osd(str(REAL), image).stdout.decode())
    if parsed is None or parsed[0] not in (90, 270) or parsed[1] < 2.0:
        pytest.skip(f"this Tesseract build answers {parsed} for the sideways crop")
    upright = tmp_path / "docling_way.png"
    with Image.open(image) as im:
        _docling_way(im, parsed[0]).save(upright)
    tsv = subprocess.run(
        [
            str(REAL),
            "-l",
            "vie",
            "--tessdata-dir",
            str(TESSDATA),
            str(upright),
            "stdout",
            "tsv",
        ],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    words = " ".join(str(t) for t in docling_patches.read_tesseract_tsv(tsv)["text"])
    if "Nông" not in words:
        pytest.skip("ingestion's rotation does not read this crop either")
    return crops, parsed[0]


@needs_tesseract
@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-01: crops mode rotates a 90/270 crop the wrong way, so its "
    "'applied' reading is upside-down garbage where ingestion reads the text",
)
def test_crops_mode_reads_a_sideways_crop_like_ingestion(tmp_path, monkeypatch):
    pytest.importorskip("docling")
    monkeypatch.setenv(tesseract_gate.REAL_ENV, str(REAL))
    crops, _ = _sideways(tmp_path, pil_ccw=90)  # Tesseract answers 270
    records, _ = _run_crops(tmp_path, crops)
    assert records[0]["applied_rotation"] and "rotated" in records[0]["flags"]
    assert "Nông" in records[0]["ocr_applied"]["text"]


@needs_tesseract
@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-01: crops mode accuses a CORRECT confident sideways rotation "
    "('candidates for a WRONG rotation above the threshold')",
)
def test_crops_mode_does_not_accuse_a_correct_sideways_rotation(tmp_path, monkeypatch):
    pytest.importorskip("docling")
    monkeypatch.setenv(tesseract_gate.REAL_ENV, str(REAL))
    crops, _ = _sideways(tmp_path, pil_ccw=270)  # Tesseract answers 90
    records, summary = _run_crops(tmp_path, crops)
    assert "alternative_reads_better" not in records[0]["flags"]
    assert summary["hint"] == "no evidence of a wrong rotation in this run."


def _probe_docling_stage(
    tmp_path: Path, pil_ccw: int
) -> tuple[Any, list[str], list[str]]:
    """PDF mode's probe on Docling's real OCR stage (one layout region holding a
    sideways line): (probe, cells through ingestion's command, cells ungated)."""
    from typing import cast

    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import (
        BoundingBox,
        Cluster,
        InputFormat,
        LayoutPrediction,
        Page,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.pipeline_options import OcrMode, TesseractCliOcrOptions
    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm
    from docling_core.types.doc import DocItemLabel
    from PIL import Image

    from open_notebook.ocr import docling_patches

    with Image.open(_strip(tmp_path / "s.png", LONG, rotate=pil_ccw)) as strip:
        page_img = Image.new("L", (2480, 3508), 255)
        page_img.paste(strip, (120, 100))
        k = 72 / 300
        box = BoundingBox(
            l=120 * k, t=100 * k, r=(120 + strip.width) * k, b=(100 + strip.height) * k
        )
    pdf = tmp_path / "page.pdf"
    page_img.save(pdf, "PDF", resolution=300)
    docling_patches.apply()

    def run_stage(cmd: str) -> list[str]:
        in_doc = InputDocument(
            path_or_stream=pdf, format=InputFormat.PDF, backend=PyPdfiumDocumentBackend
        )
        conv = ConversionResult(input=in_doc)
        page = Page(page_no=1)
        page._backend = cast(Any, in_doc._backend).load_page(0)
        page.size = page._backend.get_size()
        page.predictions.layout = LayoutPrediction(
            clusters=[
                Cluster(
                    id=0, label=DocItemLabel.TEXT, bbox=box, confidence=0.9, cells=[]
                )
            ]
        )
        model = tm.TesseractOcrCliModel(
            enabled=True,
            artifacts_path=None,
            options=TesseractCliOcrOptions(
                lang=["vie"],
                path=TESSDATA,
                tesseract_cmd=cmd,
                mode=OcrMode.LAYOUT_REGIONS,
            ),
            accelerator_options=AcceleratorOptions(),
        )
        list(model(conv, [page]))
        return [c.text for c in page.cells]

    gate_cmd = options.tesseract_command(str(REAL))
    assert gate_cmd == str(GATE.resolve())
    out = tmp_path / "probe"
    out.mkdir()
    probe = TOOL.OrientationProbe(out, options.tesseract_gate_state(str(REAL)))
    with probe:
        gated = run_stage(gate_cmd)
    ungated = run_stage(str(REAL))
    return probe, gated, ungated


@needs_tesseract
@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-01: PDF mode records 'gate_would_pass' in Tesseract's angle "
    "and 'applied_rotation' in Docling's (360 - angle): 270 vs 90 for one crop",
)
def test_pdf_mode_reports_one_angle_convention(tmp_path):
    pytest.importorskip("docling")
    probe, gated, _ = _probe_docling_stage(tmp_path, pil_ccw=90)
    rec = probe.records[0]
    if (
        rec["osd_raw"]["orientation"] not in (90, 270)
        or rec["osd_raw"]["confidence"] < 2.0
    ):
        pytest.skip(f"this Tesseract build answers {rec['osd_raw']}")
    assert "Nông" in " ".join(gated)  # ingestion itself reads the region
    assert rec["gate_would_pass"] == rec["osd_raw"]["orientation"]
    assert rec["applied_rotation"] == rec["gate_would_pass"]


@needs_tesseract
@pytest.mark.xfail(
    strict=True,
    reason="D8-ORI-01: for a refused 90/270 rotation the tool reads the "
    "'alternative' upside down, so it reports 'no evidence of a wrong rotation' "
    "although the ungated reading is the correct text",
)
def test_pdf_mode_shows_that_a_refused_sideways_rotation_read_better(
    tmp_path, monkeypatch
):
    pytest.importorskip("docling")
    monkeypatch.setenv(tesseract_gate.MIN_CONFIDENCE_ENV, "50")  # refuse everything
    probe, gated, ungated = _probe_docling_stage(tmp_path, pil_ccw=90)
    rec = probe.records[0]
    if "Nông" not in " ".join(ungated) or "Nông" in " ".join(gated):
        pytest.skip("this Tesseract build reads the unrotated sideways crop")
    assert rec["applied_rotation"] == 0
    summary = TOOL._finalize(probe.records, [], True)
    assert "rotation_refused_by_gate" in rec["flags"]  # holds today
    assert "alternative_reads_better" in rec["flags"]
    assert "too strict" in TOOL._hint(probe.gate, summary)
