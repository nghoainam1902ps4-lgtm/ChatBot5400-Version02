"""E1-05 (Phase 12D7): small OCR crops rotated 180 degrees.

The orientation gate (D-25) is what keeps Docling from applying Tesseract's
low-confidence rotations to small crops. It runs through its ``#!`` line, so a
copy with Windows line endings cannot start and the app falls back to an
UNGATED Tesseract - exactly the reported symptom. These tests pin the line
endings, replay the Dockerfile repair step, check that the state is visible,
and exercise the diagnostic tool on the real Tesseract and on Docling's real
OCR stage (the tool must record without changing anything).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from open_notebook.ocr import options, tesseract_gate

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "open_notebook" / "ocr" / "tesseract_gate.py"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LONG = "Ngân hàng Nông nghiệp và Phát triển Nông thôn Việt Nam chi nhánh"

_spec = importlib.util.spec_from_file_location(
    "phase12_orientation_diagnose",
    ROOT / "scripts" / "ocr" / "phase12_orientation_diagnose.py",
)
assert _spec is not None and _spec.loader is not None
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)


def _tessdata() -> str | None:
    exe = shutil.which("tesseract")
    if not exe:
        return None
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    langs = set(text.split())
    where = re.search(r'"([^"]+)"', text)
    if not where or "vie" not in langs or "osd" not in langs:
        return None
    return where.group(1)


TESSDATA = _tessdata()
needs_tesseract = pytest.mark.skipif(
    TESSDATA is None or not Path(FONT).is_file(),
    reason="needs tesseract with 'vie' + 'osd' and the DejaVu font",
)


@pytest.fixture(autouse=True)
def _restore_real_tesseract_env(monkeypatch):
    """tesseract_command() sets OCR_TESSERACT_REAL process-wide (D-04)."""
    monkeypatch.setenv(
        tesseract_gate.REAL_ENV, os.environ.get(tesseract_gate.REAL_ENV, "")
    )


def _git(*args: str) -> str | None:
    if not shutil.which("git") or not (ROOT / ".git").exists():
        return None
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def _crlf_copy(dest: Path) -> Path:
    dest.write_bytes(GATE.read_bytes().replace(b"\n", b"\r\n"))
    dest.chmod(0o755)
    return dest


# --------------------------------------------------------------------------- #
# The cause: line endings of the gate
# --------------------------------------------------------------------------- #


def test_gate_is_committed_with_lf_endings_and_the_executable_bit():
    staged = _git("ls-files", "-s", "--", "open_notebook/ocr/tesseract_gate.py")
    if staged is None:
        pytest.skip("not a git checkout")
    assert staged.split()[0] == "100755"
    blob = subprocess.run(
        ["git", "cat-file", "-p", ":open_notebook/ocr/tesseract_gate.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    assert b"\r" not in blob
    assert blob.startswith(b"#!/usr/bin/env python3\n")


def test_gitattributes_keeps_lf_in_a_windows_checkout():
    """core.autocrlf=true (Git for Windows default) must not convert the gate."""
    attrs = _git("check-attr", "eol", "--", "open_notebook/ocr/tesseract_gate.py")
    if attrs is None:
        pytest.skip("not a git checkout")
    assert attrs.strip().endswith("eol: lf")


def test_a_crlf_gate_cannot_start(tmp_path):
    gate = _crlf_copy(tmp_path / "tesseract_gate.py")
    env = {**os.environ, tesseract_gate.REAL_ENV: "/bin/true"}
    crlf = subprocess.run([str(gate), "--version"], env=env, capture_output=True)
    assert crlf.returncode != 0
    # env names the interpreter "python3\r" (printed escaped or raw, per locale)
    assert b"python3\\r" in crlf.stderr or b"python3\r" in crlf.stderr
    ok = subprocess.run([str(GATE), "--version"], env=env, capture_output=True)
    assert ok.returncode == 0  # the committed file starts


def test_with_a_crlf_gate_the_app_runs_ungated_and_says_why(tmp_path, monkeypatch):
    """The fallback (D-25: never break OCR) is what made E1-05 silent."""
    gate = _crlf_copy(tmp_path / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(gate))
    assert options.tesseract_command("/bin/true") == "/bin/true"  # ungated
    state = options.tesseract_gate_state("/bin/true")
    assert state["enabled"] is True and state["active"] is False
    assert state["crlf"] is True and "CRLF" in state["reason"]


def test_the_committed_gate_is_active(monkeypatch):
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    state = options.tesseract_gate_state("/bin/true")
    assert state["active"] is True and state["reason"] is None
    assert state["crlf"] is False and state["min_confidence"] == 2.0


def test_disabled_gate_is_reported_as_disabled(monkeypatch):
    monkeypatch.setenv(options.TESSERACT_GATE_ENV, "false")
    state = options.tesseract_gate_state("/bin/true")
    assert state["active"] is False and "OCR_TESSERACT_OSD_GATE" in state["reason"]


def _dockerfile_gate_commands() -> list[str]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime = text.split("AS runtime-base", 1)[1].split("AS single", 1)[0]
    copy_at = runtime.index("COPY . /app")
    joined = runtime.replace("\\\n", " ")
    runs = [line for line in joined.splitlines() if "tesseract_gate.py" in line]
    assert len(runs) == 1, "one RUN step handles the gate"
    assert runtime.index("tesseract_gate.py") > copy_at  # after the sources
    steps = [s.strip() for s in runs[0].split("RUN", 1)[1].split("&&")]
    return [s for s in steps if "tesseract_gate" in s]


def test_the_dockerfile_repairs_and_self_tests_the_gate():
    steps = _dockerfile_gate_commands()
    assert any(s.startswith("sed -i 's/\\r$//'") for s in steps)
    assert any(s.startswith("chmod 0755") for s in steps)
    assert any("--version" in s and "OCR_TESSERACT_REAL=/bin/true" in s for s in steps)


def _gate_run_problems(dockerfile: str) -> list[str]:
    """Why the image could be built with a gate that does not start
    (D8-ORI-05, Phase 12D9): the self-test's failure swallowed, or the gate
    copied again after the repair."""
    runtime = dockerfile.split("AS runtime-base", 1)[1].split("AS single", 1)[0]
    joined = runtime.replace("\\\n", " ")
    lines = joined.splitlines()
    at = [i for i, line in enumerate(lines) if "tesseract_gate.py" in line]
    if len(at) != 1:
        return ["the gate is not handled by exactly one RUN step"]
    run = lines[at[0]]
    found = []
    tail = run[run.index("tesseract_gate.py --version") :]
    if "||" in run or ";" in tail or "|" in tail.replace("||", ""):
        found.append("the self-test's exit status can be ignored")
    if "set +e" in run:
        found.append("errors are switched off in the step")
    for line in lines[at[0] + 1 :]:
        words = line.split()
        if words[:1] == ["COPY"] and any(
            w in (".", "./", "open_notebook", "open_notebook/") or "tesseract_gate" in w
            for w in words[1:-1]
        ):
            found.append("the sources are copied again after the repair")
    return found


def test_the_gate_self_test_can_fail_the_build():
    """D8-ORI-05 (Phase 12D9): checked on the real Dockerfile and on the ways
    a build could swallow the self-test."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert _gate_run_problems(text) == []
    self_test = "tesseract_gate.py --version >/dev/null"
    for bad in (" || true", " || :", "; true", " | cat"):
        assert _gate_run_problems(text.replace(self_test, self_test + bad)), bad
    later = text.replace(
        "# Copy supervisord configuration",
        "COPY . /app\n# Copy supervisord configuration",
    )
    assert "the sources are copied again after the repair" in _gate_run_problems(later)


