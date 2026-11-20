"""Phase 12F1 RB-1 - offline restore of the RapidOCR recognition dictionary for v1.2.0.

LOCAL TEST HELPER (not the official integration; Codex integrates later).

Run INSIDE the v1.2.0 application container, with the container's interpreter
in isolated mode, after the entrypoint has installed Docling / RapidOCR from the
uv cache:

    /app/.venv/bin/python -I restore_rapidocr_assets.py --manifest M --assets DIR [--check | --apply]

--check (default) verifies everything and changes nothing (preflight use).
--apply writes the dictionary when (and only when) it is missing.

Every location is resolved from the installed runtime (importlib metadata, the
constant RapidOCR itself uses, RapidOCR's own default_models.yaml); nothing is
downloaded (no network module is imported); the database, the Agri models and
the user's OCR settings are never touched. Prints one JSON line.

Exit codes: 0 ok (valid / restored / would restore), 2 usage or manifest,
3 runtime mismatch, 4 recognition model identity mismatch, 5 source asset
checksum mismatch, 6 target exists but is not the expected file (refused,
nothing overwritten), 7 target location mismatch, 8 write / verify failure.
"""

import argparse
import hashlib
import importlib.metadata as md
import importlib.util
import json
import os
import sys
from pathlib import Path

SCHEMA = "cb5400-rollback-assets/1"


