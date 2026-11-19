"""Run inside the pinned baseline after its stock entrypoint initializes the venv."""

import json
import os
import runpy
import sys
from importlib.metadata import version
from pathlib import Path


def check(helper, manifest, asset_root=None):
    refuse = helper["Refuse"]
    if (
        Path("/app/VERSION").read_text(encoding="utf-8").strip() != "1.2.0"
        or os.environ.get("OCR_RAPIDOCR_PERSISTENT") != "true"
        or os.environ.get("OCR_OFFLINE") != "true"
    ):
        raise refuse(3, "expected the offline persistent v1.2.0 runtime")
    runtime = helper["check_runtime"](manifest)
    if version("torch") != "2.14.0+cpu":
        raise refuse(3, "expected the verified CPU torch build")
    model = helper["check_model"](manifest, runtime["pkg"], runtime["yaml"])
    from open_notebook.ocr import paths

    root = paths.rapidocr_dir().resolve()
    if Path("/app/data") not in root.parents:
        raise refuse(4, "RapidOCR weights are outside the persistent app volume")
    sha = helper["sha256"]
    recognition = manifest["recognition_model"]
    if model["weights"].stat().st_size != recognition["size"]:
        raise refuse(4, "recognition weight size differs")
    for item in (recognition, *manifest["related_models_verified_only"]):
        path = root / item["file"]
        if path.is_symlink() or not path.is_file() or sha(path) != item["sha256"]:
            raise refuse(4, "a persistent RapidOCR model differs")
    if (
        sha(runtime["pkg"] / "ch_ppocr_rec" / "main.py")
        != manifest["runtime"]["recognizer_source_sha256"]
    ):
        raise refuse(3, "RapidOCR recognizer source differs")
    asset = manifest["assets"]["dictionary"]
    if model["dict_url"] != asset["source_url"]:
        raise refuse(7, "RapidOCR dictionary source differs")
    target = helper["resolve_target"](manifest, runtime["pkg"], model["dict_url"])
    if asset_root is None:
        return helper["restore"](None, target, asset, False)
    source = asset_root / asset["source_relative_path"]
    if (
        source.is_symlink()
        or not source.is_file()
        or source.stat().st_size != asset["size"]
        or sha(source) != asset["sha256"]
    ):
        raise refuse(5, "dictionary asset is missing or incompatible")
    return helper["restore"](source, target, asset, True)


def verdict(helper, manifest, asset_root=None):
    try:
        result = check(helper, manifest, asset_root)
    except (helper["Refuse"], OSError, ValueError, KeyError) as exc:
        status = getattr(exc, "code", 8)
        print("RB1 " + json.dumps({"result": "REFUSED", "exit": status}))
        return status
    print("RB1 " + json.dumps({"result": result}))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--apply"]:
        raise SystemExit(2)
    folder = Path(__file__).resolve().parent
    implementation = runpy.run_path(str(folder / "restore_rapidocr_assets.py"))
    raise SystemExit(
        verdict(
            implementation,
            implementation["load_manifest"](folder / "manifest.json"),
            folder,
        )
    )
