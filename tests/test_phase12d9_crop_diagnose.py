"""Phase 12D9 (E2-01, E2-02): the OCR crop diagnostic - metadata only by default.

Runs the REAL Tesseract on synthetic crops (no document): the benchmark of the
short-token cases and of crops that must stay empty, the PROPOSED short-text
fallback measured (it is not in the pipeline), and the crop metrics of E2-02.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "phase12d9_crop_diagnose", ROOT / "scripts" / "ocr" / "phase12d9_crop_diagnose.py"
)
assert _spec and _spec.loader
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def _has_vie() -> bool:
    exe = shutil.which("tesseract")
    if not exe or not Path(C.FONT_CANDIDATES[0]).is_file():
        return False
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True)
    return "vie" in (out.stdout + out.stderr).split()


needs_tesseract = pytest.mark.skipif(
    not _has_vie(), reason="needs tesseract + vie + DejaVu"
)


def test_outcomes_count_false_insertion_and_false_recognition():
    assert C.outcome("9.", ["9."]) == "correct"
    assert C.outcome("9.", []) == "empty"
    assert C.outcome("9.", ["9"]) == "false recognition"
    assert C.outcome("", []) == "correct empty"
    assert C.outcome("", ["l1"]) == "false insertion"  # text on a stamp / signature
    assert C.outcome("đ).", ["đ)."]) == "correct"  # NFC


def test_the_proposed_fallback_never_replaces_text_and_needs_one_line_with_ink():
    line = {"height": 80, "width": 200, "ink_share": 0.05}
    tall = {"height": 400, "width": 200, "ink_share": 0.05}
    blank = {"height": 80, "width": 200, "ink_share": 0.0}
    psm3_text = {"rc": 0, "words": ["Điều"], "conf": [90.0]}
    psm3_empty = {"rc": 0, "words": [], "conf": []}
    psm3_failed = {"rc": 1, "words": [], "conf": []}
    psm7 = {"rc": 0, "words": ["9."], "conf": [80.0]}
    assert C.fallback(line, psm3_text, psm7) is psm3_text  # never replaces a result
    assert (
        C.fallback(line, psm3_failed, psm7) is psm3_failed
    )  # not for a failed run (E2-04)
    assert C.fallback(tall, psm3_empty, psm7) is psm3_empty  # not one line
    assert C.fallback(blank, psm3_empty, psm7) is psm3_empty  # no ink
    assert C.fallback(line, psm3_empty, psm7) is psm7


@needs_tesseract
def test_benchmark_is_metadata_only_by_default(tmp_path, capsys):
    out = tmp_path / "e201"
    assert C.main(["benchmark", "--lang", "vie", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    report_file = out / "crop_diagnose_benchmark.json"
    assert stat.S_IMODE(report_file.stat().st_mode) == 0o600
    report = json.loads(report_file.read_text(encoding="utf-8"))
    body = report_file.read_text(encoding="utf-8")
    for token in ("Điều", "Khoản", "05/2024", "đ).", "Hiệu lực"):
        assert token not in body and token not in printed, token
    assert all("words" not in r and "expected" not in r for r in report["rows"])
    kinds = {r["kind"] for r in report["rows"]}
    assert kinds == {"short", "empty", "multi"}
    # every row is measured four ways and the counts add up
    for key in ("psm3", "psm6", "psm7", "fallback"):
        assert sum(report["summary"][key].values()) == len(C.CASES)
    # the measures that matter are reported, not only "how many gave text"
    seen = {o for r in report["rows"] for o in r["outcomes"].values()}
    assert seen <= {
        "correct",
        "empty",
        "false recognition",
        "correct empty",
        "false insertion",
    }


@needs_tesseract
def test_benchmark_with_text_and_crops_mode(tmp_path):
    out = tmp_path / "e201"
    assert C.main(["benchmark", "--lang", "vie", "--out", str(out), "--with-text"]) == 0
    report = json.loads(
        (out / "crop_diagnose_benchmark.json").read_text(encoding="utf-8")
    )
    assert all("words" in r for r in report["rows"])
    crops = tmp_path / "crops"
    crops.mkdir()
    C.render_case("clause number", "9.", crops / "a.png")
    C.render_case("stamp", "", crops / "b.png")
    out2 = tmp_path / "e202"
    assert C.main(["crops", str(crops), "--lang", "vie", "--out", str(out2)]) == 0
    rows = json.loads((out2 / "crop_diagnose_crops.json").read_text(encoding="utf-8"))[
        "rows"
    ]
    assert [r["file"] for r in rows] == [None, None]  # no file name without --with-text
    for r in rows:
        assert {
            "width",
            "height",
            "ink_share",
            "contrast",
            "edge_energy",
            "ink_touches_edge",
        } <= set(r["stats"])
        assert set(r["psm"]) == {"psm3", "psm6", "psm7"}
        assert "words" not in r
