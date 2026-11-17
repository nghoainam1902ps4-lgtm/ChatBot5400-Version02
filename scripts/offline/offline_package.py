#!/usr/bin/env python3
"""ChatBot5400 offline update package: build, verify, preflight, update, rollback.

Phase 12F (docs/deployment/OFFLINE_UPDATE_PACKAGE.md). Standard library only,
Python >= 3.8, so the same file runs on the build machine, inside the image
(``inventory``) and on an air-gapped Ubuntu server.

Principles: fail closed; read-only unless ``--apply``; one update at a time
(lock); never ``docker compose down``, never ``-v``, never ``pull``, never
``build`` on the server; the database container is never recreated; no
network access (the only URL used is the local health URL on loopback);
secrets are never read or printed (``.env`` files are not opened).

Commands::

  build      (build machine)  docker save + git bundle + manifest + SHA256SUMS (+ signature)
  inventory  (inside the image, --network none)  versions, runtime artifacts, schema version
  verify     (server)  integrity, authenticity, archive safety, platform, compatibility
  preflight  (server)  read-only checks of the running deployment against the package
  update     (server)  dry-run by default; --apply performs steps G..P of the guide
  finish     (server)  leave maintenance mode after approval
  rollback   (server)  app image / Legal mode / Agri model / interrupted update
  health     (server)  functional + offline readiness checks of the running app
  status     (server)  the update journal
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional

FORMAT_VERSION = 1
SIG_NAMESPACE = "chatbot5400-offline"
MANIFEST = "manifest.json"
SIGNATURE = "manifest.json.sig"
SUMS = "SHA256SUMS"

# Archive safety limits (overridable for tests / very large images).
MAX_MEMBERS = 5000
MAX_TOTAL_BYTES = int(os.environ.get("CB5400_OFFLINE_MAX_BYTES", str(64 * 1024**3)))
MAX_RATIO = 200.0  # uncompressed / compressed
SAFE_NAME = re.compile(r"^[A-Za-z0-9._+\-/]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

EXIT_OK, EXIT_USAGE, EXIT_VERIFY, EXIT_PREFLIGHT, EXIT_UPDATE, EXIT_LOCK = (
    0,
    2,
    3,
    4,
    5,
    6,
)


class Refused(Exception):
    """A check failed: stop, change nothing more."""

    def __init__(self, message: str, code: int = EXIT_VERIFY) -> None:
        super().__init__(message)
        self.code = code


def log(msg: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[cb5400-offline {stamp}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(
    cmd: List[str],
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run a command (list form, never a shell)."""
    proc = subprocess.run(  # noqa: S603 - fixed binaries, list arguments
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
        input=input_text,
    )
    if check and proc.returncode != 0:
        detail = (
            (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            if capture
            else []
        )
        raise Refused(
            f"command failed ({proc.returncode}): {' '.join(cmd[:4])} … {' | '.join(detail)}",
            EXIT_UPDATE,
        )
    return proc


def normalize_platform(value: str) -> str:
    v = (value or "").strip().lower()
    aliases = {
        "x86_64": "linux/amd64",
        "amd64": "linux/amd64",
        "aarch64": "linux/arm64",
        "arm64": "linux/arm64",
    }
    if v in aliases:
        return aliases[v]
    if v.startswith("linux/"):
        arch = v.split("/", 1)[1]
        return "linux/" + {"x86_64": "amd64", "aarch64": "arm64"}.get(arch, arch)
    return v


# --------------------------------------------------------------------------- #
# Configuration (server side)
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    "DEPLOY_DIR": "",
    "COMPOSE_PROJECT": "",
    "COMPOSE_FILES": "docker-compose.yml",
    "APP_SERVICE": "open_notebook",
    "DB_SERVICE": "surrealdb",
    "IMAGE_REPO": "chatbot5400",
    "STATE_DIR": "/var/lib/chatbot5400-offline",
    "ALLOWED_SIGNERS": "/etc/chatbot5400/allowed_signers",
    "SIGNER_IDENTITY": "release@chatbot5400",
    "MAINTENANCE_OVERRIDE": "",
    "BACKUP_CMD": "",
    "BACKUP_VERIFY_CMD": "",
    "HEALTH_URL": "http://127.0.0.1:5055/health",
    "MIN_FREE_GB_EXTRA": "5",
    "APP_ENV_OVERRIDES": "OCR_RAPIDOCR_PERSISTENT=true OCR_OFFLINE=true",
}


def load_config(path: Optional[str]) -> Dict[str, str]:
    """KEY=VALUE file (no shell evaluation). Missing file -> defaults + env."""
    cfg = dict(DEFAULT_CONFIG)
    candidate = Path(
        path
        or os.environ.get(
            "CB5400_OFFLINE_CONFIG", "/etc/chatbot5400/offline-update.conf"
        )
    )
    if candidate.is_file():
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in cfg:
                cfg[key] = value.strip().strip('"').strip("'")
    for key in cfg:
        if os.environ.get("CB5400_" + key):
            cfg[key] = os.environ["CB5400_" + key]
    return cfg


def require(cfg: Dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise Refused(
            f"configuration missing: {', '.join(missing)} (see docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md)",
            EXIT_USAGE,
        )


@contextlib.contextmanager
def update_lock(state_dir: Path) -> Iterator[None]:
    """One update at a time (flock); released automatically if the process dies."""
    import fcntl

    state_dir.mkdir(parents=True, exist_ok=True)
    fh = open(state_dir / "update.lock", "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refused(
                "another update / rollback is running (lock held)", EXIT_LOCK
            ) from None
        fh.write(str(os.getpid()))
        fh.flush()
        yield
    finally:
        fh.close()


class Journal:
    """Progress of the current update, so an interruption can be resumed or rolled back."""

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "journal.json"
        self.data: Dict[str, Any] = (
            json.loads(self.path.read_text()) if self.path.is_file() else {}
        )

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        os.replace(tmp, self.path)

    def step(self, name: str, **info: Any) -> None:
        self.data.setdefault("steps", []).append(
            {
                "step": name,
                "at": _dt.datetime.now().isoformat(timespec="seconds"),
                **info,
            }
        )
        self.save()

    def done(self, name: str) -> bool:
        return any(s.get("step") == name for s in self.data.get("steps", []))


# --------------------------------------------------------------------------- #
# Archive safety + verification
# --------------------------------------------------------------------------- #


def _check_member(m: tarfile.TarInfo, top: Optional[str]) -> str:
    name = m.name
    if name.startswith("/") or "\\" in name or not SAFE_NAME.match(name):
        raise Refused(f"unsafe archive entry name: {name!r}")
    parts = PurePosixPath(name).parts
    if ".." in parts or any(p in ("", ".") for p in parts):
        raise Refused(f"path traversal in archive entry: {name!r}")
    if m.issym() or m.islnk():
        raise Refused(f"link in archive (symlink / hardlink refused): {name!r}")
    if not (m.isfile() or m.isdir()):
        raise Refused(f"special file in archive refused: {name!r}")
    if top is not None and parts[0] != top:
        raise Refused(f"archive entry outside the package folder: {name!r}")
    return parts[0]


def inspect_archive(package: Path) -> List[tarfile.TarInfo]:
    """Validate every entry BEFORE anything is written to disk."""
    compressed = package.stat().st_size
    members: List[tarfile.TarInfo] = []
    total = 0
    top: Optional[str] = None
    with tarfile.open(package, "r:*") as tar:
        for m in tar:
            if len(members) >= MAX_MEMBERS:
                raise Refused(f"too many archive entries (> {MAX_MEMBERS})")
            top = _check_member(m, top)
            total += max(0, m.size)
            if total > MAX_TOTAL_BYTES:
                raise Refused(f"package expands beyond {MAX_TOTAL_BYTES} bytes")
            members.append(m)
    if not members:
        raise Refused("empty package")
    if compressed and total / compressed > MAX_RATIO:
        raise Refused(
            f"abnormal compression ratio ({total / compressed:.0f}x): refused"
        )
    return members


def safe_extract(package: Path, dest: Path) -> Path:
    if dest.exists() and any(dest.iterdir()):
        raise Refused(f"{dest} must be a new or empty directory")
    members = inspect_archive(package)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(package, "r:*") as tar:
        for m in members:
            target = (root / m.name).resolve()
            if root not in target.parents and target != root:
                raise Refused(f"entry escapes the extraction folder: {m.name!r}")
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            if src is None:
                raise Refused(f"unreadable archive entry: {m.name!r}")
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out, 4 * 1024 * 1024)
            os.chmod(target, 0o755 if m.mode & 0o111 else 0o644)
    tops = {PurePosixPath(m.name).parts[0] for m in members}
    return root / tops.pop()


