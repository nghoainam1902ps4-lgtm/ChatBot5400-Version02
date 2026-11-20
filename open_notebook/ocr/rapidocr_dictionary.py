"""RapidOCR recognition dictionary for offline deployments (Phase 12D13, D12-L1).

RapidOCR 3.9.2 (torch backend) reads its recognition dictionary from its own
package folder, also when ``Global.model_root_dir`` puts the weights on the
data volume, and downloads it without a checksum when it is missing (D-32).
The package folder is in the container layer, so every recreate loses it and
an offline deployment cannot OCR with RapidOCR any more.

Before RapidOCR is configured this module puts back the dictionary shipped
in the image (``scripts/offline/rb1/``: the Windows-verified artifact, SHA-256
pinned, Apache-2.0) with the SAME verified helper the v1.2.0 rollback gate
uses: only for the pinned RapidOCR / torch / Docling / model identity, only at
the location RapidOCR itself resolves, never over a file of unknown origin.

``OCR_OFFLINE=true``: a dictionary that cannot be proven (other runtime,
missing weights, unknown file at the target, missing asset) stops the
conversion with a ValueError - nothing is downloaded, no other engine is used.
Online deployments keep RapidOCR's upstream behaviour when the helper refuses
(the refusal is logged).
"""

from __future__ import annotations

import runpy
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from open_notebook.ocr import paths

RB1 = Path(__file__).resolve().parents[2] / "scripts" / "offline" / "rb1"
HELPER = RB1 / "restore_rapidocr_assets.py"
MANIFEST = RB1 / "manifest.json"

_lock = threading.Lock()
_helper: dict[str, Any] | None = None
_verified: tuple | None = None  # stat signature of the last verified state


def _implementation() -> dict[str, Any]:
    global _helper
    if _helper is None:
        _helper = runpy.run_path(str(HELPER))
    return _helper


def _signature(*files: Path) -> tuple:
    out = []
    for f in files:
        try:
            st = f.stat()
            out.append((str(f), st.st_size, st.st_mtime_ns, st.st_ino))
        except OSError:
            out.append((str(f), None))
    return tuple(out)


def _restore() -> tuple[str, tuple]:
    helper = _implementation()
    manifest = helper["load_manifest"](MANIFEST)
    runtime = helper["check_runtime"](manifest)
    model = helper["check_model"](manifest, runtime["pkg"], runtime["yaml"])
    target = helper["resolve_target"](manifest, runtime["pkg"], model["dict_url"])
    asset = manifest["assets"]["dictionary"]
    source = RB1 / asset["source_relative_path"]
    try:
        result = helper["restore"](source, target, asset, True)
    except helper["Refuse"]:
        # another process (API / worker) may have installed it meanwhile
        result = helper["restore"](source, target, asset, False)
        if result != "already valid":
            raise
    return result, _signature(target, model["weights"])


def ensure_dictionary() -> str:
    """Make RapidOCR's dictionary the approved one before RapidOCR starts.

    Returns "already valid", "restored", "cached" or "not applicable" (online,
    helper refused). Raises ValueError when offline and it cannot be proven.
    """
    global _verified
    with _lock:
        if (
            _verified is not None
            and _signature(*(Path(s[0]) for s in _verified)) == _verified
        ):
            return "cached"
        try:
            result, signature = _restore()
        except Exception as exc:  # noqa: BLE001 - helper Refuse or unreadable state
            _verified = None
            code = getattr(exc, "code", None)
            detail = f"RapidOCR dictionary not verified (helper code {code}): {exc}"
            if paths.offline_mode():
                raise ValueError(
                    detail + ". OCR_OFFLINE=true: nothing is downloaded and no "
                    "other engine is used; restore the approved RapidOCR runtime "
                    "and weights (docs/ocr, D-32)."
                ) from None
            logger.warning(detail + " - RapidOCR keeps its upstream behaviour")
            return "not applicable"
        _verified = signature
        if result == "restored":
            logger.info("RapidOCR dictionary restored offline from the approved asset")
        return result


def main() -> int:
    """Startup step of the image entrypoint (after the runtime is installed,
    before supervisord starts the API / worker). Prints one line."""
    try:
        result = ensure_dictionary()
    except ValueError as exc:
        print(f"[rapidocr-dictionary] REFUSED: {exc}")
        return 1
    print(f"[rapidocr-dictionary] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
