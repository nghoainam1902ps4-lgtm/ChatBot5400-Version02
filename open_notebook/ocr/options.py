"""Map an engine id to Docling's OFFICIAL OCR option classes (no adapters).

| engine          | Docling class            | key settings                                  |
|-----------------|--------------------------|-----------------------------------------------|
| rapidocr        | RapidOcrOptions          | backend = what Auto picks today, lang=[]      |
| tesseract_fast  | TesseractCliOcrOptions   | lang=[fast/vie, fast/eng], path=tessdata dir  |
| tesseract_best  | TesseractCliOcrOptions   | lang=[best/vie, best/eng], path=tessdata dir  |
| easyocr         | EasyOcrOptions           | lang=[vi, en], use_gpu=False, no downloads    |

Docling is imported lazily: this module is imported by the API process, which
must not load torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from open_notebook.ocr import catalog, paths, runtime

DEFAULT_THREADS_LABEL = "docling-default"


@dataclass(frozen=True)
class OcrSettings:
    """The OCR-related subset of ContentSettings, frozen at job start."""

    enabled: bool = True
    engine: str = catalog.DEFAULT_ENGINE
    num_threads: int | None = (
        None  # None = keep Docling's default (4 / OMP_NUM_THREADS)
    )
    force_full_page: bool = False

    @classmethod
    def from_content_settings(cls, settings: Any) -> "OcrSettings":
        engine = getattr(settings, "docling_ocr_engine", None) or catalog.DEFAULT_ENGINE
        if engine not in catalog.ENGINES:
            engine = catalog.DEFAULT_ENGINE
        threads = getattr(settings, "docling_ocr_num_threads", None)
        enabled = getattr(settings, "docling_ocr", None)
        return cls(
            enabled=True if enabled is None else bool(enabled),
            engine=engine,
            num_threads=int(threads) if threads else None,
            force_full_page=bool(
                getattr(settings, "docling_ocr_force_full_page", False)
            ),
        )

    @property
    def uses_default_tuning(self) -> bool:
        return self.num_threads is None and not self.force_full_page


def describe(engine_id: str) -> dict[str, Any]:
    """What the options will be, as plain data (for logs / UI / tests)."""
    spec = catalog.get_engine(engine_id)
    info: dict[str, Any] = {
        "engine": engine_id,
        "docling_class": {
            "rapidocr": "RapidOcrOptions",
            "tesseract": "TesseractCliOcrOptions",
            "easyocr": "EasyOcrOptions",
        }[spec.docling_kind],
        "lang": list(catalog.DOCLING_LANGS[engine_id]),
        "device": "cpu"
        if spec.runtime != "builtin" or rapidocr_force_cpu()
        else "docling-auto (CPU when no GPU)",
        "model": f"{spec.model_name} {spec.model_version}",
    }
    if spec.runtime == "builtin":
        info["backend"] = runtime.rapidocr_backend()
    if spec.runtime == "tesseract":
        info["tessdata"] = str(paths.tessdata_dir())
    if spec.runtime == "easyocr":
        info["model_storage_directory"] = str(paths.easyocr_dir())
    return info


# RapidOCR device flags Docling sets from the accelerator (docling 2.129
# rapid_ocr_model.py); forcing them off keeps RapidOCR on CPU while Layout /
# TableFormer keep Docling's own device choice.
RAPIDOCR_CPU_PARAMS: dict[str, Any] = {
    "EngineConfig.torch.use_cuda": False,
    "EngineConfig.onnxruntime.use_cuda": False,
    "EngineConfig.paddle.use_cuda": False,
    "Det.use_cuda": False,
    "Cls.use_cuda": False,
    "Rec.use_cuda": False,
    "Det.use_dml": False,
    "Cls.use_dml": False,
    "Rec.use_dml": False,
}


def rapidocr_persistent() -> bool:
    """Opt-in (OCR_RAPIDOCR_PERSISTENT=true): keep RapidOCR weights on the data volume.

    Default off: RapidOCR keeps downloading into its package directory (the
    venv), exactly as before. When on, weights live in <OCR_MODELS_DIR>/rapidocr
    and survive container recreation (no re-download after an update).
    """
    import os

    return os.environ.get("OCR_RAPIDOCR_PERSISTENT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def rapidocr_force_cpu() -> bool:
    """Opt-in (OCR_RAPIDOCR_FORCE_CPU=true): keep the default engine on CPU on GPU hosts.

    Off by default for backward compatibility: before this feature RapidOCR used
    CUDA through Docling's AUTO device whenever a CUDA torch build saw a GPU.
    """
    import os

    return os.environ.get("OCR_RAPIDOCR_FORCE_CPU", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# Docling's EasyOcrOptions.confidence_threshold defaults to 0.5, which drops
# most correct Vietnamese lines of a 150 DPI scan (they score 0.2-0.5). Measured
# in Phase 8C (docs/ocr/OCR_QUALITY_OPTIMIZATION.md): below 0.2 only garbage
# lines were found, between 0.2 and 0.5 mostly correct or partly correct ones.
EASYOCR_CONFIDENCE_DEFAULT = 0.2
EASYOCR_CONFIDENCE_ENV = "OCR_EASYOCR_CONFIDENCE"


def easyocr_confidence_threshold() -> float:
    """Deployment-wide EasyOCR line confidence threshold, 0.0-1.0 (D-26)."""
    import os

    raw = os.environ.get(EASYOCR_CONFIDENCE_ENV, "").strip()
    if not raw:
        return EASYOCR_CONFIDENCE_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        return EASYOCR_CONFIDENCE_DEFAULT
    return value if 0.0 <= value <= 1.0 else EASYOCR_CONFIDENCE_DEFAULT


TESSERACT_GATE_ENV = "OCR_TESSERACT_OSD_GATE"


def tesseract_osd_gate_enabled() -> bool:
    """On by default; ``OCR_TESSERACT_OSD_GATE=false`` calls Tesseract directly."""
    import os

    return os.environ.get(TESSERACT_GATE_ENV, "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def tesseract_command(real_cmd: str) -> str:
    """The value for ``TesseractCliOcrOptions.tesseract_cmd`` (D-25).

    Docling rotates every OCR crop by Tesseract's orientation guess whatever
    its confidence. ``tesseract_gate.py`` sits in front of the real binary and
    turns low-confidence guesses into "upright"; everything else is passed
    through untouched. The real path travels in ``OCR_TESSERACT_REAL`` — the
    same value for every job, so setting it is race-free (like D-04).
    """
    import os
    from pathlib import Path

    from open_notebook.ocr import tesseract_gate

    if not tesseract_osd_gate_enabled():
        return real_cmd
    gate = Path(tesseract_gate.__file__).resolve()
    if not os.access(gate, os.X_OK):
        try:
            gate.chmod(gate.stat().st_mode | 0o111)
        except OSError:
            pass
    if not os.access(gate, os.X_OK):
        # Never break OCR over this: Tesseract still works, only the
        # protection against wrongly rotated crops is missing.
        from loguru import logger

        logger.warning(
            f"{gate} is not executable; Tesseract runs without orientation "
            f"gating (run 'chmod +x {gate}' to restore it)."
        )
        return real_cmd
    os.environ[tesseract_gate.REAL_ENV] = real_cmd
    return str(gate)


def build_ocr_options(
    engine_id: str, force_full_page: bool = False, scale: float | None = None
) -> Any:
    """Return a Docling ``OcrOptions`` instance for ``engine_id``.

    ``scale`` is Docling's official ``OcrOptions.scale`` (72 DPI x scale);
    None keeps Docling's default. Only the Tesseract engines use it (D-25).
    """
    from docling.datamodel.pipeline_options import (
        EasyOcrOptions,
        OcrMode,
        RapidOcrOptions,
        TesseractCliOcrOptions,
    )

    spec = catalog.get_engine(engine_id)
    mode = OcrMode.FULL_PAGE if force_full_page else OcrMode.DEFAULT
    lang = list(catalog.DOCLING_LANGS[engine_id])
    if spec.docling_kind == "rapidocr":
        extra: dict[str, Any] = {}
        params: dict[str, Any] = {}
        if rapidocr_force_cpu():
            # Official RapidOcrOptions.rapidocr_params override the device flags
            # Docling derives from the pipeline accelerator, for OCR ONLY.
            params.update(RAPIDOCR_CPU_PARAMS)
        if rapidocr_persistent():
            # RapidOCR's own Global.model_root_dir: same PP-OCR models, same
            # URLs, SHA-256 checked by RapidOCR, stored on the data volume.
            params["Global.model_root_dir"] = paths.rapidocr_dir()
        if params:
            extra["rapidocr_params"] = params
        return RapidOcrOptions(
            backend=runtime.rapidocr_backend(), lang=lang, mode=mode, **extra
        )
    if spec.docling_kind == "tesseract":
        ok, detail = runtime.ensure_tessdata_prefix()
        if not ok:
            raise ValueError(detail)
        runtime.ensure_tessdata_layout()
        cmd = tesseract_command(runtime.tesseract_cmd() or "tesseract")
        tess_extra: dict[str, Any] = {"scale": scale} if scale else {}
        return TesseractCliOcrOptions(
            lang=lang,
            path=str(paths.tessdata_dir()),
            tesseract_cmd=cmd,
            mode=mode,
            **tess_extra,
        )
    if spec.docling_kind == "easyocr":
        return EasyOcrOptions(
            lang=lang,
            use_gpu=False,  # OCR on CPU only (D-09); layout/table devices untouched
            model_storage_directory=str(paths.easyocr_dir()),
            download_enabled=False,  # never download during document processing
            confidence_threshold=easyocr_confidence_threshold(),
            mode=mode,
        )
    raise ValueError(f"Unsupported OCR engine kind: {spec.docling_kind}")


def build_accelerator_options(num_threads: int | None) -> Any | None:
    """AcceleratorOptions only when the admin chose a thread count (else Docling default)."""
    if not num_threads:
        return None
    from docling.datamodel.accelerator_options import AcceleratorOptions

    return AcceleratorOptions(num_threads=int(num_threads))