MANIFEST_REQUIRED = {
    "package_format_version": int,
    "application": dict,
    "platform": str,
    "image": dict,
    "source": dict,
    "database": dict,
    "dependencies": dict,
    "runtime_artifacts": dict,
    "rollback": dict,
    "files": dict,
    "build": dict,
}


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise Refused("manifest is not a JSON object")
    for key, typ in MANIFEST_REQUIRED.items():
        if not isinstance(manifest.get(key), typ):
            raise Refused(f"manifest field missing or invalid: {key}")
    if manifest["package_format_version"] != FORMAT_VERSION:
        raise Refused(
            f"unsupported package format {manifest['package_format_version']}"
        )
    app = manifest["application"]
    if not VERSION_RE.match(str(app.get("version", ""))):
        raise Refused("manifest application.version is not a version number")
    if (
        not isinstance(app.get("supported_source_versions"), list)
        or not app["supported_source_versions"]
    ):
        raise Refused("manifest application.supported_source_versions missing")
    img = manifest["image"]
    for key in ("tag", "id", "archive", "archive_sha256"):
        if not isinstance(img.get(key), str) or not img[key]:
            raise Refused(f"manifest image.{key} missing")
    if not re.match(r"^sha256:[0-9a-f]{64}$", img["id"]):
        raise Refused("manifest image.id is not a sha256 image id")
    db = manifest["database"]
    if not isinstance(db.get("schema_version"), int) or not isinstance(
        db.get("migration_required"), bool
    ):
        raise Refused("manifest database.schema_version / migration_required invalid")
    for rel, meta in manifest["files"].items():
        if (
            not isinstance(meta, dict)
            or not SHA_RE.match(str(meta.get("sha256", "")))
            or not isinstance(meta.get("size"), int)
        ):
            raise Refused(f"manifest files entry invalid: {rel}")
        parts = PurePosixPath(rel).parts
        if rel.startswith("/") or ".." in parts or not SAFE_NAME.match(rel):
            raise Refused(f"manifest files entry unsafe: {rel}")
    secrets_like = re.compile(
        r"(password|secret|api[_-]?key|token)\s*[=:]", re.IGNORECASE
    )
    if secrets_like.search(json.dumps(manifest)):
        raise Refused("manifest looks like it contains a secret: refused")


