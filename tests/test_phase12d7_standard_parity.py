"""Standard parity after E0-07, on Docling's real OCR stage (Phase 12D7, section 9).

The approved rule: Standard may differ from v1.2.0 ONLY where the old parser
rewrote a token Tesseract recognised; every other byte stays the same, and each
difference is tied to the raw Tesseract TSV.

Rendered page, one layout region per line (OCR mode LAYOUT_REGIONS: one
Tesseract crop per region, like ingestion's default mode), the real Tesseract,
Docling's real ``TesseractOcrCliModel.__call__``: once with the upstream TSV
parse (what v1.2.0 / the 12D5 candidate ran), once with the patch. The texts are
classified by ``scripts/ocr/phase12_standard_diff.py`` with the raw TSV of every
crop as evidence. Synthetic: the 22 real PDFs are a Windows checklist item.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("docling")

ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_spec = importlib.util.spec_from_file_location(
    "phase12_standard_diff", ROOT / "scripts" / "ocr" / "phase12_standard_diff.py"
)
assert _spec is not None and _spec.loader is not None
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

LINES = [
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Số: 0001/2024/QĐ-NHNo",
    "0001",
    "000123",
    "2024",
    "12.50",
    "Điều 1. Lãi suất tối đa 12.50%/năm.",
    "Mã sản phẩm NA và N/A",
    "1/2024",
    "05%",
    "Trang 2",
]


def _tessdata() -> str | None:
    exe = shutil.which("tesseract")
    if not exe or not Path(FONT).is_file():
        return None
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    where = re.search(r'"([^"]+)"', text)
    return where.group(1) if where and "vie" in text.split() else None


TESSDATA = _tessdata()
pytestmark = pytest.mark.skipif(TESSDATA is None, reason="needs tesseract with 'vie'")


def _page(tmp_path: Path):
    from docling.datamodel.base_models import BoundingBox
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, 40)
    # regions >= 20 pt apart: Docling dilates OCR regions by 20 pt and merges
    # those that touch (BaseOcrModel.DEFAULT_DILATION_SIZE); one crop per line
    step = 220
    page = Image.new("L", (2480, 140 + step * len(LINES)), 255)
    draw = ImageDraw.Draw(page)
    k = 72 / 300  # 300 dpi pixels -> PDF points
    regions = []
    for i, text in enumerate(LINES):
        x, y = 160, 80 + step * i
        draw.text((x, y), text, font=font, fill=0)
        w = int(font.getlength(text))
        regions.append(
            BoundingBox(
                l=(x - 30) * k, t=(y - 20) * k, r=(x + w + 30) * k, b=(y + 70) * k
            )
        )
    pdf = tmp_path / "page.pdf"
    page.save(pdf, "PDF", resolution=300)
    return pdf, regions


def _ocr(pdf: Path, regions, patched: bool, crops: Path | None) -> list[str]:
    """Docling's OCR stage on the page: the text of each region, in order."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import (
        Cluster,
        InputFormat,
        LayoutPrediction,
        Page,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.pipeline_options import OcrMode, TesseractCliOcrOptions
    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm
    from docling_core.types.doc import DocItemLabel

    from open_notebook.ocr import docling_patches

    docling_patches.apply()
    cls = tm.TesseractOcrCliModel
    patched_fn = cls.__dict__["_run_tesseract"]
    saved_osd = cls.__dict__["_perform_osd"]  # defined on the class itself
    n = [0]

    def keep_crop(model, ifilename):  # the crop image, for the raw TSV evidence
        if crops is not None:
            n[0] += 1
            shutil.copyfile(ifilename, crops / f"page_c{n[0]:03d}.png")
        return saved_osd(model, ifilename)

    setattr(  # noqa: B010 - a class attribute, restored in finally
        cls,
        "_run_tesseract",
        patched_fn if patched else docling_patches.upstream_function(),
    )
    setattr(cls, "_perform_osd", keep_crop)  # noqa: B010
    try:
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
                tesseract_cmd="tesseract",
                mode=OcrMode.LAYOUT_REGIONS,
            ),
            accelerator_options=AcceleratorOptions(),
        )
        list(model(conv, [page]))
    finally:
        setattr(cls, "_run_tesseract", patched_fn)  # noqa: B010
        setattr(cls, "_perform_osd", saved_osd)  # noqa: B010
    lines = []
    for b in regions:
        words = [
            c
            for c in page.cells
            if b.l <= c.rect.to_bounding_box().l <= b.r
            and b.t <= c.rect.to_bounding_box().t <= b.b
        ]
        lines.append(
            " ".join(
                c.text for c in sorted(words, key=lambda c: c.rect.to_bounding_box().l)
            )
        )
    return lines


def _raw_tsv(crops: Path, out: Path) -> None:
    for png in sorted(crops.glob("*.png")):
        tsv = subprocess.run(
            [
                "tesseract",
                str(png),
                "stdout",
                "-l",
                "vie",
                "--tessdata-dir",
                str(TESSDATA),
                "tsv",
            ],
            capture_output=True,
            check=True,
        ).stdout
        (out / f"{png.stem}.tsv").write_bytes(tsv)


def test_standard_differs_only_where_the_old_parser_rewrote_a_token(tmp_path):
    pdf, regions = _page(tmp_path)
    crops = tmp_path / "crops"
    crops.mkdir()
    before = _ocr(pdf, regions, patched=False, crops=None)
    after = _ocr(pdf, regions, patched=True, crops=crops)
    evidence = tmp_path / "tsv"
    evidence.mkdir()
    _raw_tsv(crops, evidence)
    b, a, o = tmp_path / "before", tmp_path / "after", tmp_path / "report"
    b.mkdir()
    a.mkdir()
    (b / "page.md").write_text("\n\n".join(before), encoding="utf-8")
    (a / "page.md").write_text("\n\n".join(after), encoding="utf-8")
    rc = D.main(
        ["--before", str(b), "--after", str(a), "--tsv", str(evidence), "--out", str(o)]
    )
    report = json.loads((o / "standard_diff.json").read_text(encoding="utf-8"))
    doc = report["documents"]["page"]
    # the E0-07 rewrites, line by line
    changed = {i: (x, y) for i, (x, y) in enumerate(zip(before, after)) if x != y}
    assert after[2] == "0001" and before[2] == "1.0"
    assert after[3] == "000123" and before[3] == "123.0"
    assert after[4] == "2024" and before[4] == "2024.0"
    assert "NA" in after[7].split() and "NA" not in before[7].split()
    assert set(changed) <= {2, 3, 4, 5, 7}, changed  # only crops the old parser rewrote
    for i in set(range(len(LINES))) - set(changed):
        assert before[i] == after[i]  # every other region byte-identical
    assert rc == 0 and doc["class"] == D.EXPECTED
    assert {h["class"] for h in doc["hunks"]} == {D.EXPECTED}
