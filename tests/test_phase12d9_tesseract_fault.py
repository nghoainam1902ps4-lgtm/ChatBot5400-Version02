"""Phase 12D9: the E2-04 local-acceptance fault injector
(``scripts/ocr/phase12d9_tesseract_fault.sh``, test stack only).

It must change nothing without a control file, fail only RECOGNITION calls
(never OSD, ``--version`` or ``--list-langs``), fail exactly once with
``fail-once`` and every time with ``fail-always``; and the test stack must keep
the real Tesseract by default. Real ``tesseract`` binary, synthetic image.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "ocr" / "phase12d9_tesseract_fault.sh"
REAL = shutil.which("tesseract")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

pytestmark = pytest.mark.skipif(
    REAL is None or os.name != "posix" or not Path(FONT).is_file(),
    reason="needs a POSIX shell, the tesseract binary and DejaVu",
)


@pytest.fixture
def rig(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    image = tmp_path / "crop.png"
    im = Image.new("L", (520, 90), 255)
    ImageDraw.Draw(im).text(
        (10, 15), "ALPHA 2024", font=ImageFont.truetype(FONT, 48), fill=0
    )
    im.save(image, dpi=(216, 216))
    fault = tmp_path / "fault"
    fault.mkdir()
    env = dict(os.environ, CB5400_FAULT_DIR=str(fault), CB5400_REAL_TESSERACT=REAL)

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", str(WRAPPER), *args], capture_output=True, text=True, env=env
        )

    return run, image, fault


def _recognize(run, image):
    # the command line Docling builds (docling_patches._run_tesseract)
    return run("-l", "eng", "--psm", "6", str(image), "stdout", "tsv")


def test_without_a_control_file_every_call_is_the_real_one(rig):
    run, image, _fault = rig
    out = _recognize(run, image)
    assert out.returncode == 0 and "ALPHA" in out.stdout
    real = subprocess.run(
        [REAL, "-l", "eng", "--psm", "6", str(image), "stdout", "tsv"],
        capture_output=True,
        text=True,
    )
    assert out.stdout == real.stdout
    assert run("--version").returncode == 0


def test_fail_once_fails_one_recognition_then_passes(rig):
    run, image, fault = rig
    (fault / "fail-once").touch()
    first = _recognize(run, image)
    assert first.returncode == 1 and "fail-once" in first.stderr
    assert not (fault / "fail-once").exists()
    second = _recognize(run, image)
    assert second.returncode == 0 and "ALPHA" in second.stdout


def test_fail_always_fails_every_recognition_but_nothing_else(rig):
    run, image, fault = rig
    (fault / "fail-always").touch()
    for _ in range(3):
        assert _recognize(run, image).returncode == 1
    assert run("--version").returncode == 0
    assert run("--list-langs").returncode == 0
    # orientation detection is never failed (it ends with "stdout", not "tsv")
    osd = run("--psm", "0", "-l", "osd", str(image), "stdout")
    assert "injected" not in osd.stderr


def test_the_wrapper_is_lf_and_executable_and_the_stack_defaults_to_the_real_binary():
    data = WRAPPER.read_bytes()
    assert b"\r" not in data and data.startswith(b"#!/bin/sh\n")
    assert os.access(WRAPPER, os.X_OK)
    compose = (ROOT / "deploy" / "phase12-test" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "- OCR_TESSERACT_CMD=${PHASE12_TESSERACT_CMD:-tesseract}" in compose
    root_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "phase12d9_tesseract_fault" not in root_compose


def test_behind_the_orientation_gate_only_recognition_is_failed(rig):
    """The application calls the orientation gate (D-25), which ``exec``s the
    configured executable - the injector - with the arguments untouched."""
    _run, image, fault = rig
    gate = ROOT / "open_notebook" / "ocr" / "tesseract_gate.py"
    env = dict(
        os.environ,
        CB5400_FAULT_DIR=str(fault),
        CB5400_REAL_TESSERACT=REAL,
        OCR_TESSERACT_REAL=str(WRAPPER),
    )

    def via_gate(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(gate), *args], capture_output=True, text=True, env=env
        )

    (fault / "fail-once").touch()
    assert via_gate("--version").returncode == 0
    osd = via_gate("--psm", "0", "-l", "osd", str(image), "stdout")
    assert "injected" not in osd.stderr
    assert (fault / "fail-once").exists()  # OSD did not consume it
    rec = ["-l", "eng", "--psm", "6", str(image), "stdout", "tsv"]
    assert via_gate(*rec).returncode == 1
    assert via_gate(*rec).returncode == 0