def verify_signature(root: Path, allowed_signers: str, identity: str) -> str:
    sig = root / SIGNATURE
    if not sig.is_file():
        return "absent"
    if not allowed_signers or not Path(allowed_signers).is_file():
        raise Refused(
            f"package is signed but no trusted key file is installed ({allowed_signers})"
        )
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        raise Refused("ssh-keygen is required to check the signature")
    with open(root / MANIFEST, "rb") as data:
        proc = subprocess.run(  # noqa: S603
            [
                keygen,
                "-Y",
                "verify",
                "-f",
                allowed_signers,
                "-I",
                identity,
                "-n",
                SIG_NAMESPACE,
                "-s",
                str(sig),
            ],
            stdin=data,
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise Refused(
            "INVALID signature: the package is not from the trusted release key"
        )
    return "valid"


def verify_tree(
    root: Path,
    platform_expected: Optional[str],
    current_version: Optional[str],
    current_schema: Optional[int],
) -> Dict[str, Any]:
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise Refused("manifest.json missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Refused(f"manifest.json unreadable: {e}") from None
    validate_manifest(manifest)
    # Every file listed, nothing more, nothing less (manifest + sums + signature aside).
    present = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    } - {MANIFEST, SIGNATURE, SUMS}
    for p in root.rglob("*"):
        if p.is_symlink():
            raise Refused(f"symlink in package: {p.relative_to(root)}")
    listed = set(manifest["files"])
    if present - listed:
        raise Refused(f"files not in the manifest: {sorted(present - listed)[:5]}")
    if listed - present:
        raise Refused(f"files missing from the package: {sorted(listed - present)[:5]}")
    for rel, meta in sorted(manifest["files"].items()):
        f = root / rel
        if f.stat().st_size != meta["size"] or sha256_file(f) != meta["sha256"]:
            raise Refused(f"checksum mismatch: {rel}")
    sums = root / SUMS
    if not sums.is_file():
        raise Refused("SHA256SUMS missing")
    expected_sums = render_sums(manifest["files"])
    if sums.read_text(encoding="utf-8") != expected_sums:
        raise Refused("SHA256SUMS does not match the manifest")
    if (
        manifest["files"].get(manifest["image"]["archive"], {}).get("sha256")
        != manifest["image"]["archive_sha256"]
    ):
        raise Refused(
            "image archive checksum differs from manifest image.archive_sha256"
        )
    if platform_expected and normalize_platform(
        manifest["platform"]
    ) != normalize_platform(platform_expected):
        raise Refused(
            f"wrong platform: package {manifest['platform']}, server {platform_expected}"
        )
    if (
        current_version
        and current_version not in manifest["application"]["supported_source_versions"]
    ):
        raise Refused(
            f"cannot update from {current_version}: supported {manifest['application']['supported_source_versions']}"
        )
    if current_schema is not None:
        db = manifest["database"]
        if current_schema > db["schema_version"]:
            raise Refused(
                f"database schema {current_schema} is newer than the package ({db['schema_version']})"
            )
        if current_schema < db["schema_version"] and not db.get("migration_required"):
            raise Refused(
                "manifest inconsistent: schema differs but migration_required is false"
            )
    if manifest["database"]["migration_required"]:
        raise Refused(
            "this package needs a database migration: offline tooling refuses it (separate approved procedure)"
        )
    return manifest


def render_sums(files: Dict[str, Dict[str, Any]]) -> str:
    return "".join(f"{meta['sha256']}  {rel}\n" for rel, meta in sorted(files.items()))


def cmd_verify(args: argparse.Namespace) -> int:
    package = Path(args.package)
    if not package.is_file():
        raise Refused(f"no such package: {package}", EXIT_USAGE)
    digest = sha256_file(package)
    log(f"package sha256 {digest}")
    authenticity = []
    if args.expected_sha256:
        if digest != args.expected_sha256.strip().lower():
            raise Refused(
                "package SHA-256 differs from the value received over the trusted channel"
            )
        authenticity.append("sha256 matched the trusted-channel value")
    root = safe_extract(package, Path(args.extract_to))
    sig = verify_signature(root, args.allowed_signers, args.identity)
    if sig == "valid":
        authenticity.append("signature valid")
    if not authenticity:
        raise Refused(
            "AUTHENTICITY NOT VERIFIED: the package is unsigned (or no key is installed) and no "
            "--expected-sha256 from a trusted channel was given. Refused."
        )
    manifest = verify_tree(
        root, args.platform, args.current_version, args.current_schema
    )
    report = {
        "result": "VERIFIED",
        "package_sha256": digest,
        "authenticity": authenticity,
        "version": manifest["application"]["version"],
        "platform": manifest["platform"],
        "image": manifest["image"]["tag"],
        "readiness": manifest.get("readiness", {}).get("status"),
        "package_dir": str(root),
    }
    (root.parent / "verify-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Build (machine with Internet; Windows via build-package.ps1, Linux/WSL via .sh)
# --------------------------------------------------------------------------- #


def docker_inspect_image(ref: str) -> Dict[str, Any]:
    out = run(["docker", "image", "inspect", ref]).stdout
    data = json.loads(out)
    if not data:
        raise Refused(f"image not found: {ref}", EXIT_USAGE)
    return data[0]


def cmd_inventory(args: argparse.Namespace) -> int:
    """Runs INSIDE the image (docker run --network none): what this image contains."""
    from importlib.metadata import PackageNotFoundError, version

    app_root = Path(args.app_root)
    info: Dict[str, Any] = {
        "python": _platform.python_version(),
        "machine": _platform.machine(),
    }
    deps = {}
    for pkg in (
        "open-notebook",
        "content-core",
        "docling",
        "docling-core",
        "docling-ibm-models",
        "torch",
        "rapidocr",
        "onnxruntime",
        "easyocr",
        "surrealdb",
        "langchain-core",
    ):
        try:
            deps[pkg] = version(pkg)
        except PackageNotFoundError:
            deps[pkg] = None
    info["dependencies"] = deps
    tess = shutil.which("tesseract")
    info["tesseract"] = (
        run([tess, "--version"], check=False).stdout.splitlines()[0] if tess else None
    )
    migrations = sorted(
        int(p.stem)
        for p in (app_root / "open_notebook/database/migrations").glob("*.surrealql")
        if p.stem.isdigit()
    )
    info["schema_version"] = max(migrations) if migrations else 0
    version_file = app_root / "VERSION"
    info["app_version"] = (
        version_file.read_text().strip() if version_file.is_file() else None
    )
    artifacts: Dict[str, Any] = {}
    try:
        sys.path.insert(0, str(app_root))
        from open_notebook.ocr import catalog, installer

        artifacts["rapidocr_weights_sha256"] = installer.rapidocr_known_checksums()
        engines = {}
        for eid, spec in catalog.ENGINES.items():
            engines[eid] = {
                "display_name": getattr(spec, "display_name", eid),
                "runtime": getattr(spec, "runtime", None),
                "model": f"{getattr(spec, 'model_name', '')} {getattr(spec, 'model_version', '')}".strip(),
                "custom": spec.custom is not None,
            }
        artifacts["engines"] = engines
    except Exception as e:  # noqa: BLE001 - reported, not fatal
        artifacts["error"] = type(e).__name__
    artifacts["docling_models"] = {
        "location": "HF_HOME on the data volume (/app/data/.cache/huggingface): reused, never shipped",
        "layout": "docling-project/docling-layout-heron",
        "tableformer": "docling-project/docling-models (TableFormer accurate)",
    }
    artifacts["persistent_volume_artifacts"] = [
        "/app/data/.cache/huggingface (Layout Heron, TableFormer)",
        "/app/data/ocr/models/tesseract (fast / best / osd.traineddata, custom/agri/<version>)",
        "/app/data/ocr/models/rapidocr (with OCR_RAPIDOCR_PERSISTENT=true)",
        "/app/data/ocr/models/easyocr",
        "/app/data/ocr (manifests, readiness state, custom model versions)",
    ]
    info["runtime_artifacts"] = artifacts
    info["runtimes_baked"] = {
        "docling": deps.get("docling") is not None,
        "easyocr": deps.get("easyocr") is not None,
        "tesseract": tess is not None,
    }
    print(json.dumps(info, indent=2, sort_keys=True))
    return EXIT_OK


def _git(repo: Path, *a: str) -> str:
    return run(["git", "-C", str(repo), *a]).stdout.strip()


def cmd_build(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    version = args.version
    if not VERSION_RE.match(version):
        raise Refused("--version must look like 1.3.0 or 1.3.0-rc.1", EXIT_USAGE)
    out_root = Path(args.out).resolve()
    name = f"ChatBot5400-{version}-{normalize_platform(args.platform).replace('/', '-')}-offline"
    stage = out_root / name
    if stage.exists():
        raise Refused(f"{stage} exists: remove it or choose another --out", EXIT_USAGE)
    image = docker_inspect_image(args.image)
    img_platform = normalize_platform(f"{image.get('Os')}/{image.get('Architecture')}")
    if img_platform != normalize_platform(args.platform):
        raise Refused(
            f"image platform {img_platform} != --platform {args.platform}", EXIT_USAGE
        )
    labels = (image.get("Config") or {}).get("Labels") or {}
    commit = _git(repo, "rev-parse", args.git_ref + "^{commit}")
    if (
        labels.get("org.opencontainers.image.revision")
        and labels["org.opencontainers.image.revision"] != commit
    ):
        raise Refused("image label revision differs from --git-ref commit", EXIT_USAGE)
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise Refused("the build checkout has uncommitted changes", EXIT_USAGE)
    for d in ("images", "source", "scripts", "docs"):
        (stage / d).mkdir(parents=True)

    log("inventory from the image (network disabled)")
    inv = json.loads(
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "/app/.venv/bin/python",
                args.image,
                "/app/scripts/offline/offline_package.py",
                "inventory",
            ],
            timeout=600,
        ).stdout
    )
    if (
        inv.get("app_version")
        and inv["app_version"] != version.split("-")[0]
        and inv["app_version"] != version
    ):
        raise Refused(
            f"image VERSION {inv['app_version']} does not match --version {version}",
            EXIT_USAGE,
        )

    tag = f"{args.image_repo}:{version}"
    if args.image != tag:
        run(["docker", "tag", args.image, tag])
    archive_rel = f"images/{args.image_repo}-{version}.tar"
    log(f"docker save {tag} (keeps image metadata; docker export is never used)")
    run(["docker", "save", "-o", str(stage / archive_rel), tag], timeout=7200)

    bundle_rel = f"source/chatbot5400-{version}.bundle"
    log(f"git bundle {args.base_ref}..{args.git_ref}")
    run(
        [
            "git",
            "-C",
            str(repo),
            "bundle",
            "create",
            str(stage / bundle_rel),
            f"{args.base_ref}..{args.git_ref}",
        ]
        + (args.bundle_refs or [])
    )
    run(["git", "-C", str(repo), "bundle", "verify", str(stage / bundle_rel)])
    archive_src = f"source/chatbot5400-{version}-src.tar.gz"
    run(
        [
            "git",
            "-C",
            str(repo),
            "archive",
            "--format=tar.gz",
            f"--prefix=chatbot5400-{version}/",
            "-o",
            str(stage / archive_src),
            commit,
        ]
    )

    here = Path(__file__).resolve().parent
    for f in (
        "offline_package.py",
        "verify-package.sh",
        "preflight.sh",
        "update.sh",
        "rollback.sh",
        "healthcheck.sh",
        "finish.sh",
        "status.sh",
        "offline-update.conf.example",
    ):
        shutil.copy2(here / f, stage / "scripts" / f)
    docs = repo / "docs" / "deployment"
    for f in (
        "OFFLINE_UPDATE_PACKAGE.md",
        "OFFLINE_UPDATE_UBUNTU_GUIDE.md",
        "OFFLINE_UPDATE_ROLLBACK.md",
        "OFFLINE_UPDATE_SECURITY.md",
    ):
        if (docs / f).is_file():
            shutil.copy2(docs / f, stage / "docs" / f)
    if args.release_notes and Path(args.release_notes).is_file():
        shutil.copy2(args.release_notes, stage / "docs" / "RELEASE_NOTES.md")

    readiness_problems = []
    if not inv.get("runtimes_baked", {}).get("docling"):
        readiness_problems.append(
            "Docling is not baked into the image (build with OCR_PREINSTALL_RUNTIMES=true)"
        )
    if not inv.get("tesseract"):
        readiness_problems.append(
            "Tesseract binary not in the image (build with OCR_INSTALL_TESSERACT=true)"
        )
    manifest = {
        "package_format_version": FORMAT_VERSION,
        "application": {
            "name": "ChatBot5400",
            "version": version,
            "release_tag": args.release_tag or f"v{version}",
            "supported_source_versions": args.supported_from,
        },
        "platform": normalize_platform(args.platform),
        "image": {
            "tag": tag,
            "id": image["Id"],
            "archive": archive_rel,
            "archive_sha256": sha256_file(stage / archive_rel),
            "created": image.get("Created"),
            "labels": {
                k: v for k, v in labels.items() if k.startswith("org.opencontainers")
            },
        },
        "source": {
            "commit": commit,
            "base_ref": args.base_ref,
            "base_commit": _git(repo, "rev-parse", args.base_ref + "^{commit}"),
            "git_bundle": bundle_rel,
            "archive": archive_src,
        },
        "database": {
            "schema_version": int(inv.get("schema_version") or 0),
            "migration_required": bool(args.migration_required),
            "compatible_schema_versions": [int(inv.get("schema_version") or 0)],
        },
        "dependencies": {
            **inv.get("dependencies", {}),
            "tesseract": inv.get("tesseract"),
            "python": inv.get("python"),
        },
        "runtime_artifacts": inv.get("runtime_artifacts", {}),
        "readiness": {
            "status": "READY" if not readiness_problems else "NOT_READY",
            "problems": readiness_problems,
        },
        "rollback": {
            "app_rollback_without_restore": not args.migration_required,
            "previous_versions": args.supported_from,
            "notes": "database untouched; previous image kept as a rollback tag",
        },
        "build": {
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "builder": "offline_package.py",
        },
        "files": {},
    }
    for p in sorted(stage.rglob("*")):
        if p.is_file():
            rel = p.relative_to(stage).as_posix()
            manifest["files"][rel] = {
                "sha256": sha256_file(p),
                "size": p.stat().st_size,
            }
    validate_manifest(manifest)
    (stage / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (stage / SUMS).write_text(render_sums(manifest["files"]), encoding="utf-8")
    if args.sign_key:
        log("signing manifest.json with ssh-keygen -Y sign")
        run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                args.sign_key,
                "-n",
                SIG_NAMESPACE,
                str(stage / MANIFEST),
            ],
            capture=False,
        )
    else:
        log(
            "WARNING: package NOT signed: authenticity must be established by comparing its SHA-256 over a trusted channel"
        )
    package = out_root / f"{name}.tar.gz"
    with tarfile.open(package, "w:gz", compresslevel=6) as tar:
        for p in sorted(stage.rglob("*")):
            info = tar.gettarinfo(
                str(p), arcname=f"{name}/{p.relative_to(stage).as_posix()}"
            )
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o755 if (p.is_dir() or p.suffix in (".sh", ".py")) else 0o644
            if p.is_file():
                with open(p, "rb") as fh:
                    tar.addfile(info, fh)
            else:
                tar.addfile(info)
    digest = sha256_file(package)
    (out_root / f"{name}.tar.gz.sha256").write_text(f"{digest}  {package.name}\n")
    log(f"package: {package}")
    log(
        f"SHA-256: {digest}  <- send this value to the server operator over a trusted channel"
    )
    log(
        f"readiness: {manifest['readiness']['status']} {manifest['readiness']['problems']}"
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Server side helpers
# --------------------------------------------------------------------------- #


class Deployment:
    def __init__(self, cfg: Dict[str, str]) -> None:
        require(cfg, "DEPLOY_DIR", "COMPOSE_PROJECT")
        self.cfg = cfg
        self.dir = Path(cfg["DEPLOY_DIR"])
        self.project = cfg["COMPOSE_PROJECT"]
        self.files = [f for f in re.split(r"[\s:]+", cfg["COMPOSE_FILES"]) if f]
        self.app = cfg["APP_SERVICE"]
        self.db = cfg["DB_SERVICE"]
        self.state = Path(cfg["STATE_DIR"])

    def compose(self, extra_files: Optional[List[str]] = None) -> List[str]:
        cmd = [
            "docker",
            "compose",
            "-p",
            self.project,
            "--project-directory",
            str(self.dir),
        ]
        for f in self.files + (extra_files or []):
            cmd += ["-f", f if os.path.isabs(f) else str(self.dir / f)]
        return cmd

    def config_json(self, extra_files: Optional[List[str]] = None) -> Dict[str, Any]:
        return json.loads(
            run(self.compose(extra_files) + ["config", "--format", "json"]).stdout
        )

    def app_container(self) -> Optional[str]:
        out = run(self.compose() + ["ps", "-q", self.app], check=False).stdout.strip()
        return out.splitlines()[0] if out else None

    def container_image_id(self, container: str) -> str:
        return run(
            ["docker", "inspect", "--format", "{{.Image}}", container]
        ).stdout.strip()

    def exec_app(
        self, *cmd: str, check: bool = True, timeout: int = 600
    ) -> subprocess.CompletedProcess:
        return run(
            self.compose() + ["exec", "-T", self.app, *cmd],
            check=check,
            timeout=timeout,
        )

    def override_path(self, name: str) -> Path:
        return self.state / name


def write_image_override(
    dep: Deployment, image: str, extra_env: Dict[str, str]
) -> Path:
    """Our own override file (outside the deployment folder): image + no pulls."""
    dep.state.mkdir(parents=True, exist_ok=True)
    lines = [
        "services:",
        f"  {dep.app}:",
        f"    image: {image}",
        "    pull_policy: never",
    ]
    if extra_env:
        lines.append("    environment:")
        for k, v in sorted(extra_env.items()):
            if not re.match(r"^[A-Z0-9_]+$", k) or not re.match(
                r"^[A-Za-z0-9_.:/\-]*$", v
            ):
                raise Refused(f"unsafe environment override {k}", EXIT_USAGE)
            lines.append(f'      {k}: "{v}"')
    path = dep.override_path("image-override.yml")
    path.write_text("\n".join(lines) + "\n")
    return path


def parse_env_overrides(text: str) -> Dict[str, str]:
    out = {}
    for item in text.split():
        if "=" in item:
            k, v = item.split("=", 1)
            out[k] = v
    return out


def server_platform() -> str:
    try:
        arch = run(["docker", "info", "--format", "{{.Architecture}}"]).stdout.strip()
    except Refused:
        arch = _platform.machine()
    return normalize_platform(arch)


def current_schema(dep: Deployment) -> Optional[int]:
    code = (
        "import asyncio\n"
        "from open_notebook.database.async_migrate import get_latest_version\n"
        "print(asyncio.run(get_latest_version()))\n"
    )
    proc = dep.exec_app("/app/.venv/bin/python", "-c", code, check=False, timeout=120)
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def running_jobs(dep: Deployment) -> Optional[int]:
    code = (
        "import asyncio\n"
        "from open_notebook.database.repository import repo_query\n"
        "async def m():\n"
        "    r = await repo_query(\"SELECT count() AS n FROM command WHERE status IN ['running','queued','new'] GROUP ALL\")\n"
        "    print(r[0]['n'] if r else 0)\n"
        "asyncio.run(m())\n"
    )
    proc = dep.exec_app("/app/.venv/bin/python", "-c", code, check=False, timeout=120)
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def load_package(package_dir: Optional[str]) -> Dict[str, Any]:
    if not package_dir:
        raise Refused(
            "--package-dir is required (the folder verify-package.sh extracted)",
            EXIT_USAGE,
        )
    root = Path(package_dir).resolve()
    report = root.parent / "verify-report.json"
    if not report.is_file() or json.loads(report.read_text()).get("package_dir") != str(
        root.resolve()
    ):
        raise Refused(
            "package not verified: run verify-package.sh first", EXIT_PREFLIGHT
        )
    # Re-check the files (they could have changed since verify).
    return verify_tree(root, None, None, None)


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 1024**3


def cmd_preflight(
    args: argparse.Namespace, cfg: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    cfg = cfg or load_config(args.config)
    dep = Deployment(cfg)
    manifest = load_package(args.package_dir)
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "", fatal: bool = True) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail, "fatal": fatal})
        log(
            f"{'OK  ' if ok else ('FAIL' if fatal else 'WARN')} {name}{': ' + detail if detail else ''}"
        )

    plat = server_platform()
    check(
        "platform",
        plat == normalize_platform(manifest["platform"]),
        f"server {plat}, package {manifest['platform']}",
    )
    check(
        "readiness of the package",
        manifest.get("readiness", {}).get("status") == "READY" or args.accept_not_ready,
        json.dumps(manifest.get("readiness")),
    )
    try:
        base = dep.config_json()
        check(
            "compose config",
            dep.app in base.get("services", {}) and dep.db in base.get("services", {}),
            f"services {sorted(base.get('services', {}))}",
        )
    except Refused as e:
        check("compose config", False, str(e))
        base = {}
    container = dep.app_container()
    check("application container running", bool(container), container or "not found")
    current_image = dep.container_image_id(container) if container else ""
    if container:
        version_out = dep.exec_app("cat", "/app/VERSION", check=False).stdout.strip()
        supported = manifest["application"]["supported_source_versions"]
        check(
            "current version supported",
            version_out in supported or args.allow_version_mismatch,
            f"current {version_out or '?'}, supported {supported}",
        )
        schema = current_schema(dep)
        check(
            "database schema compatible",
            schema is not None and schema == manifest["database"]["schema_version"],
            f"database {schema}, package {manifest['database']['schema_version']}",
        )
        jobs = running_jobs(dep)
        check(
            "no background job running",
            jobs == 0 or args.ignore_jobs,
            f"running/queued jobs: {jobs}",
        )
    loaded = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", manifest["image"]["tag"]],
        check=False,
    )
    if loaded.returncode == 0:
        check(
            "image tag",
            loaded.stdout.strip() == manifest["image"]["id"],
            f"{manifest['image']['tag']} already loaded with id {loaded.stdout.strip()[:19]}",
        )
    check(
        "not already on the target image",
        current_image != manifest["image"]["id"],
        current_image[:19],
        fatal=False,
    )
    root_dir = (
        run(
            ["docker", "info", "--format", "{{.DockerRootDir}}"], check=False
        ).stdout.strip()
        or "/var/lib/docker"
    )
    need = manifest["files"][manifest["image"]["archive"]][
        "size"
    ] * 2.5 / 1024**3 + float(cfg["MIN_FREE_GB_EXTRA"])
    have = free_gb(root_dir) if Path(root_dir).exists() else free_gb("/")
    check(
        "disk space for docker load",
        have >= need,
        f"free {have:.1f} GB, need {need:.1f} GB in {root_dir}",
    )
    state_free = free_gb(
        str(dep.state.parent if dep.state.parent.exists() else Path("/"))
    )
    check(
        "disk space for state / backup notes", state_free >= 1, f"{state_free:.1f} GB"
    )
    try:
        mem_kb = int(
            re.search(
                r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()
            ).group(1)
        )  # type: ignore[union-attr]
        check(
            "available RAM",
            mem_kb / 1024**2 >= 2,
            f"{mem_kb / 1024**2:.1f} GB",
            fatal=False,
        )
    except (OSError, AttributeError):
        check("available RAM", False, "unknown", fatal=False)
    check(
        "maintenance override configured",
        bool(cfg["MAINTENANCE_OVERRIDE"])
        and Path(cfg["MAINTENANCE_OVERRIDE"]).is_file()
        or args.no_maintenance,
        cfg["MAINTENANCE_OVERRIDE"] or "none",
    )
    check(
        "backup procedure configured",
        bool(cfg["BACKUP_CMD"]) or bool(args.backup_reference),
        cfg["BACKUP_CMD"] and "BACKUP_CMD set" or (args.backup_reference or "none"),
    )
    journal = Journal(dep.state) if dep.state.exists() else None
    unfinished = bool(
        journal and journal.data.get("status") in ("in_progress", "failed")
    )
    check(
        "no unfinished update",
        not unfinished
        or (
            journal is not None
            and journal.data.get("version") == manifest["application"]["version"]
        ),
        str(journal.data.get("status") if journal else "none"),
    )
    fatal = [c for c in checks if not c["ok"] and c["fatal"]]
    result = {
        "result": "PASS" if not fatal else "FAIL",
        "checks": checks,
        "current_image": current_image,
        "base_config": bool(base),
    }
    if not getattr(args, "quiet", False):
        print(
            json.dumps(
                {"result": result["result"], "failed": [c["check"] for c in fatal]},
                indent=2,
            )
        )
    if fatal:
        raise Refused(
            f"preflight failed: {[c['check'] for c in fatal]}", EXIT_PREFLIGHT
        )
    return result