def test_the_dockerfile_step_turns_a_windows_copy_into_the_committed_file(tmp_path):
    """Replays the Dockerfile's own commands on a CRLF, non-executable copy."""
    app = tmp_path / "app"
    (app / "open_notebook" / "ocr").mkdir(parents=True)
    copy = _crlf_copy(app / "open_notebook" / "ocr" / "tesseract_gate.py")
    copy.chmod(0o644)  # what a Windows build context may give
    for step in _dockerfile_gate_commands():
        subprocess.run(["sh", "-c", step.replace("/app/", f"{app}/")], check=True)
    assert copy.read_bytes() == GATE.read_bytes()
    assert copy.stat().st_mode & stat.S_IXUSR


def test_ocr_status_shows_whether_the_gate_runs(monkeypatch, capsys):
    from open_notebook.ocr import cli

    monkeypatch.setattr(
        options,
        "tesseract_gate_state",
        lambda real=None: {"active": False, "reason": "the gate file has CRLF"},
    )
    assert cli.main(["status", "--no-db"]) == 0
    assert (
        "orientation gate: NOT ACTIVE - the gate file has CRLF"
        in capsys.readouterr().out
    )


# --------------------------------------------------------------------------- #
# The diagnostic tool
# --------------------------------------------------------------------------- #


