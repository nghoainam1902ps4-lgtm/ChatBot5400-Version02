"""Phase 12D9: the Standard expected-diff gate on REAL OCR output.

``scripts/ocr/phase12d9_standard_export.py`` converts rendered scans with the
application's ``convert_file`` (real Tesseract, Docling's real threaded PDF
pipeline - only the layout model is a stub with fixed regions, its weights are
not available here) and records the evidence of that same conversion; the
``--before`` side is the same conversion with the v1.2.0 code (upstream TSV
parse, upstream text assembly and Markdown export). ``phase12_standard_diff.py``
must explain every difference from that evidence (exit 0), and catch the
mutations of the candidate output (changed digit, deleted word, lost hyphen,
NBSP, an output that is not the recorded one). Unit tests cover the classes the
real run does not produce (footnote, block join, several causes in one hunk -
E2-03) and the run-level failures (D8-STD-04).

Nothing real is used: synthetic pages, local temporary folders.
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
from typing import Any

import pytest

pytest.importorskip("docling")

from open_notebook.ocr import docling_patches as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _load(name: str, rel: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


D = _load("phase12_standard_diff_gate", "scripts/ocr/phase12_standard_diff.py")
X = _load("phase12d9_standard_export_gate", "scripts/ocr/phase12d9_standard_export.py")
sys.path.insert(0, str(ROOT / "tests"))
import test_phase12d9_ocr_failure_safety as F  # noqa: E402  (rig, stub layout)

needs_ocr = pytest.mark.skipif(
    F.TESSDATA is None or os.name != "posix",
    reason="needs the tesseract binary with 'vie' + 'osd', DejaVu and fcntl",
)

# one page, one region per entry (lines of the region)
REGIONS = [
    ["2021 2025 0001"],  # every word a number: v1.2.0's pandas parse rewrote them
    ["Căn cứ Thông tư số 05/2024/TT-", "BNNPTNT ngày 01 tháng 02 năm 2024;"],
    ["Nơi nhận: Lưu VT- KHTC."],
    ["Điều 5. Hiệu lực thi hành"],
]


def _render(path: Path, regions: list[list[str]]) -> dict[int, list[Any]]:
    from docling_core.types.doc import BoundingBox
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, 44)
    k = 72 / 300
    img = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(img)
    boxes, y = [], 220
    for lines in regions:
        top, width = y, 0
        for text in lines:
            draw.text((160, y), text, font=font, fill=0)
            width = max(width, int(font.getlength(text)))
            y += 80
        boxes.append(
            BoundingBox(
                l=130 * k, t=(top - 20) * k, r=(190 + width) * k, b=(y + 10) * k
            )
        )
        y += 280
    img.save(path, "PDF", resolution=300)
    return {1: boxes}


@pytest.fixture
def gate(monkeypatch, tmp_path):
    import docling.pipeline.standard_pdf_pipeline as spp
    from docling.models.stages.ocr.tesseract_ocr_cli_model import TesseractOcrCliModel

    from open_notebook.ocr import docling_extract, pdf_prep

    registry: dict[str, dict[int, list[Any]]] = {}
    rig = F.Rig(tmp_path / "rig", {})

    class _Factory:
        def create_instance(self, **_kw: Any) -> Any:
            return F._StubLayout(registry)

    monkeypatch.setattr(spp, "get_layout_factory", lambda **_kw: _Factory())
    monkeypatch.setattr(
        docling_extract, "build_pipeline_options", lambda *_a, **_k: rig.options()
    )
    monkeypatch.setattr(docling_extract, "assert_engine_ready", lambda *a, **k: None)
    monkeypatch.setattr(pdf_prep, "prepare", lambda *_a, **_k: pdf_prep.PdfPrep())
    P.apply()

    class Gate:
        inputs = tmp_path / "inputs"
        before = tmp_path / "v120"
        after = tmp_path / "candidate"

        def pdf(self, name: str, regions: list[list[str]]) -> Path:
            self.inputs.mkdir(exist_ok=True)
            path = self.inputs / f"{name}.pdf"
            registry[path.name] = _render(path, regions)
            return path

        def export_v120(self) -> dict:
            """The same conversion with the v1.2.0 code (no evidence)."""
            with monkeypatch.context() as m:
                m.setattr(TesseractOcrCliModel, "_run_tesseract", P.upstream_function())
                m.setattr(P, "evidence_capture", None)
                with P.upstream_text_preservation():
                    return X.export(self.inputs, self.before, "tesseract_best")

        def export_candidate(self) -> dict:
            return X.export(self.inputs, self.after, "tesseract_best")

        def diff(self, *extra: str) -> tuple[int, dict]:
            out = tmp_path / "report"
            rc = D.main(
                [
                    "--before",
                    str(self.before),
                    "--after",
                    str(self.after),
                    "--out",
                    str(out),
                    *extra,
                ]
            )
            return rc, json.loads(
                (out / "standard_diff.json").read_text(encoding="utf-8")
            )

    return Gate()


def _edit(gate: Any, name: str, old: str, new: str, keep_manifest: bool = True) -> None:
    md = gate.after / f"{name}.md"
    text = md.read_text(encoding="utf-8")
    assert old in text, old
    md.write_text(text.replace(old, new, 1), encoding="utf-8")
    if keep_manifest:  # the mutation is in the output, the manifest follows it
        man = json.loads((gate.after / "manifest.json").read_text(encoding="utf-8"))
        for doc in man["documents"]:
            if doc["name"] == name:
                doc["output_sha256"] = X._sha(md)
        (gate.after / "manifest.json").write_text(json.dumps(man), encoding="utf-8")


# --------------------------------------------------------------------------- #
# A. Real OCR: every difference explained by the evidence of the conversion
# --------------------------------------------------------------------------- #


@needs_ocr
def test_every_real_difference_is_explained_and_the_gate_passes(gate, capsys):
    gate.pdf("cong_van", REGIONS)
    gate.export_v120()
    gate.export_candidate()
    before = (gate.before / "cong_van.md").read_text(encoding="utf-8")
    after = (gate.after / "cong_van.md").read_text(encoding="utf-8")
    # what OCR read (precondition): the fixes really are in the candidate
    for must in ("0001", "05/2024/TT-BNNPTNT", "VT- KHTC"):
        assert must in after, must
    for lost in ("1.0", "05/2024/TTBNNPTNT", "VTKHTC"):
        assert lost in before, lost
    capsys.readouterr()
    rc, report = gate.diff()
    doc = report["documents"]["cong_van"]
    assert rc == D.EXIT_OK, doc
    classes = {h["class"] for h in doc["hunks"]}
    assert D.EXPECTED_TSV in classes and D.EXPECTED_HYPHEN in classes
    assert doc.get("changes_missing_from_output") is None
    printed = capsys.readouterr().out
    for secret in ("BNNPTNT", "KHTC", "Thông", "0001", "cong_van"):
        assert secret not in printed, secret  # stdout: counts only
    body = (gate.after.parent / "report" / "standard_diff.json").read_text("utf-8")
    for secret in ("BNNPTNT", "KHTC", "Thông"):
        assert secret not in body, secret  # default report: metadata only


@needs_ocr
def test_the_evidence_and_the_outputs_are_owner_only(gate):
    gate.pdf("quyen", REGIONS[:2])
    gate.export_candidate()
    evidence = gate.after / "quyen.evidence"
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o700
    files = [p for p in evidence.rglob("*") if p.is_file()]
    assert (
        any(p.suffix == ".tsv" for p in files)
        and (evidence / "elements.jsonl").is_file()
    )
    for f in [*files, gate.after / "quyen.md", gate.after / "manifest.json"]:
        assert stat.S_IMODE(f.stat().st_mode) == 0o600, f
    sidecar = json.loads(next(evidence.rglob("*.json")).read_text(encoding="utf-8"))
    for key in (
        "document",
        "page",
        "region",
        "bbox",
        "invocation",
        "engine",
        "model_files",
    ):
        assert key in sidecar, key
    assert sidecar["document"] == "quyen"
    assert all(len(m["sha256"]) == 64 for m in sidecar["model_files"])


@needs_ocr
@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("0001", "0002", D.UNEXPECTED),  # a digit changed in the numeric crop
        ("Hiệu lực", "lực", D.UNEXPECTED),  # a word deleted
        (
            "05/2024/TT-BNNPTNT",
            "05/2024/TTBNNPTNT",
            D.NOT_VERIFIED,
        ),  # hyphen lost again
        ("VT- KHTC", "VT- KHTC", D.UNEXPECTED),  # NBSP
        ("Điều 5.", "Điều 6.", D.UNEXPECTED),  # an unchanged region changed
    ],
    ids=["digit", "deleted-word", "lost-hyphen", "nbsp", "unchanged-region"],
)
def test_mutations_of_the_candidate_output_fail_the_gate(gate, old, new, expected):
    gate.pdf("dot_bien", REGIONS)
    gate.export_v120()
    gate.export_candidate()
    _edit(gate, "dot_bien", old, new)
    rc, report = gate.diff()
    assert report["documents"]["dot_bien"]["class"] == expected
    assert rc != D.EXIT_OK


@needs_ocr
def test_an_output_that_is_not_the_recorded_one_fails_the_run(gate):
    gate.pdf("sua_tay", REGIONS)
    gate.export_v120()
    gate.export_candidate()
    _edit(gate, "sua_tay", "Điều 5.", "Điều 5.", keep_manifest=False)  # no change: ok
    assert gate.diff()[0] == D.EXIT_OK
    md = gate.after / "sua_tay.md"
    md.write_text(
        md.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )  # manifest stale
    rc, report = gate.diff()
    assert rc != D.EXIT_OK
    assert "an output differs from the manifest (sha256)" in report["run_problems"]


@needs_ocr
def test_with_text_puts_tokens_in_an_owner_only_report(gate):
    gate.pdf("van_ban", REGIONS)
    gate.export_v120()
    gate.export_candidate()
    rc, report = gate.diff("--with-text")
    path = gate.after.parent / "report" / "standard_diff.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    hunks = report["documents"]["van_ban"]["hunks"]
    assert any("0001" in h.get("after", []) for h in hunks)


@needs_ocr
def test_a_v120_checkout_exports_outputs_without_evidence(gate):
    gate.pdf("cu", REGIONS[:1])
    manifest = gate.export_v120()
    assert manifest["evidence"] is False
    assert not list(gate.before.glob("*.evidence"))
    assert manifest["documents"][0]["output_sha256"] == X._sha(gate.before / "cu.md")


# --------------------------------------------------------------------------- #
# B. Units: footnote, block join, several causes in one hunk (E2-03)
# --------------------------------------------------------------------------- #


def _evidence(*units: tuple[str, str, str]) -> Any:
    ev = D.Evidence()
    for cause, old, new in units:
        ev.units.append(D.Unit(cause=cause, old=old, new=new, source=f"{cause}:1"))
    return ev


def test_two_causes_in_one_hunk_are_both_proven_and_attributed():
    ev = _evidence(("tsv", "1.0", "0001"), ("hyphen", "VTKHTC", "VT- KHTC"))
    kind, causes, _ = D.explain("1.0 VTKHTC", "0001 VT- KHTC", ev, [], [])
    assert causes == ["hyphen", "tsv"]
    assert kind == "+".join(sorted([D.EXPECTED_HYPHEN, D.EXPECTED_TSV]))
    assert all(u.used for u in ev.units)


def test_a_hunk_only_partly_proven_is_not_accepted():
    """E2-03: part of the hunk has evidence, the rest does not - never EXPECTED."""
    ev = _evidence(("tsv", "1.0", "0001"))
    kind, _, _ = D.explain("1.0 Điều 5", "0001 Điều 6", ev, [], [])
    assert kind not in D.EXPECTED_CLASSES
    assert not ev.units[0].used  # nothing consumed by a failed explanation


def test_an_attached_footnote_is_proven_once():
    note = "(1) Theo Thông tư số 15/2024/TT-BNNPTNT."
    ev = _evidence(("footnote", "", note))
    assert D.explain("", "\n\n" + note, ev, [], [])[0] == D.EXPECTED_FOOTNOTE
    assert D.explain("", "\n\n" + note, ev, [], [])[0] != D.EXPECTED_FOOTNOTE  # used


def test_a_docling_block_join_keeping_its_hyphen_is_proven():
    ev = _evidence(("merge", "xuyênbiên", "xuyên-biên"))
    assert D.explain("xuyênbiên", "xuyên-biên", ev, [], [])[0] == D.EXPECTED_HYPHEN


def test_orientation_needs_its_own_evidence():
    """No orientation evidence: a re-read crop is never accepted."""
    kind, _, _ = D.explain("ờưl .1 uềiĐ", "Điều 1. Lãi", _evidence(), [], [])
    assert kind == D.UNEXPECTED
    ev = _evidence(("orientation", "ờưl .1 uềiĐ", "Điều 1. Lãi"))
    assert (
        D.explain("ờưl .1 uềiĐ", "Điều 1. Lãi", ev, [], [])[0] == D.EXPECTED_ORIENTATION
    )


def test_whitespace_or_structure_changes_are_never_explained():
    ev = _evidence(("tsv", "1.0", "0001"))
    for old, new in (("\n\n", " "), (" ", " "), ("\n", "\n\n")):
        assert D.explain(old, new, ev, [], [])[0] == D.UNEXPECTED
    # beside a proven change too
    assert D.explain("1.0\n\n", "0001 ", ev, [], [])[0] == D.UNEXPECTED


# --------------------------------------------------------------------------- #
# C. The run proves something or fails (D8-STD-04)
# --------------------------------------------------------------------------- #


def _folders(
    tmp_path: Path, before: dict[str, str], after: dict[str, str]
) -> list[str]:
    b, a = tmp_path / "b", tmp_path / "a"
    b.mkdir(parents=True)
    a.mkdir(parents=True)
    for name, text in before.items():
        (b / f"{name}.md").write_text(text, encoding="utf-8")
    for name, text in after.items():
        (a / f"{name}.md").write_text(text, encoding="utf-8")
    return ["--before", str(b), "--after", str(a), "--out", str(tmp_path / "o")]


def test_run_level_failures(tmp_path):
    assert (
        D.main(_folders(tmp_path / "1", {}, {})) == D.EXIT_INVALID
    )  # nothing compared
    assert D.main(_folders(tmp_path / "2", {"x": "a"}, {})) == D.EXIT_INVALID  # missing
    same = _folders(tmp_path / "3", {"x": "a"}, {"x": "a"})
    assert D.main(same) == D.EXIT_OK
    if sys.platform != "darwin":  # a case-insensitive file system keeps one of them
        dup = _folders(tmp_path / "4", {"x": "a", "X": "a"}, {"x": "a", "X": "a"})
        assert D.main(dup) == D.EXIT_INVALID


def test_a_manifest_without_evidence_for_a_changed_document_fails(tmp_path):
    argv = _folders(tmp_path, {"x": "Số: 1.0"}, {"x": "Số: 0001"})
    after = Path(argv[3])
    (after / "manifest.json").write_text(
        json.dumps(
            {"documents": [{"name": "x", "output_sha256": X._sha(after / "x.md")}]}
        ),
        encoding="utf-8",
    )
    rc = D.main(argv)
    report = json.loads((tmp_path / "o" / "standard_diff.json").read_text("utf-8"))
    assert rc == D.EXIT_INVALID
    assert "a changed document has no evidence" in report["run_problems"]


def test_the_cli_prints_counts_only(tmp_path):
    argv = _folders(
        tmp_path, {"bi_mat": "Số: 1.0 Thông tư"}, {"bi_mat": "Số: 0001 Thông tư"}
    )
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ocr/phase12_standard_diff.py"), *argv],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert out.returncode == D.EXIT_NOT_VERIFIED
    assert "bi_mat" not in out.stdout + out.stderr
    assert (
        "Thông" not in out.stdout + out.stderr and "0001" not in out.stdout + out.stderr
    )
    assert re.search(r'"not verified": 1', out.stdout)


def test_no_unexplained_tokens_leak_into_the_markdown_summary(tmp_path):
    argv = _folders(tmp_path, {"x": "Số: 1.0 Thông tư"}, {"x": "Số: 0001 Thông tư"})
    D.main(argv)
    md = (tmp_path / "o" / "standard_diff.md").read_text(encoding="utf-8")
    assert "Thông" not in md and "0001" not in md


@needs_ocr
def test_export_skips_nothing_and_records_failures(gate, monkeypatch):
    """A document whose conversion fails is in the manifest with its error
    class; it has no output, so the gate fails on it."""
    gate.pdf("hong", REGIONS[:1])
    from open_notebook.ocr import docling_extract

    def boom(*_a: Any, **_k: Any) -> Any:
        raise docling_extract.IncompleteConversionError(ocr_region=True, details="x")

    monkeypatch.setattr(docling_extract, "convert_file", boom)
    manifest = X.export(gate.inputs, gate.after, "tesseract_best")
    assert manifest["documents"] == [
        {
            "name": "hong",
            "input_sha256": X._sha(gate.inputs / "hong.pdf"),
            "error": "IncompleteConversionError",
        }
    ]
    # failed on both sides: no output anywhere, the document must not vanish
    shutil.copytree(gate.after, gate.before, dirs_exist_ok=True)
    rc, report = gate.diff()
    assert rc == D.EXIT_INVALID
    assert report["documents"]["hong"] == {
        "class": D.NOT_VERIFIED,
        "reason": "conversion failed",
    }
    assert "a document failed to convert on the after side" in report["run_problems"]


def test_a_stale_output_beside_a_failed_conversion_is_not_compared(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    for folder in (before, after):
        folder.mkdir()
        (folder / "x.md").write_text("Số: 1.0", encoding="utf-8")
    (after / "manifest.json").write_text(
        json.dumps(
            {"documents": [{"name": "x", "error": "IncompleteConversionError"}]}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "o"
    rc = D.main(["--before", str(before), "--after", str(after), "--out", str(out)])
    report = json.loads((out / "standard_diff.json").read_text(encoding="utf-8"))
    assert rc == D.EXIT_INVALID
    assert report["documents"]["x"]["class"] == D.NOT_VERIFIED


def test_the_export_refuses_a_folder_holding_another_run(tmp_path):
    inputs, out = tmp_path / "in", tmp_path / "out"
    inputs.mkdir()
    out.mkdir()
    (out / "old.md").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        X.export(inputs, out, "tesseract_best", convert=lambda _p: ("", {}))


def test_the_export_runs_where_the_patch_module_does_not_exist(tmp_path, monkeypatch):
    """The ``--before`` side runs on the v1.2.0 image, which has no
    ``docling_patches`` module: the export must still write the outputs and the
    manifest (no evidence), not stop on the import."""
    import open_notebook.ocr as ocr_pkg

    monkeypatch.delattr(ocr_pkg, "docling_patches", raising=False)
    monkeypatch.setitem(sys.modules, "open_notebook.ocr.docling_patches", None)
    inputs = tmp_path / "in"
    inputs.mkdir()
    (inputs / "a.pdf").write_bytes(b"%PDF-1.4 synthetic")
    out = tmp_path / "v120"
    manifest = X.export(
        inputs,
        out,
        "tesseract_best",
        convert=lambda _p: ("Số: 1.0", {"conversion_status": "success"}),
    )
    assert manifest["evidence"] is False
    assert [d["name"] for d in manifest["documents"]] == ["a"]
    assert (out / "a.md").read_text(encoding="utf-8") == "Số: 1.0"
    assert not list(out.glob("*.evidence"))