def compare_configs(
    dep: Deployment, before: Dict[str, Any], after: Dict[str, Any], maintenance: bool
) -> None:
    """The database service must be identical; the app keeps its ports (or loopback-only)."""
    b_db, a_db = before["services"].get(dep.db), after["services"].get(dep.db)
    if b_db != a_db:
        raise Refused(
            "the effective compose config would change the database service: refused",
            EXIT_UPDATE,
        )
    if set(before["services"]) != set(after["services"]):
        raise Refused(
            "the effective compose config would add/remove services: refused",
            EXIT_UPDATE,
        )
    b_ports = before["services"][dep.app].get("ports", [])
    a_ports = after["services"][dep.app].get("ports", [])
    if not maintenance and b_ports != a_ports:
        raise Refused(
            "the effective compose config would change published ports: refused",
            EXIT_UPDATE,
        )
    if maintenance:
        for p in a_ports:
            ip = p.get("host_ip") if isinstance(p, dict) else None
            if ip not in ("127.0.0.1", "::1"):
                raise Refused(
                    "maintenance override must publish on loopback only", EXIT_UPDATE
                )
    svc = after["services"][dep.app]
    if svc.get("pull_policy") not in ("never",):
        raise Refused("application pull_policy must be 'never'", EXIT_UPDATE)