class Refuse(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def load_manifest(path: Path) -> dict:
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refuse(2, f"manifest unreadable: {e}")
    if m.get("schema") != SCHEMA:
        raise Refuse(2, f"manifest schema {m.get('schema')!r} != {SCHEMA!r}")
    for k in ("baseline", "runtime", "recognition_model", "assets"):
        if k not in m:
            raise Refuse(2, f"manifest misses {k!r}")
    return m


def check_runtime(m: dict) -> dict:
    rt = m["runtime"]
    try:
        have = md.version(rt["package"])
    except md.PackageNotFoundError:
        raise Refuse(3, f"{rt['package']} is not installed (Docling / RapidOCR must first be installed from the uv cache by the entrypoint)")
    if have != rt["version"]:
        raise Refuse(3, f"{rt['package']} {have} != manifest {rt['version']}")
    for name, ver in (rt.get("requires") or {}).items():
        try:
            v = md.version(name)
        except md.PackageNotFoundError:
            raise Refuse(3, f"{name} is not installed")
        if v.split("+")[0] != ver.split("+")[0]:
            raise Refuse(3, f"{name} {v} != manifest {ver}")
    spec = importlib.util.find_spec("rapidocr")
    if spec is None or not spec.origin:
        raise Refuse(3, "rapidocr module not importable")
    pkg = Path(spec.origin).resolve().parent
    yml = pkg / "default_models.yaml"
    if sha256(yml) != rt["default_models_yaml_sha256"]:
        raise Refuse(3, "rapidocr default_models.yaml differs from the manifest (other RapidOCR build)")
    backend_req = rt.get("backend")
    if backend_req:
        try:
            from open_notebook.ocr import runtime as on_runtime  # v1.2.0's own backend choice
            backend = on_runtime.rapidocr_backend()
        except Exception as e:  # noqa: BLE001
            raise Refuse(3, f"cannot read the application's RapidOCR backend: {e}")
        if backend != backend_req:
            raise Refuse(3, f"RapidOCR backend {backend!r} != manifest {backend_req!r}")
    return {"pkg": pkg, "yaml": yml}


def check_model(m: dict, pkg: Path, yml: Path) -> dict:
    import yaml  # PyYAML ships with the Docling stack (already installed, no network)

    rm = m["recognition_model"]
    node = yaml.safe_load(yml.read_text(encoding="utf-8"))
    for key in rm["yaml_path"]:
        if not isinstance(node, dict) or key not in node:
            raise Refuse(4, f"recognition model {'/'.join(rm['yaml_path'])} not in RapidOCR's default_models.yaml")
        node = node[key]
    if Path(node.get("model_dir", "")).name != rm["file"] or str(node.get("SHA256", "")).lower() != rm["sha256"]:
        raise Refuse(4, "recognition model identity in default_models.yaml differs from the manifest")
    dict_url = node.get("dict_url") or ""
    # the weights actually used: Global.model_root_dir (OCR_RAPIDOCR_PERSISTENT) or the package dir
    if os.environ.get("OCR_RAPIDOCR_PERSISTENT", "").strip().lower() in ("1", "true", "yes", "on"):
        from open_notebook.ocr import paths

        weights = paths.rapidocr_dir() / rm["file"]
    else:
        weights = pkg / "models" / rm["file"]
    if not weights.is_file() or sha256(weights) != rm["sha256"]:
        raise Refuse(4, f"recognition weights {weights} missing or not {rm['file']} sha256 {rm['sha256'][:12]}")
    return {"dict_url": dict_url, "weights": weights}


def resolve_target(m: dict, pkg: Path, dict_url: str) -> Path:
    a = m["assets"]["dictionary"]
    if Path(dict_url).name != a["file"]:
        raise Refuse(7, f"RapidOCR asks for {Path(dict_url).name!r}, manifest provides {a['file']!r}")
    # exactly the constant RapidOCR's recognizer uses for the dictionary path
    from rapidocr.ch_ppocr_rec import main as rec_main

    target_dir = Path(rec_main.DEFAULT_MODEL_PATH).resolve()
    if target_dir != (pkg / "models").resolve():
        raise Refuse(7, f"RapidOCR dictionary dir {target_dir} is not inside the rapidocr package")
    site = Path(md.distribution("rapidocr").locate_file("")).resolve()
    rel = (target_dir / a["file"]).relative_to(site).as_posix()
    if rel != a["target_relative_to_site_packages"]:
        raise Refuse(7, f"target {rel} != manifest {a['target_relative_to_site_packages']}")
    return target_dir / a["file"]


def restore(src: Path, target: Path, a: dict, apply: bool) -> str:
    if target.is_symlink():
        raise Refuse(6, f"{target} is a symlink: refused")
    if target.exists():
        if not target.is_file():
            raise Refuse(6, f"{target} exists and is not a file: refused")
        if sha256(target) == a["sha256"]:
            return "already valid"
        raise Refuse(6, f"{target} exists with another checksum (unknown origin): refused, not overwritten")
    if not apply:
        return "missing - would restore"
    tmp = target.with_name(f".{target.name}.cb5400-{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            for c in iter(lambda: inp.read(1 << 20), b""):
                out.write(c)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, int(a["mode"], 8))
        if sha256(tmp) != a["sha256"]:
            raise Refuse(8, "temporary copy checksum mismatch")
        try:
            os.link(tmp, target)  # fails if the target appeared meanwhile: never overwrite
        except FileExistsError:
            raise Refuse(6, f"{target} appeared during the restore: refused")
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    dfd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    if sha256(target) != a["sha256"] or oct(target.stat().st_mode & 0o777) != oct(int(a["mode"], 8)):
        raise Refuse(8, "restored file does not verify (checksum / mode)")
    return "restored"


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--assets", required=True, type=Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    a_ = ap.parse_args(argv)
    out = {"helper": "restore_rapidocr_assets/1", "mode": "apply" if a_.apply else "check"}
    try:
        m = load_manifest(a_.manifest)
        out["baseline"] = m["baseline"]["commit"]
        rt = check_runtime(m)
        mo = check_model(m, rt["pkg"], rt["yaml"])
        target = resolve_target(m, rt["pkg"], mo["dict_url"])
        a = m["assets"]["dictionary"]
        src = (a_.assets / a["source_relative_path"]).resolve()
        if not src.is_file() or src.stat().st_size != a["size"] or sha256(src) != a["sha256"]:
            raise Refuse(5, f"source asset {a['source_relative_path']} missing or not sha256 {a['sha256'][:12]}")
        out.update(target=str(target), weights=str(mo["weights"]), result=restore(src, target, a, a_.apply))
        print(json.dumps(out))
        return 0
    except Refuse as e:
        out.update(result="REFUSED", exit=e.code, reason=str(e))
        print(json.dumps(out))
        return e.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