def _strip(path: Path, text: str, rotate: int = 0, font_px: int = 44) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, font_px)
    img = Image.new("L", (int(font.getlength(text)) + 2 * font_px, 2 * font_px), 255)
    ImageDraw.Draw(img).text((font_px, font_px // 3), text, font=font, fill=0)
    img.rotate(rotate, expand=True).save(path)
    return path


def _crops(folder: Path) -> Path:
    folder.mkdir()
    _strip(folder / "a_upright.png", LONG)
    _strip(folder / "b_upside_down.png", LONG, rotate=180)
    _strip(folder / "c_short.png", "Trang 2")
    return folder


def _run_crops(tmp_path, *extra: str) -> tuple[dict, list, dict]:
    out = tmp_path / "out"
    rc = TOOL.main(
        [
            "--crops",
            str(tmp_path / "crops"),
            "--out",
            str(out),
            "--lang",
            "vie",
            "--tessdata",
            str(TESSDATA),
            # Phase 12D9: numbers only by default; these tests read the words
            # (was: words by default, --no-text to drop them)
            *(extra if "--no-text" in extra else ("--with-text", *extra)),
        ]
    )
    assert rc == 0
    read = lambda n: json.loads((out / n).read_text(encoding="utf-8"))  # noqa: E731
    return (
        read("00_orientation_environment.json"),
        read("orientation_crops.json"),
        read("orientation_summary.json"),
    )


@needs_tesseract
def test_tool_records_orientation_confidence_and_both_readings(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_TESSERACT_REAL", shutil.which("tesseract"))
    _crops(tmp_path / "crops")
    env, crops, summary = _run_crops(tmp_path)
    assert env["gate"]["active"] is True and env["gate"]["min_confidence"] == 2.0
    by = {c["file"]: c for c in crops}
    up, down, short = by["a_upright.png"], by["b_upside_down.png"], by["c_short.png"]
    assert up["osd_raw"]["orientation"] == 0 and up["applied_rotation"] == 0
    assert up["ocr_alternative"] is None
    assert down["osd_raw"]["orientation"] == 180
    assert down["osd_raw"]["confidence"] >= 2.0
    assert down["applied_rotation"] == 180 and "rotated" in down["flags"]
    assert down["ocr_alternative"]["rotation"] == 0
    assert down["ocr_applied"]["mean_conf"] > down["ocr_alternative"]["mean_conf"]
    assert "Nông" in down["ocr_applied"]["text"]
    assert "osd_failed" in short["flags"] and short["applied_rotation"] == 0
    assert short["pixels"][0] > 0 and short["psm"] is None
    assert summary["crops"] == 3 and summary["rotated_by_degrees"] == {"180": 1}
    assert summary["osd_failed"] == 1 and summary["look_first"] == []
    assert summary["hint"] == "no evidence of a wrong rotation in this run."
    out = tmp_path / "out"
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(f.stat().st_mode) == 0o600 for f in out.rglob("*") if f.is_file()
    )
    assert (out / "crops" / "crop_002.applied.tsv").is_file()


@needs_tesseract
def test_tool_points_at_a_rotation_the_gate_refused(tmp_path, monkeypatch):
    """A threshold above the answer: the gate refuses it, the tool shows that the
    refused orientation reads better (a pointer for review, nothing changes)."""
    monkeypatch.setenv("OCR_TESSERACT_REAL", shutil.which("tesseract"))
    monkeypatch.setenv(tesseract_gate.MIN_CONFIDENCE_ENV, "50")
    _crops(tmp_path / "crops")
    env, crops, summary = _run_crops(tmp_path)
    down = {c["file"]: c for c in crops}["b_upside_down.png"]
    assert down["applied_rotation"] == 0
    assert {"rotation_refused_by_gate", "alternative_reads_better"} <= set(
        down["flags"]
    )
    assert summary["rotation_refused_by_gate"] == 1
    assert [r["id"] for r in summary["look_first"]] == [down["id"]]
    assert "too strict" in summary["hint"]


@needs_tesseract
def test_tool_says_when_the_gate_is_not_running(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_TESSERACT_REAL", shutil.which("tesseract"))
    gate = _crlf_copy(tmp_path / "tesseract_gate.py")
    monkeypatch.setattr(tesseract_gate, "__file__", str(gate))
    _crops(tmp_path / "crops")
    env, _, summary = _run_crops(tmp_path)
    assert env["gate"]["active"] is False and env["gate"]["crlf"] is True
    assert summary["hint"].startswith("THE ORIENTATION GATE IS NOT ACTIVE")


@needs_tesseract
def test_no_text_output_holds_numbers_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_TESSERACT_REAL", shutil.which("tesseract"))
    _crops(tmp_path / "crops")
    _, crops, _ = _run_crops(tmp_path, "--no-text")
    out = tmp_path / "out"
    assert not (out / "crops").exists()
    assert sorted(p.name for p in out.iterdir()) == [
        "00_orientation_environment.json",
        "orientation_crops.json",
        "orientation_summary.json",
    ]
    dumped = json.dumps(crops, ensure_ascii=False)
    assert "Nông" not in dumped and "Trang" not in dumped
    assert all(c["file"] is None for c in crops)


def test_suspect_regions_are_matched_on_page_and_overlap():
    rec = lambda i, page, rect, rot: {  # noqa: E731
        "id": i,
        "page": page,
        "rect": rect,
        "osd_raw": {"rc": 0, "orientation": rot, "confidence": 3.0},
        "applied_rotation": rot,
        "ocr_applied": {"words": 2, "mean_conf": 40.0},
        "ocr_alternative": None,
    }
    records = [
        rec("p3_c001", 3, [70, 630, 300, 700], 180),
        rec("p3_c002", 3, [70, 100, 300, 160], 0),
        rec("p4_c001", 4, [70, 630, 300, 700], 0),
    ]
    summary = TOOL._finalize(records, [TOOL.parse_suspect("3:72,640,290,690")], True)
    assert summary["suspects"] == [
        {
            "suspect": "3:72.0,640.0,290.0,690.0",
            "crops": ["p3_c001"],
            "rotated": ["p3_c001"],
            "refused_by_gate": [],
            "alternative_reads_better": [],
        }
    ]
    with pytest.raises(Exception):
        TOOL.parse_suspect("3:1,2,3")


@needs_tesseract
def test_probe_on_doclings_real_ocr_stage_records_without_changing_anything(
    tmp_path, monkeypatch
):
    """Docling's TesseractOcrCliModel.__call__ in layout-region mode (one OCR
    crop per region, like ingestion), through the gate: the cells are identical
    with and without the probe, the E0-07 patch and the fingerprints hold, and
    the class is restored afterwards."""
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

    from open_notebook.ocr import compat, docling_patches

    real = shutil.which("tesseract")
    assert real is not None
    gate_cmd = options.tesseract_command(real)
    assert gate_cmd == str(GATE.resolve())  # ingestion's command: the gate
    page_img = Image.new("L", (2480, 900), 255)
    regions = []
    for i, (text, rot) in enumerate([(LONG, 0), (LONG, 180), ("Trang 2", 0)]):
        strip = Image.open(_strip(tmp_path / f"s{i}.png", text, rotate=rot))
        x, y = 120, 80 + i * 260
        page_img.paste(strip, (x, y))
        k = 72 / 300  # pixels at 300 dpi -> PDF points
        regions.append(
            BoundingBox(
                l=x * k, t=y * k, r=(x + strip.width) * k, b=(y + strip.height) * k
            )
        )
    pdf = tmp_path / "page.pdf"
    page_img.save(pdf, "PDF", resolution=300)
    docling_patches.apply()
    cls = tm.TesseractOcrCliModel
    before = {
        n: cls.__dict__.get(n)
        for n in ("get_ocr_rects", "_perform_osd", "_run_tesseract")
    }

    def run_stage() -> list[str]:
        in_doc = InputDocument(
            path_or_stream=pdf, format=InputFormat.PDF, backend=PyPdfiumDocumentBackend
        )
        conv = ConversionResult(input=in_doc)
        page = Page(page_no=1)
        page._backend = cast(Any, in_doc._backend).load_page(0)
        page.size = page._backend.get_size()
        page.predictions.layout = LayoutPrediction(
            clusters=[
                Cluster(id=i, label=DocItemLabel.TEXT, bbox=b, confidence=0.9, cells=[])
                for i, b in enumerate(regions)
            ]
        )
        model = cls(
            enabled=True,
            artifacts_path=None,
            options=TesseractCliOcrOptions(
                lang=["vie"],
                path=TESSDATA,
                tesseract_cmd=gate_cmd,
                mode=OcrMode.LAYOUT_REGIONS,
            ),
            accelerator_options=AcceleratorOptions(),
        )
        list(model(conv, [page]))
        return [c.text for c in page.cells]

    plain = run_stage()
    out = tmp_path / "probe"
    out.mkdir()
    probe = TOOL.OrientationProbe(out, options.tesseract_gate_state(real))
    with probe:
        assert docling_patches.is_applied()
        assert compat.check_fingerprints(compat.DOCLING_FINGERPRINTS) == []
        probed = run_stage()
    assert probed == plain  # the probe only records
    assert {n: cls.__dict__.get(n) for n in before} == before  # restored
    assert docling_patches.is_applied()
    recs = probe.records
    assert [r["id"] for r in recs] == ["p1_c001", "p1_c002", "p1_c003"]
    assert [r["applied_rotation"] for r in recs] == [0, 180, 0]
    assert recs[1]["osd_raw"]["confidence"] >= 2.0
    assert recs[1]["ocr_alternative"]["rotation"] == 0
    assert recs[1]["ocr_applied"]["mean_conf"] > recs[1]["ocr_alternative"]["mean_conf"]
    assert recs[2]["docling_osd"].startswith("failed")
    for rec, box in zip(recs, regions):
        assert (
            rec["page"] == 1
            and rec["rect"][0] <= box.l + 1
            and rec["rect"][2] >= box.r - 1
        )
        assert rec["pixels"][0] > 0 and 0 < rec["area_share"] < 1
    assert "Nông" in " ".join(plain)


def test_tool_refuses_a_non_tesseract_engine(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    with pytest.raises(SystemExit, match="Tesseract engines only"):
        TOOL.main([str(pdf), "--engine", "rapidocr", "--out", str(tmp_path / "o")])


def test_tool_needs_exactly_one_input(tmp_path):
    with pytest.raises(SystemExit):
        TOOL.main(["--out", str(tmp_path / "o")])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))


@needs_tesseract
def test_crops_mode_prepares_the_engine_tessdata_like_ingestion(tmp_path, monkeypatch):
    """Without --tessdata the tool uses the engine's own folder, prepared the way
    build_ocr_options prepares it (TESSDATA_PREFIX, configs/tsv)."""
    models = tmp_path / "models"
    tessdata = models / "tesseract"
    tessdata.mkdir(parents=True)
    for lang in ("vie", "osd"):
        (tessdata / f"{lang}.traineddata").symlink_to(
            Path(str(TESSDATA)) / f"{lang}.traineddata"
        )
    monkeypatch.setenv("OCR_MODELS_DIR", str(models))
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    monkeypatch.setenv("OCR_TESSERACT_REAL", shutil.which("tesseract"))
    _crops(tmp_path / "crops")
    out = tmp_path / "out"
    assert (
        TOOL.main(
            [
                "--crops",
                str(tmp_path / "crops"),
                "--out",
                str(out),
                "--lang",
                "vie",
                "--with-text",
            ]  # fmt: skip
        )
        == 0
    )
    assert (tessdata / "configs" / "tsv").is_file()
    assert os.environ["TESSDATA_PREFIX"] == str(tessdata)
    crops = json.loads((out / "orientation_crops.json").read_text(encoding="utf-8"))
    down = {c["file"]: c for c in crops}["b_upside_down.png"]
    assert down["applied_rotation"] == 180 and down["ocr_applied"]["words"] > 3