def cmd_update(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    manifest = load_package(args.package_dir)
    root = Path(args.package_dir)
    target = manifest["image"]["tag"]
    version = manifest["application"]["version"]
    maintenance = [] if args.no_maintenance else [cfg["MAINTENANCE_OVERRIDE"]]
    env = parse_env_overrides(cfg["APP_ENV_OVERRIDES"])
    plan = [
        "G  docker load the new image (the running application is not stopped)",
        "H  tag the CURRENT application image as rollback image",
        "I  run the approved backup command (BACKUP_CMD) / record the operator's backup reference",
        "J  run BACKUP_VERIFY_CMD (restore check) when configured",
        "K  synchronise the source from the git bundle (only with --sync-source; fast-forward only)",
        "L  keep .env / compose files untouched; write our own image override (pull_policy never)",
        "-- move RapidOCR weights onto the data volume in the OLD container (SHA-256 checked)",
        "M+N recreate ONLY the application container: up -d --no-deps --no-build --pull never (maintenance override)",
        "O  offline readiness check inside the new container",
        "P  functional health check; normal mode only after approval: finish --approve",
    ]
    if not args.apply:
        log("DRY RUN (nothing changes). Plan:")
        for p in plan:
            log("  " + p)
        args.quiet = True
        cmd_preflight(args, cfg)
        log(
            "dry run complete: preflight PASS. Re-run with --apply to perform the update."
        )
        return EXIT_OK

    with update_lock(dep.state):
        journal = Journal(dep.state)
        if (
            journal.data.get("status") in ("in_progress", "failed")
            and journal.data.get("version") != version
        ):
            raise Refused(
                "another update is unfinished: finish or roll it back first (rollback.sh interrupted)",
                EXIT_UPDATE,
            )
        args.quiet = True
        pre = cmd_preflight(args, cfg)
        if journal.data.get("version") != version:
            journal.data = {
                "version": version,
                "status": "in_progress",
                "started": _dt.datetime.now().isoformat(timespec="seconds"),
                "steps": [],
            }
            journal.save()
        if not journal.data.get("previous_image"):
            journal.data["previous_image"] = pre["current_image"]
            journal.save()

        if not journal.done("G_load"):
            log("G: docker load")
            run(
                ["docker", "load", "-i", str(root / manifest["image"]["archive"])],
                timeout=7200,
            )
            loaded = run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", target]
            ).stdout.strip()
            if loaded != manifest["image"]["id"]:
                raise Refused(
                    f"loaded image id {loaded} != manifest {manifest['image']['id']}",
                    EXIT_UPDATE,
                )
            journal.step("G_load", image_id=loaded)
        if not journal.done("H_rollback_tag"):
            prev = journal.data["previous_image"]
            stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
            rollback_tag = f"{cfg['IMAGE_REPO']}:rollback-{stamp}"
            run(["docker", "tag", prev, rollback_tag])
            journal.data["rollback_tag"] = rollback_tag
            journal.step("H_rollback_tag", tag=rollback_tag, image_id=prev)
            log(f"H: rollback image {rollback_tag} -> {prev[:19]}")
        if not journal.done("I_backup"):
            if cfg["BACKUP_CMD"]:
                log("I: running BACKUP_CMD")
                run(
                    ["/bin/sh", "-c", cfg["BACKUP_CMD"]],
                    capture=False,
                    timeout=6 * 3600,
                )
                journal.step("I_backup", method="BACKUP_CMD")
            elif args.backup_reference:
                journal.step(
                    "I_backup", method="operator", reference=args.backup_reference
                )
            else:
                raise Refused(
                    "no backup: set BACKUP_CMD or pass --backup-reference after an approved backup",
                    EXIT_UPDATE,
                )
        if not journal.done("J_backup_verified"):
            if cfg["BACKUP_VERIFY_CMD"]:
                run(
                    ["/bin/sh", "-c", cfg["BACKUP_VERIFY_CMD"]],
                    capture=False,
                    timeout=6 * 3600,
                )
                journal.step("J_backup_verified", method="BACKUP_VERIFY_CMD")
            elif args.backup_verified:
                journal.step("J_backup_verified", method="operator attestation")
            else:
                raise Refused(
                    "backup restore not verified: set BACKUP_VERIFY_CMD or pass --backup-verified",
                    EXIT_UPDATE,
                )
        if args.sync_source and not journal.done("K_source"):
            sync_source(dep, root, manifest)
            journal.step("K_source", commit=manifest["source"]["commit"])
        override = write_image_override(dep, target, env)
        before = dep.config_json()
        after = dep.config_json([str(override)] + maintenance)
        if after["services"][dep.app].get("image") != target:
            raise Refused(
                "the effective configuration does not use the new image", EXIT_UPDATE
            )
        compare_configs(dep, before, after, maintenance=bool(maintenance))
        if not journal.done("RAPIDOCR_weights"):
            code = "from open_notebook.ocr import installer; import json; print(json.dumps(installer.import_rapidocr_weights()))"
            res = dep.exec_app(
                "/app/.venv/bin/python", "-c", code, check=False, timeout=600
            )
            journal.step(
                "RAPIDOCR_weights",
                result=(res.stdout.strip().splitlines() or ["?"])[-1][:500],
                rc=res.returncode,
            )
        log("M+N: recreating ONLY the application container")
        run(
            dep.compose([str(override)] + maintenance)
            + [
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--force-recreate",
                dep.app,
            ],
            capture=False,
            timeout=1800,
        )
        journal.step("N_recreated", maintenance=bool(maintenance))
        journal.data["status"] = "deployed_pending_checks"
        journal.save()
        ok = health_checks(
            dep, cfg, expect_image=manifest["image"]["id"], prove_offline=False
        )
        journal.step("O_P_checks", ok=ok)
        journal.data["status"] = "awaiting_approval" if ok else "failed"
        journal.save()
        if not ok:
            log(
                "CHECKS FAILED: the application stays in maintenance mode. Roll back with: rollback.sh app"
            )
            return EXIT_UPDATE
        log(
            "update deployed in maintenance mode. After acceptance: finish.sh --approve <name>"
        )
        return EXIT_OK


