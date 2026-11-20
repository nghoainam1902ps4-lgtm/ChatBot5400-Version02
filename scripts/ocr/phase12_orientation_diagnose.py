#!/usr/bin/env python3
"""Phase 12D7 (E1-05): how each Tesseract OCR crop was oriented, and what the other way reads.

LOCAL USE ONLY. Run it inside the ChatBot5400 container on the machine that
holds the document. It never uploads anything, never writes to the database
and is not part of ingestion: nothing runs unless an operator starts it.

Background. With a Tesseract engine Docling (2.129.0, OCR mode DEFAULT) reads a
scanned page region by region - every layout region (a paragraph, a title, a
page number, a table...) is one OCR "crop". Before reading a crop it asks
Tesseract for its orientation (``tesseract --psm 0 -l osd``) and rotates the
crop by the answer, whatever its confidence. ``tesseract_gate.py`` sits in
front of Tesseract and turns a rotation reported with a confidence below
``OCR_TESSERACT_OSD_MIN_CONFIDENCE`` (2.0) into "upright" (D-25): without it,
small crops come out upside down and read as garbage. The gate only works when
it can start (Windows line endings or a missing executable bit stop it - the
app then runs Tesseract ungated and logs "runs without orientation gating").

PDF mode converts the PDF exactly like ingestion (same engine options, page
preparation, gate and E0-07 patch) and records every crop Docling hands to
Tesseract. Crops mode analyses crop images saved earlier (PNG files).

Written in ``--out`` (owner-only permissions):

  00_orientation_environment.json  versions, engine, gate state (active? CRLF?
                                   executable?), threshold, PSM, render scale,
                                   page preparation (pages rotated before OCR)
  orientation_crops.json           one record per crop: page, rectangle (page
                                   points, top-left origin), size in pixels,
                                   raw orientation answer of the real Tesseract
                                   (degrees, confidence, script, return code),
                                   what the gate passed on, the rotation applied,
                                   OCR words / mean confidence as applied and
                                   with the other orientation
  orientation_summary.json         counts, the crops to look at first, suspects
  crops/<id>.png                   the crop before rotation        (--with-text only)
  crops/<id>.applied.tsv           OCR words with the rotation applied   (idem)
  crops/<id>.alternative.tsv       OCR words with the other orientation  (idem)
  07_markdown_standard.md          PDF mode: the Standard text of this run (idem)

Since Phase 12D9 the default output holds numbers only (no words, no images,
no Markdown, no file name); ``--with-text`` keeps them, in owner-only files.

``--suspect PAGE:L,T,R,B`` (repeatable) marks the crops overlapping a suspect
region; PAGE and the box are the ``page`` / ``bbox`` of a cluster in
``03_layout_clusters.json`` of ``phase12_diagnose.py`` (Docling's page number,
PDF points, top-left origin). ``--no-text`` keeps only numbers (no words, no
images): that output can go into a sanitized report.

The probe only records: the OCR cells, the gate, the threshold and every
default stay what ingestion uses (a test compares the cells with and without
it). "alternative reads better" is a pointer for a human reviewer, not a
verdict: confidence is not accuracy.

Examples (inside the test container)::

  python scripts/ocr/phase12_orientation_diagnose.py /import/qd.pdf \\
      --engine tesseract_best --out /app/data/phase12-diagnostics/orient-qd \\
      --suspect 3:72,640,290,700
  python scripts/ocr/phase12_orientation_diagnose.py --crops /app/data/crops \\
      --engine tesseract_agri --out /app/data/phase12-diagnostics/orient-crops
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCHEMA = "chatbot5400-orientation-diagnostic/1"
# "the other orientation reads better": its mean word confidence is at least
# this many points higher (Tesseract word confidence, 0-100). A pointer only.
ALTERNATIVE_BETTER_POINTS = 10.0
OSD_TIMEOUT_SECONDS = 120

_SCRIPT = re.compile(r"^Script:\s*(\S+)\s*$", re.MULTILINE)
_SCRIPT_CONF = re.compile(r"^Script confidence:\s*([0-9.]+)\s*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def _prepare_out(out: Path, overwrite: bool) -> None:
    if out.exists() and any(out.iterdir()):
        if not overwrite:
            raise SystemExit(
                f"{out} is not empty (use --overwrite to replace its files)"
            )
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)


def _write(path: Path, data: Any) -> None:
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    else:
        text = str(data)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


# --------------------------------------------------------------------------- #
# One crop
# --------------------------------------------------------------------------- #


def osd_raw(real: str, image: Path) -> dict[str, Any]:
    """The REAL Tesseract's orientation answer (the gate is not involved)."""
    from open_notebook.ocr import tesseract_gate

    try:
        proc = subprocess.run(  # noqa: S603 - the configured Tesseract binary
            [real, "--psm", "0", "-l", "osd", str(image), "stdout"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=OSD_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return {
            "rc": None,
            "orientation": None,
            "confidence": None,
            "error": type(e).__name__,
        }
    out = proc.stdout.decode("utf-8", "replace")
    parsed = tesseract_gate.parse_osd(out)
    script = _SCRIPT.search(out)
    script_conf = _SCRIPT_CONF.search(out)
    err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    return {
        "rc": proc.returncode,
        "orientation": parsed[0] if parsed else None,
        "confidence": parsed[1] if parsed else None,
        "script": script.group(1) if script else None,
        "script_confidence": float(script_conf.group(1)) if script_conf else None,
        "error": (err[-1][:200] if err else "no answer") if parsed is None else None,
        "stdout": out,
    }


def gate_passes(raw: dict[str, Any], gate: dict[str, Any]) -> int:
    """The rotation Docling applies for this raw answer, given the gate state."""
    from open_notebook.ocr import tesseract_gate

    if raw.get("rc") != 0 or raw.get("orientation") is None:
        return 0  # Docling logs "OSD failed" and reads the crop as it is
    if not gate.get("active"):
        return int(raw["orientation"])
    parsed = tesseract_gate.parse_osd(
        tesseract_gate.gate_osd(raw["stdout"], float(gate["min_confidence"]))
    )
    return int(parsed[0]) if parsed else 0


def word_stats(df: Any) -> dict[str, Any]:
    words = [str(t) for t in df["text"]]
    confs = [float(c) for c in df["conf"] if float(c) >= 0]
    return {
        "words": len(words),
        "mean_conf": round(sum(confs) / len(confs), 1) if confs else None,
        "text": " ".join(words),
    }


def rotated_copy(image: Path, degrees: int, dest: Path) -> Path:
    """The crop rotated the way Docling rotates it for Tesseract's answer
    ``degrees`` ("Orientation in degrees", clockwise): Docling's
    ``parse_tesseract_orientation`` turns it into ``(-degrees) % 360`` and the
    crop is ``rotate(-that, expand=True)`` (D8-ORI-01, Phase 12D9: 90 and 270
    were turned the opposite way before)."""
    from PIL import Image

    docling = (-int(degrees)) % 360
    with Image.open(image) as im:
        im.rotate(-docling, expand=True).save(dest)
    return dest


def ocr_tsv_direct(
    real: str,
    image: Path,
    langs: list[str],
    tessdata: Optional[str],
    psm: Optional[int],
) -> Any:
    """Crops mode: the recognition command Docling builds, TSV read verbatim (E0-07)."""
    from open_notebook.ocr import docling_patches

    cmd = [real]
    if langs:
        cmd += ["-l", "+".join(langs)]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata]
    if psm is not None:
        cmd += ["--psm", str(int(psm))]
    cmd += [str(image), "stdout", "tsv"]
    out = subprocess.run(  # noqa: S603 - the configured Tesseract binary
        cmd, capture_output=True, stdin=subprocess.DEVNULL, check=True
    ).stdout.decode("utf-8")
    df = docling_patches.read_tesseract_tsv(out)
    return df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]


