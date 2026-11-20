#!/usr/bin/env python3
"""RB-1 staged-state verifier (Phase 12D13). Standard library + ssh-keygen only:
it runs from the persistent stage itself, never from a source checkout or $WORK.

    python3 -I <RB1_STATE>/verify_stage.py --allowed-signers FILE --identity ID \\
        [--service NAME]

Run before EVERY start of the v1.2.0 rollback (adapter normal / maintenance,
boot guard). It checks that

* the stage folder, its sub-folders and every file belong to root (or the
  running user) and are not writable by group / others, nor any folder above
  (a sticky folder excepted); no symlink; exactly the expected files;
* the package manifest copied into the stage verifies with the operator's
  trusted signers file (kept OUTSIDE the stage) - the trust root after staging;
* every staged RB-1 file has the signed size and SHA-256;
* the Compose override is exactly the application-only startup gate of this
  stage (entrypoint, empty command, read-only bind of this folder, pull never);
* the image pins are one strict LF-terminated line each.

Prints one JSON line. Exit 0 = verified, 3 = refused (nothing is changed).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

NAMESPACE = "chatbot5400-offline"
PREFIX = "rollback-assets/v1.2.0/"
MOUNT = "/opt/cb5400-rb1"
ENTRYPOINT = ["/bin/sh", MOUNT + "/startup.sh"]
SIGNED = (
    "manifest.json",
    "restore_rapidocr_assets.py",
    "assets/rapidocr/ppocrv6_dict.txt",
    "LICENSE.txt",
    "runtime_gate.py",
    "startup.sh",
    "select-compose.sh",
    "verify_stage.py",
)
GENERATED = (
    "compose.json",
    "baseline-image",
    "deploy-tag",
    "signed-manifest.json",
    "signed-manifest.json.sig",
)
FOLDERS = ("assets", "assets/rapidocr")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
TAG = re.compile(
    r"[a-z0-9]+(?:[._-]+[a-z0-9]+)*(?::\d{1,5})?(?:/[a-z0-9]+(?:[._-]+[a-z0-9]+)*)*"
    r":[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}"
)
SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,62}")


class Refused(Exception):
    pass


def override(service: str, stage: Path) -> dict:
    """The only Compose override a stage may hold (shared with rb1_setup.py)."""
    return {
        "services": {
            service: {
                "entrypoint": ENTRYPOINT,
                "command": [],
                "pull_policy": "never",
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(stage),
                        "target": MOUNT,
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }
                ],
            }
        }
    }


def _trusted(path: Path, what: str) -> None:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise Refused(f"{what} is a symlink")
    if st.st_uid not in (0, os.geteuid()) or st.st_mode & 0o022:
        raise Refused(f"{what} is owned by another user or writable by group / others")


def _trusted_parents(path: Path) -> None:
    for folder in path.parents:
        st = folder.stat()
        if st.st_uid not in (0, os.geteuid()) or (
            st.st_mode & 0o022 and not st.st_mode & stat.S_ISVTX
        ):
            raise Refused("a folder above the stage is writable by others")


def _pin(stage: Path, name: str, shape: "re.Pattern[str]") -> str:
    raw = (stage / name).read_bytes()
    value = raw[:-1].decode("ascii")
    if not raw.endswith(b"\n") or not shape.fullmatch(value):
        raise Refused(f"{name} is not one strict line")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(
    stage: Path, allowed_signers: Path, identity: str, service=None, location=None
) -> dict:
    """``location``: where the stage will lie (rb1_setup verifies a stage before
    putting it in place); defaults to where it is."""
    stage = Path(os.path.abspath(stage))
    if not stage.is_dir() or stage.is_symlink():
        raise Refused("stage folder missing")
    _trusted_parents(stage)
    _trusted(stage, "stage folder")
    present_files: set[str] = set()
    present_dirs: set[str] = set()
    for path in stage.rglob("*"):
        rel = path.relative_to(stage).as_posix()
        _trusted(path, rel)
        (present_dirs if path.is_dir() else present_files).add(rel)
    if present_files != set(SIGNED) | set(GENERATED) or present_dirs != set(FOLDERS):
        raise Refused("stage holds missing or unexpected files")
    _trusted(allowed_signers, "trusted signers file")
    _trusted_parents(allowed_signers)
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        raise Refused("ssh-keygen is required")
    signed = (stage / "signed-manifest.json").read_bytes()
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [
            keygen,
            "-Y",
            "verify",
            "-f",
            str(allowed_signers),
            "-I",
            identity,
            "-n",
            NAMESPACE,
            "-s",
            str(stage / "signed-manifest.json.sig"),
        ],
        input=signed,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise Refused("staged package manifest is not signed by the trusted key")
    files = json.loads(signed.decode("utf-8"))["files"]
    for name in SIGNED:
        meta = files.get(PREFIX + name)
        data = (stage / name).read_bytes()
        if (
            not isinstance(meta, dict)
            or meta.get("size") != len(data)
            or meta.get("sha256") != _sha(data)
        ):
            raise Refused(f"staged {name} differs from the signed bytes")
    config = json.loads((stage / "compose.json").read_text(encoding="utf-8"))
    names = list((config.get("services") or {}) if isinstance(config, dict) else [])
    if (
        len(names) != 1
        or not SERVICE.fullmatch(names[0])
        or (service is not None and names[0] != service)
        or config != override(names[0], Path(os.path.abspath(location or stage)))
    ):
        raise Refused("Compose override is not the startup gate of this stage")
    return {
        "rb1_stage": "verified",
        "service": names[0],
        "baseline_image": _pin(stage, "baseline-image", IMAGE_ID),
        "deploy_tag": _pin(stage, "deploy-tag", TAG),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--service")
    parser.add_argument("--stage", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)
    try:
        result = verify(args.stage, args.allowed_signers, args.identity, args.service)
    except (Refused, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "unreadable stage"
        print(json.dumps({"rb1_stage": "REFUSED", "reason": reason}))
        return 3
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