def sync_source(dep: Deployment, root: Path, manifest: Dict[str, Any]) -> None:
    """Fast-forward the deployment's git checkout from the bundle; never reset, never force."""
    repo = dep.dir
    if not (repo / ".git").exists():
        raise Refused(
            "DEPLOY_DIR is not a git checkout: use the source archive manually",
            EXIT_UPDATE,
        )
    bundle = str(root / manifest["source"]["git_bundle"])
    run(["git", "-C", str(repo), "bundle", "verify", bundle])
    commit = manifest["source"]["commit"]
    tag = manifest["application"]["release_tag"]
    run(
        [
            "git",
            "-C",
            str(repo),
            "fetch",
            "--no-tags",
            bundle,
            f"+refs/*:refs/cb5400-offline/{manifest['application']['version']}/*",
        ]
    )
    have = run(
        ["git", "-C", str(repo), "cat-file", "-e", commit + "^{commit}"], check=False
    )
    if have.returncode != 0:
        raise Refused("the bundle does not contain the release commit", EXIT_UPDATE)
    if (
        run(
            ["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
            check=False,
        ).returncode
        != 0
    ):
        run(["git", "-C", str(repo), "tag", tag, commit])
    if (
        run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", "HEAD", commit],
            check=False,
        ).returncode
        != 0
    ):
        raise Refused(
            "local history diverges from the release (local commits?): not changed, merge manually",
            EXIT_UPDATE,
        )
    branch = run(
        ["git", "-C", str(repo), "symbolic-ref", "-q", "--short", "HEAD"], check=False
    ).stdout.strip()
    if branch:
        run(
            ["git", "-C", str(repo), "merge", "--ff-only", commit]
        )  # refuses if local edits conflict
    else:
        run(
            ["git", "-C", str(repo), "checkout", "--detach", commit]
        )  # refuses if local edits conflict
    log(f"K: source now at {commit[:12]} (.env and untracked files untouched)")