def flags_for(rec: dict[str, Any]) -> list[str]:
    flags = []
    raw = rec["osd_raw"]
    if raw.get("rc") != 0 or raw.get("orientation") is None:
        flags.append("osd_failed")
    if rec["applied_rotation"]:
        flags.append("rotated")
    elif raw.get("orientation") and raw.get("rc") == 0:
        flags.append("rotation_refused_by_gate")
    applied, alt = rec.get("ocr_applied") or {}, rec.get("ocr_alternative") or {}
    if (
        alt.get("words")
        and alt.get("mean_conf") is not None
        and (applied.get("mean_conf") or 0) + ALTERNATIVE_BETTER_POINTS
        <= alt["mean_conf"]
    ):
        flags.append("alternative_reads_better")
    return flags


def _overlaps(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def parse_suspect(text: str) -> tuple[int, list[float]]:
    try:
        page, box = text.split(":", 1)
        values = [float(v) for v in box.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"--suspect {text!r}: expected PAGE:L,T,R,B")
    if len(values) != 4:
        raise argparse.ArgumentTypeError(f"--suspect {text!r}: expected PAGE:L,T,R,B")
    left, top, right, bottom = values
    return int(page), [
        min(left, right),
        min(top, bottom),
        max(left, right),
        max(top, bottom),
    ]


# --------------------------------------------------------------------------- #
# PDF mode: record what Docling does with each crop
# --------------------------------------------------------------------------- #


class OrientationProbe:
    """Wraps three methods of Docling's TesseractOcrCliModel IN THIS PROCESS to
    record each crop. Every wrapper calls the method it replaces and returns its
    result unchanged; the upstream function stays reachable as
    ``__cb5400_upstream__`` (fingerprints, E0-07 patch guard)."""

    def __init__(
        self,
        out: Optional[Path],
        gate: dict[str, Any],
        keep_text: bool = True,
    ) -> None:
        self.out = out
        self.gate = gate
        self.keep_text = keep_text
        self.records: list[dict[str, Any]] = []
        self._pending: list[tuple[Any, list[float], list[float]]] = []
        self._by_file: dict[str, dict[str, Any]] = {}
        self._copies: dict[str, Path] = {}
        self._crop_no: dict[Any, int] = {}
        self._lock = threading.Lock()
        self._saved: dict[str, Any] = {}

    # -- install / remove ----------------------------------------------------
    def install(self) -> "OrientationProbe":
        from docling.models.stages.ocr import tesseract_ocr_cli_model as tm

        from open_notebook.ocr import docling_patches

        docling_patches.apply()  # first: the probe wraps the patched method
        cls = tm.TesseractOcrCliModel
        self._cls = cls
        probe = self
        for name in ("get_ocr_rects", "_perform_osd", "_run_tesseract"):
            self._saved[name] = cls.__dict__.get(name)
        rects, osd, run = (
            cls.get_ocr_rects,
            cls._perform_osd,
            cls.__dict__["_run_tesseract"],
        )

        def get_ocr_rects(model: Any, page: Any) -> Any:
            found = rects(model, page)
            probe._start_page(page, found)
            return found

        def _perform_osd(model: Any, ifilename: str) -> Any:
            rec = probe._start_crop(model, ifilename)
            try:
                df = osd(model, ifilename)
            except subprocess.CalledProcessError:
                rec["docling_osd"] = "failed (Docling reads the crop as it is)"
                raise
            rec["docling_osd"] = "ok"
            try:
                docling = int(tm._parse_orientation(df))
                # one convention for every angle of the report: Tesseract's
                # (gate_would_pass, osd_raw); Docling's own value kept beside it
                rec["applied_rotation"] = (-docling) % 360
                rec["docling_rotation"] = docling
            except Exception:  # noqa: BLE001 - reported, Docling raises the same
                rec["applied_rotation"] = None
            return df

        def _run_tesseract(model: Any, ifilename: str, osd_df: Any) -> Any:
            df = run(model, ifilename, osd_df)
            probe._finish_crop(model, ifilename, osd_df, df, run)
            return df

        get_ocr_rects.__cb5400_upstream__ = getattr(rects, "__cb5400_upstream__", rects)  # type: ignore[attr-defined]
        _perform_osd.__cb5400_upstream__ = getattr(osd, "__cb5400_upstream__", osd)  # type: ignore[attr-defined]
        _run_tesseract.__cb5400_upstream__ = getattr(run, "__cb5400_upstream__", run)  # type: ignore[attr-defined]
        _run_tesseract.__cb5400_patch__ = getattr(run, "__cb5400_patch__", None)  # type: ignore[attr-defined]
        # class attributes of THIS process only; remove() puts the saved ones back
        setattr(cls, "get_ocr_rects", get_ocr_rects)  # noqa: B010
        setattr(cls, "_perform_osd", _perform_osd)  # noqa: B010
        setattr(cls, "_run_tesseract", _run_tesseract)  # noqa: B010
        return self

    def remove(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                try:
                    delattr(self._cls, name)
                except AttributeError:
                    pass
            else:
                setattr(self._cls, name, value)
        self._saved.clear()

    def __enter__(self) -> "OrientationProbe":
        return self.install()

    def __exit__(self, *exc: Any) -> None:
        self.remove()

    # -- recording -----------------------------------------------------------
    def _start_page(self, page: Any, rects: list[Any]) -> None:
        size = getattr(page, "size", None)
        page_size = (
            [round(float(size.width), 1), round(float(size.height), 1)] if size else []
        )
        with self._lock:
            self._pending = [
                (
                    page.page_no,
                    [
                        round(float(r.l), 1),
                        round(float(r.t), 1),
                        round(float(r.r), 1),
                        round(float(r.b), 1),
                    ],
                    page_size,
                )
                for r in rects
                if r.area() != 0
            ]

    def _start_crop(self, model: Any, ifilename: str) -> dict[str, Any]:
        from PIL import Image

        with self._lock:
            page_no, rect, page_size = (
                self._pending.pop(0) if self._pending else (None, None, [])
            )
            n = self._crop_no[page_no] = self._crop_no.get(page_no, 0) + 1
        crop_id = f"p{page_no if page_no is not None else 'x'}_c{n:03d}"
        with Image.open(ifilename) as im:
            pixels = list(im.size)
        copy = None
        if self.out is not None:
            # the crop before rotation: kept with the results, or (--no-text)
            # in a private work folder and deleted once read the other way
            work = self.out / ("crops" if self.keep_text else ".work")
            work.mkdir(mode=0o700, exist_ok=True)
            copy = work / f"{crop_id}.png"
            shutil.copyfile(ifilename, copy)
        real = os.environ.get("OCR_TESSERACT_REAL") or model._safe_tesseract_cmd
        raw = osd_raw(real, Path(ifilename))
        area = None
        if rect and len(page_size) == 2 and page_size[0] * page_size[1] > 0:
            area = round(
                (rect[2] - rect[0])
                * (rect[3] - rect[1])
                / (page_size[0] * page_size[1]),
                4,
            )
        rec: dict[str, Any] = {
            "id": crop_id,
            "page": page_no,
            "rect": rect,
            "page_size": page_size,
            "area_share": area,
            "pixels": pixels,
            "scale": getattr(model, "scale", None),
            "psm": getattr(model.options, "psm", None),
            "osd_raw": raw,
            "gate_would_pass": gate_passes(raw, self.gate),
            "applied_rotation": 0,
        }
        with self._lock:
            self._by_file[ifilename] = rec
            if copy is not None:
                self._copies[ifilename] = copy
            self.records.append(rec)
        return rec

    def _finish_crop(
        self, model: Any, ifilename: str, osd_df: Any, df: Any, run: Any
    ) -> None:
        with self._lock:
            rec = self._by_file.pop(ifilename, None)
            copy = self._copies.pop(ifilename, None)
        if rec is None:
            return
        rec["ocr_applied"] = word_stats(df)
        raw = rec["osd_raw"]
        alt_rotation: Optional[int] = None
        if rec.get("applied_rotation"):
            alt_rotation = 0
        elif raw.get("rc") == 0 and raw.get("orientation"):
            alt_rotation = int(raw["orientation"])
        rec["ocr_alternative"] = None
        if alt_rotation is not None and copy is not None:
            target = copy
            if alt_rotation:
                target = rotated_copy(copy, alt_rotation, copy.with_suffix(".alt.png"))
            try:
                alt = run(model, str(target), osd_df)
                rec["ocr_alternative"] = {"rotation": alt_rotation, **word_stats(alt)}
                if self.keep_text:
                    alt.to_csv(
                        copy.with_suffix(".alternative.tsv"), sep="\t", index=False
                    )
            except subprocess.CalledProcessError as e:
                rec["ocr_alternative"] = {
                    "rotation": alt_rotation,
                    "error": f"rc {e.returncode}",
                }
            finally:
                if target != copy:
                    target.unlink(missing_ok=True)
        if self.keep_text and copy is not None:
            df.to_csv(copy.with_suffix(".applied.tsv"), sep="\t", index=False)
        elif copy is not None:
            copy.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #


def _versions() -> dict[str, Any]:
    from importlib.metadata import PackageNotFoundError, version

    info: dict[str, Any] = {}
    for pkg in ("docling", "docling-core", "pypdfium2", "pandas", "open-notebook"):
        try:
            info[pkg] = version(pkg)
        except PackageNotFoundError:
            info[pkg] = None
    return info


def _tesseract_version(real: str) -> Optional[str]:
    try:
        out = subprocess.run(  # noqa: S603 - the configured Tesseract binary
            [real, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (out.stdout or out.stderr).splitlines()
    return lines[0] if lines else None


def _finalize(
    records: list[dict[str, Any]],
    suspects: list[tuple[int, list[float]]],
    keep_text: bool,
) -> dict[str, Any]:
    for rec in records:
        rec["flags"] = flags_for(rec)
        rec["osd_raw"].pop("stdout", None)
        if not keep_text:
            for key in ("ocr_applied", "ocr_alternative"):
                if rec.get(key):
                    rec[key].pop("text", None)
    rotated: dict[str, int] = {}
    for rec in records:
        if rec.get("applied_rotation"):
            rotated[str(rec["applied_rotation"])] = (
                rotated.get(str(rec["applied_rotation"]), 0) + 1
            )
    look_first = sorted(
        (r for r in records if "alternative_reads_better" in r["flags"]),
        key=lambda r: -((r["ocr_alternative"] or {}).get("mean_conf") or 0)
        + ((r["ocr_applied"] or {}).get("mean_conf") or 0),
    )
    suspect_rows = []
    for page, box in suspects:
        hits = [
            r
            for r in records
            if r["page"] == page and r["rect"] and _overlaps(r["rect"], box)
        ]
        suspect_rows.append(
            {
                "suspect": f"{page}:{','.join(str(v) for v in box)}",
                "crops": [r["id"] for r in hits],
                "rotated": [r["id"] for r in hits if r.get("applied_rotation")],
                "refused_by_gate": [
                    r["id"] for r in hits if "rotation_refused_by_gate" in r["flags"]
                ],
                "alternative_reads_better": [
                    r["id"] for r in hits if "alternative_reads_better" in r["flags"]
                ],
            }
        )
    return {
        "crops": len(records),
        "osd_failed": sum("osd_failed" in r["flags"] for r in records),
        "rotated_by_degrees": rotated,
        "rotation_refused_by_gate": sum(
            "rotation_refused_by_gate" in r["flags"] for r in records
        ),
        "look_first": [
            {
                "id": r["id"],
                "applied_rotation": r.get("applied_rotation"),
                "raw_orientation": r["osd_raw"].get("orientation"),
                "raw_confidence": r["osd_raw"].get("confidence"),
                "applied_mean_conf": (r["ocr_applied"] or {}).get("mean_conf"),
                "alternative_mean_conf": (r["ocr_alternative"] or {}).get("mean_conf"),
            }
            for r in look_first
        ],
        "suspects": suspect_rows,
    }


def _hint(gate: dict[str, Any], summary: dict[str, Any]) -> str:
    if gate.get("enabled") and not gate.get("active"):
        return (
            "THE ORIENTATION GATE IS NOT ACTIVE ("
            + str(gate.get("reason"))
            + "): every rotation "
            "Tesseract guessed was applied, even below the threshold. Fix the image first "
            "(Phase 12D7 Dockerfile step / LF checkout), then re-run."
        )
    rotated_better = [r for r in summary["look_first"] if r["applied_rotation"]]
    if rotated_better:
        return (
            f"{len(rotated_better)} rotated crop(s) read better the other way: candidates for a "
            "WRONG rotation above the threshold - review the crops before changing anything."
        )
    if summary["look_first"]:
        return (
            "the gate refused rotations that would have read better: candidates for a threshold "
            "that is too strict - review the crops before changing anything."
        )
    return "no evidence of a wrong rotation in this run."


def run_pdf(args: argparse.Namespace, out: Path) -> dict[str, Any]:
    from content_core import ContentCoreConfig

    from open_notebook.ocr import catalog, docling_extract
    from open_notebook.ocr.options import OcrSettings, describe, tesseract_gate_state

    pdf = Path(args.pdf).resolve()
    if not pdf.is_file():
        raise SystemExit(f"not a file: {pdf}")
    ocr = OcrSettings(
        enabled=True,
        engine=args.engine,
        force_full_page=args.full_page,
        custom_version=args.version,
    ).pinned()
    if catalog.get_engine(ocr.engine).docling_kind != "tesseract":
        raise SystemExit(
            "orientation detection per crop exists for the Tesseract engines only"
        )
    gate = tesseract_gate_state()
    probe = OrientationProbe(out, gate, keep_text=_keep_text(args))
    cfg = ContentCoreConfig(document_engine="docling", docling_ocr=True)
    with probe:
        result, converter, prep = docling_extract.convert_document(str(pdf), cfg, ocr)
    env = {
        "schema": SCHEMA,
        "mode": "pdf",
        "file_name": pdf.name if _keep_text(args) else None,
        "file_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "engine": describe(ocr.engine, ocr.custom_version),
        "force_full_page": ocr.force_full_page,
        "versions": _versions(),
        "tesseract": _tesseract_version(
            os.environ.get("OCR_TESSERACT_REAL") or "tesseract"
        ),
        "gate": gate,
        "threshold_env": os.environ.get("OCR_TESSERACT_OSD_MIN_CONFIDENCE"),
        "gate_env": os.environ.get("OCR_TESSERACT_OSD_GATE"),
    }
    env.update(prep.as_meta())
    env.update(docling_extract.pipeline_identity(converter))
    if _keep_text(args):
        _write(out / "07_markdown_standard.md", result.document.export_to_markdown())
    return {"env": env, "records": probe.records}


def run_crops(args: argparse.Namespace, out: Path) -> dict[str, Any]:
    from open_notebook.ocr import paths, runtime
    from open_notebook.ocr.options import describe, engine_langs, tesseract_gate_state

    folder = Path(args.crops).resolve()
    images = sorted(
        p
        for p in folder.iterdir()
        if p.suffix.lower() in (".png", ".tif", ".tiff", ".jpg")
    )
    if not images:
        raise SystemExit(f"no crop image in {folder}")
    real = runtime.tesseract_cmd() or "tesseract"
    gate = tesseract_gate_state(real)
    langs = (
        args.lang.split("+") if args.lang else engine_langs(args.engine, args.version)
    )
    if not args.tessdata:
        # what build_ocr_options does: TESSDATA_PREFIX (orientation data) and the
        # `tsv` config inside the engine's tessdata folder (--tessdata-dir)
        ok, detail = runtime.ensure_tessdata_prefix()
        if not ok:
            raise SystemExit(detail)
        runtime.ensure_tessdata_layout()
    if not langs:
        raise SystemExit(f"{args.engine}: no language (no active custom version?)")
    tessdata = args.tessdata or str(paths.tessdata_dir())
    records = []
    keep = _keep_text(args)
    if keep:
        (out / "crops").mkdir(exist_ok=True)
    for n, image in enumerate(images, 1):
        crop_id = f"crop_{n:03d}"
        from PIL import Image

        with Image.open(image) as im:
            pixels = list(im.size)
        raw = osd_raw(real, image)
        applied = gate_passes(raw, gate)
        work = out / "crops" / f"{crop_id}.png" if keep else out / f".{crop_id}.png"
        shutil.copyfile(image, work)
        target = (
            rotated_copy(work, applied, work.with_suffix(".rot.png"))
            if applied
            else work
        )
        df = ocr_tsv_direct(real, target, langs, tessdata, args.psm)
        alt_rotation = (
            0
            if applied
            else (
                int(raw["orientation"])
                if raw.get("rc") == 0 and raw.get("orientation")
                else None
            )
        )
        alt = None
        if alt_rotation is not None:
            alt_img = (
                rotated_copy(work, alt_rotation, work.with_suffix(".alt.png"))
                if alt_rotation
                else work
            )
            alt_df = ocr_tsv_direct(real, alt_img, langs, tessdata, args.psm)
            alt = {"rotation": alt_rotation, **word_stats(alt_df)}
            if keep:
                alt_df.to_csv(
                    work.with_suffix(".alternative.tsv"), sep="\t", index=False
                )
            if alt_img != work:
                alt_img.unlink(missing_ok=True)
        if keep:
            df.to_csv(work.with_suffix(".applied.tsv"), sep="\t", index=False)
        if target != work:
            target.unlink(missing_ok=True)
        if not keep:
            work.unlink(missing_ok=True)
        records.append(
            {
                "id": crop_id,
                "file": image.name if keep else None,
                "page": None,
                "rect": None,
                "pixels": pixels,
                "psm": args.psm,
                "osd_raw": raw,
                "gate_would_pass": applied,
                "applied_rotation": applied,
                "ocr_applied": word_stats(df),
                "ocr_alternative": alt,
            }
        )
    env = {
        "schema": SCHEMA,
        "mode": "crops",
        "engine": describe(args.engine, args.version),
        "langs": langs,
        "versions": _versions(),
        "tesseract": _tesseract_version(real),
        "gate": gate,
        "threshold_env": os.environ.get("OCR_TESSERACT_OSD_MIN_CONFIDENCE"),
        "gate_env": os.environ.get("OCR_TESSERACT_OSD_GATE"),
    }
    return {"env": env, "records": records}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("pdf", nargs="?", help="the PDF (PDF mode)")
    p.add_argument(
        "--crops", help="folder of crop images (crops mode) instead of a PDF"
    )
    p.add_argument(
        "--out", required=True, help="new or empty local directory for the results"
    )
    p.add_argument(
        "--engine",
        default="tesseract_best",
        help="tesseract_fast | tesseract_best | tesseract_agri",
    )
    p.add_argument(
        "--version",
        default=None,
        help="custom engine version (default: the active one)",
    )
    p.add_argument(
        "--full-page", action="store_true", help="Docling full-page OCR mode (PDF mode)"
    )
    p.add_argument(
        "--lang",
        default=None,
        help="crops mode: Tesseract languages (default: the engine's)",
    )
    p.add_argument(
        "--tessdata",
        default=None,
        help="crops mode: tessdata folder (default: the engine's)",
    )
    p.add_argument(
        "--psm",
        type=int,
        default=None,
        help="crops mode: PSM (default: none, like Docling)",
    )
    p.add_argument(
        "--suspect",
        action="append",
        type=parse_suspect,
        default=[],
        help="PAGE:L,T,R,B (repeatable)",
    )
    p.add_argument(
        "--with-text",
        action="store_true",
        help="also keep OCR words, crop images and the Markdown (owner-only "
        "files, never printed). Default: numbers only (Phase 12D9).",
    )
    p.add_argument(
        "--no-text",
        action="store_true",
        help="numbers only (the default since Phase 12D9; kept for old commands)",
    )
    p.add_argument("--overwrite", action="store_true")
    return p


def _keep_text(args: argparse.Namespace) -> bool:
    """Words / images only on request (metadata-only by default, Phase 12D9)."""
    return bool(getattr(args, "with_text", False)) and not args.no_text


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.pdf) == bool(args.crops):
        raise SystemExit("give either a PDF or --crops DIR")
    out = Path(args.out).resolve()
    _prepare_out(out, args.overwrite)
    run = run_crops(args, out) if args.crops else run_pdf(args, out)
    summary = _finalize(run["records"], args.suspect, keep_text=_keep_text(args))
    summary["hint"] = _hint(run["env"]["gate"], summary)
    _write(out / "00_orientation_environment.json", run["env"])
    _write(out / "orientation_crops.json", run["records"])
    _write(out / "orientation_summary.json", summary)
    shutil.rmtree(out / ".work", ignore_errors=True)
    for f in (out / "crops").glob("*") if (out / "crops").is_dir() else []:
        os.chmod(f, 0o600)
    brief = {
        k: summary[k]
        for k in (
            "crops",
            "osd_failed",
            "rotated_by_degrees",
            "rotation_refused_by_gate",
        )
    }
    brief["gate_active"] = run["env"]["gate"].get("active")
    print(json.dumps(brief, ensure_ascii=False))
    print("hint: " + summary["hint"])
    print(
        f"Written to {out}"
        + (
            " (contains document text and images: keep it local)."
            if _keep_text(args)
            else " (numbers only)."
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