def health_checks(
    dep: Deployment,
    cfg: Dict[str, str],
    expect_image: Optional[str],
    prove_offline: bool,
) -> bool:
    import urllib.request

    ok = True
    container = None
    for _ in range(60):
        container = dep.app_container()
        if container:
            break
        time.sleep(2)
    if not container:
        log("FAIL application container not running")
        return False
    if expect_image and dep.container_image_id(container) != expect_image:
        log("FAIL container does not run the expected image")
        ok = False
    url = cfg["HEALTH_URL"]
    if not re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", url):
        log("FAIL HEALTH_URL must be a loopback http URL")
        return False
    healthy = False
    for _ in range(90):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 - loopback only (checked above)
                healthy = r.status == 200
        except Exception:  # noqa: BLE001
            healthy = False
        if healthy:
            break
        time.sleep(5)
    log(f"{'OK  ' if healthy else 'FAIL'} API health {url}")
    ok &= healthy
    checks = [
        ("Docling importable", ["/app/.venv/bin/python", "-c", "import docling"]),
        (
            "OCR engine status",
            ["/app/.venv/bin/python", "-m", "open_notebook.ocr.cli", "status"],
        ),
        (
            "offline readiness (local-only check)",
            [
                "/app/.venv/bin/python",
                "-m",
                "open_notebook.ocr.cli",
                "readiness",
                "--check",
            ],
        ),
        (
            "custom model (Agri) status",
            [
                "/app/.venv/bin/python",
                "-m",
                "open_notebook.ocr.cli",
                "custom",
                "status",
                "--no-db",
            ],
        ),
    ]
    for name, cmd in checks:
        res = dep.exec_app(*cmd, check=False, timeout=1800)
        good = res.returncode == 0
        log(f"{'OK  ' if good else 'FAIL'} {name}")
        ok &= good
    if prove_offline:
        probe = "import socket\ntry:\n    socket.create_connection(('huggingface.co', 443), 5)\n    print('REACHABLE')\nexcept OSError:\n    print('BLOCKED')\n"
        res = dep.exec_app(
            "/app/.venv/bin/python", "-c", probe, check=False, timeout=60
        )
        blocked = res.stdout.strip().endswith("BLOCKED")
        log(
            f"{'OK  ' if blocked else 'FAIL'} outbound network blocked from the container"
        )
        ok &= blocked
    return ok


def cmd_finish(args: argparse.Namespace) -> int:
    if not args.approve:
        raise Refused(
            "finish needs --approve (acceptance done, approval recorded)", EXIT_USAGE
        )
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    with update_lock(dep.state):
        journal = Journal(dep.state)
        if journal.data.get("status") != "awaiting_approval":
            raise Refused(
                f"nothing to finish (status {journal.data.get('status')})", EXIT_UPDATE
            )
        override = dep.override_path("image-override.yml")
        run(
            dep.compose([str(override)])
            + [
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--force-recreate",
                dep.app,
            ],
            capture=False,
            timeout=1800,
        )
        journal.step("Q_normal_mode", approved_by=args.approve)
        journal.data["status"] = "completed"
        journal.save()
        log("normal mode restored")
    return EXIT_OK


def cmd_rollback(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    if args.what == "agri":
        res = dep.exec_app(
            "/app/.venv/bin/python",
            "-m",
            "open_notebook.ocr.cli",
            "custom",
            "rollback",
            check=False,
        )
        print(res.stdout)
        return EXIT_OK if res.returncode == 0 else EXIT_UPDATE
    with update_lock(dep.state):
        journal = Journal(dep.state)
        maintenance = (
            []
            if args.no_maintenance or not cfg["MAINTENANCE_OVERRIDE"]
            else [cfg["MAINTENANCE_OVERRIDE"]]
        )
        if args.what in ("legal-off", "legal-on"):
            current = run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.Config.Image}}",
                    dep.app_container() or "",
                ]
            ).stdout.strip()
            env = parse_env_overrides(cfg["APP_ENV_OVERRIDES"])
            env["OCR_LEGAL_NORMALIZATION_ENABLED"] = (
                "false" if args.what == "legal-off" else "true"
            )
            override = write_image_override(dep, current, env)
            run(
                dep.compose([str(override)] + maintenance)
                + [
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--pull",
                    "never",
                    "--force-recreate",
                    dep.app,
                ],
                capture=False,
                timeout=1800,
            )
            log(
                f"Legal Document gate {'OFF (Standard everywhere)' if args.what == 'legal-off' else 'ON'}; database untouched"
            )
            return EXIT_OK
        # app / interrupted: back to the previous image, database untouched.
        target = args.to_image or journal.data.get("rollback_tag")
        if not target:
            raise Refused(
                "no rollback image recorded: pass --to-image <tag of the previous version>",
                EXIT_UPDATE,
            )
        manifest_schema = None
        if args.package_dir:
            manifest_schema = load_package(args.package_dir)["database"]
            if manifest_schema.get("migration_required"):
                raise Refused(
                    "the update changed the database schema: application rollback needs the approved restore procedure",
                    EXIT_UPDATE,
                )
        run(["docker", "image", "inspect", target])
        env = parse_env_overrides(cfg["APP_ENV_OVERRIDES"])
        override = write_image_override(dep, target, env)
        before = dep.config_json()
        after = dep.config_json([str(override)] + maintenance)
        compare_configs(dep, before, after, maintenance=bool(maintenance))
        run(
            dep.compose([str(override)] + maintenance)
            + [
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--force-recreate",
                dep.app,
            ],
            capture=False,
            timeout=1800,
        )
        journal.step("ROLLBACK_app", to=target)
        journal.data["status"] = "rolled_back"
        journal.save()
        log(
            f"application rolled back to {target}; database not restored (schema unchanged). "
            "After checks and approval, leave maintenance with: "
            f"rollback.sh app --to-image {target} --no-maintenance"
        )
    return EXIT_OK


def cmd_health(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    ok = health_checks(
        Deployment(cfg), cfg, expect_image=None, prove_offline=args.prove_offline
    )
    return EXIT_OK if ok else EXIT_UPDATE


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    j = Journal(Path(cfg["STATE_DIR"]))
    print(json.dumps(j.data or {"status": "no update recorded"}, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="create the package (machine with Internet)")
    b.add_argument("--version", required=True)
    b.add_argument("--image", required=True, help="local image built from --git-ref")
    b.add_argument("--image-repo", default="chatbot5400")
    b.add_argument("--platform", default="linux/amd64")
    b.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    b.add_argument("--git-ref", default="HEAD")
    b.add_argument("--base-ref", default="v1.2.0")
    b.add_argument(
        "--bundle-refs",
        nargs="*",
        help="extra refs to put in the bundle (e.g. the release tag)",
    )
    b.add_argument("--release-tag")
    b.add_argument("--supported-from", nargs="+", default=["1.2.0"])
    b.add_argument("--migration-required", action="store_true")
    b.add_argument("--release-notes")
    b.add_argument(
        "--sign-key",
        help="private ssh key used for ssh-keygen -Y sign (never stored in the package)",
    )
    b.add_argument("--out", default="dist/offline")
    b.set_defaults(func=cmd_build)

    i = sub.add_parser("inventory", help="(inside the image) describe it")
    i.add_argument("--app-root", default="/app")
    i.set_defaults(func=cmd_inventory)

    v = sub.add_parser("verify", help="verify and unpack a package")
    v.add_argument("package")
    v.add_argument("--extract-to", required=True)
    v.add_argument("--expected-sha256", help="value received over a trusted channel")
    v.add_argument("--allowed-signers", default=DEFAULT_CONFIG["ALLOWED_SIGNERS"])
    v.add_argument("--identity", default=DEFAULT_CONFIG["SIGNER_IDENTITY"])
    v.add_argument(
        "--platform", default=None, help="expected platform (default: this machine)"
    )
    v.add_argument("--current-version")
    v.add_argument("--current-schema", type=int)
    v.set_defaults(func=cmd_verify)

    def server(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config")
        sp.add_argument("--package-dir")
        sp.add_argument(
            "--accept-not-ready",
            action="store_true",
            help="accept a package whose readiness is NOT_READY",
        )
        sp.add_argument("--allow-version-mismatch", action="store_true")
        sp.add_argument("--ignore-jobs", action="store_true")
        sp.add_argument("--no-maintenance", action="store_true")
        sp.add_argument(
            "--backup-reference", help="id of an approved backup taken by the operator"
        )
        sp.add_argument(
            "--backup-verified",
            action="store_true",
            help="operator attests the restore test passed",
        )

    pf = sub.add_parser("preflight", help="read-only checks")
    server(pf)
    pf.set_defaults(func=lambda a: (cmd_preflight(a), EXIT_OK)[1])

    u = sub.add_parser("update", help="dry run unless --apply")
    server(u)
    u.add_argument("--apply", action="store_true")
    u.add_argument("--sync-source", action="store_true")
    u.set_defaults(func=cmd_update)

    f = sub.add_parser("finish", help="leave maintenance mode")
    f.add_argument("--config")
    f.add_argument("--approve", help="who approved (recorded in the journal)")
    f.set_defaults(func=cmd_finish)

    r = sub.add_parser(
        "rollback", help="app | legal-off | legal-on | agri | interrupted"
    )
    r.add_argument(
        "what", choices=["app", "legal-off", "legal-on", "agri", "interrupted"]
    )
    r.add_argument("--config")
    r.add_argument("--to-image")
    r.add_argument("--package-dir")
    r.add_argument("--no-maintenance", action="store_true")
    r.set_defaults(func=cmd_rollback)

    h = sub.add_parser("health", help="functional + offline readiness checks")
    h.add_argument("--config")
    h.add_argument("--prove-offline", action="store_true")
    h.set_defaults(func=cmd_health)

    s = sub.add_parser("status", help="update journal")
    s.add_argument("--config")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "verify" and args.platform is None:
        args.platform = normalize_platform(_platform.machine())
    try:
        return int(args.func(args) or 0)
    except Refused as e:
        log(f"REFUSED: {e}")
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())
