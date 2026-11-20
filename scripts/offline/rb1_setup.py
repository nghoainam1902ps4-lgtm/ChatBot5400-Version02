#!/usr/bin/env python3
"""Read-only rollback preflight and explicit staging for the manual updater."""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

try:
    from . import offline_package as package
except ImportError:
    import offline_package as package

MOUNT = "/opt/cb5400-rb1"
ENTRYPOINT = ["/bin/sh", f"{MOUNT}/startup.sh"]
STOCK = "/app/scripts/docker-entrypoint.sh"
STOCK_SHA = "62371dd1bc8e2138a2b03c29cd3efe91aec0ffade45e66c3e3f7c35df8a8349f"
PYTHON = "/app/.venv/bin/python"
ENVIRONMENT = "DATA_FOLDER OCR_DATA_DIR OCR_MODELS_DIR OCR_OFFLINE OCR_RAPIDOCR_PERSISTENT OPEN_NOTEBOOK_ENABLE_DOCLING OPEN_NOTEBOOK_ENABLE_CRAWL4AI UV_CACHE_DIR".split()


COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


def require(condition, reason):
    if not condition:
        raise package.Refused(f"RB-1 REFUSED: {reason}", package.EXIT_PREFLIGHT)


def load_payload(root, manifest):
    """Read every RB-1 file ONCE, right after the signed tree was verified, and
    check those bytes against the signed manifest and the approved pins (12D13).
    The probes and the staging use these bytes only: a file changed on disk
    after this point is never run nor staged."""
    payload = {}
    for name in package.RB1_FILES:
        path = root / package.RB1_DIR / name
        require(path.is_file() and not path.is_symlink(), f"RB-1 file missing: {name}")
        package._check_trusted_file(path, f"RB-1 file {name}")
        data = path.read_bytes()
        meta = manifest["files"].get(f"{package.RB1_DIR}/{name}")
        digest = package.sha256_bytes(data)
        require(
            isinstance(meta, dict)
            and meta.get("size") == len(data)
            and meta.get("sha256") == digest,
            f"RB-1 file differs from the signed manifest: {name}",
        )
        pin = package.RB1_PINNED.get(name)
        require(
            not pin or pin == (len(data), digest),
            f"RB-1 file differs from approved bytes: {name}",
        )
        payload[name] = data
    return payload


def _payload(source):
    """Bytes of the RB-1 files: the verified payload, or (tests / legacy callers)
    read once from a folder and checked against the approved pins."""
    if isinstance(source, dict):
        return source
    package.rb1_artifacts(source)
    return {name: (source / name).read_bytes() for name in package.RB1_FILES}


def _stage_verifier(payload):
    namespace = {"__name__": "rb1_verify_stage"}
    exec(compile(payload["verify_stage.py"], "rb1_verify_stage", "exec"), namespace)  # noqa: S102 - signed bytes
    return namespace


def probe_program(assets):
    payload = _payload(assets)
    helper = payload["restore_rapidocr_assets.py"]
    gate = payload["runtime_gate.py"]
    manifest = payload["manifest.json"]
    return (
        "import hashlib, json\n"
        f"assert hashlib.sha256(open({STOCK!r}, 'rb').read()).hexdigest() == {STOCK_SHA!r}\n"
        "helper, gate = {}, {}\n"
        f"exec(compile({helper!r}, 'rb1_helper', 'exec'), helper)\n"
        f"exec(compile({gate!r}, 'rb1_gate', 'exec'), gate)\n"
        f"raise SystemExit(gate['verdict'](helper, json.loads({manifest!r})))\n"
    )


def probe(command, program):
    result = package.run(command, check=False, timeout=900, input_text=program)
    lines = [line[4:] for line in result.stdout.splitlines() if line.startswith("RB1 ")]
    data = json.loads(lines[-1]) if lines else {}
    failure = {
        2: "rollback metadata is invalid",
        3: "runtime or backend is incompatible (requires persistent torch)",
        4: "persistent model identity does not match",
        5: "dictionary asset is missing or incompatible",
        6: "the dictionary target contains an unexpected file",
        7: "the installed recognizer dictionary path differs",
    }.get(result.returncode, "no successful runtime or offline cache verdict")
    require(
        result.returncode == 0
        and data.get("result") in ("already valid", "missing - would restore"),
        f"rollback could not be verified: {failure} (probe exit {result.returncode})",
    )
    return data["result"]


def data_mount(inspect):
    matches = []
    for mount in inspect.get("Mounts", []):
        target = mount.get("Destination", "")
        if target == "/app/data":
            matches.append(mount)
        else:
            require(
                not target.startswith("/app/data/") and target not in ("/", "/app"),
                "overlapping app data mount has no validated offline path",
            )
    require(len(matches) == 1, "expected one persistent /app/data mount")
    mount = matches[0]
    kind = mount.get("Type")
    source = mount.get("Name" if kind == "volume" else "Source")
    require(
        kind in ("bind", "volume")
        and source
        and not any(c in source for c in ',"\r\n'),
        "unsupported app data mount",
    )
    return f"type={kind},source={source},target=/app/data,readonly"


def preflight(assets, app, image, deploy_tag, service=None):
    """``assets``: the verified payload (or a folder, read once). ``service``:
    the Compose service the override will name - it must be the running
    container's own Compose service label (12D13)."""
    require(
        package.IMAGE_ID_RE.fullmatch(image),
        "supply the full approved baseline image ID",
    )
    require(
        re.fullmatch(r"[0-9a-f]{12,64}", app), "supply the running app container ID"
    )
    require(
        package.TAGGED_REF_RE.fullmatch(deploy_tag), "supply the deployment image tag"
    )
    inspect = json.loads(
        package.run(["docker", "inspect", "--type", "container", app]).stdout
    )[0]
    pinned = package.docker_inspect_image(deploy_tag)
    require(
        inspect.get("Image") == image == pinned.get("Id")
        and inspect["State"]["Running"],
        "running app, deployment tag and approved baseline image must match",
    )
    require(
        pinned["Config"].get("Entrypoint") == [STOCK],
        "baseline entrypoint is incompatible",
    )
    revision = (pinned["Config"].get("Labels") or {}).get(package.REVISION_LABEL)
    require(
        not revision or revision == package.RB1_BASE, "baseline image revision differs"
    )
    if service is not None:
        labels = inspect["Config"].get("Labels") or {}
        require(
            package.SERVICE_RE.fullmatch(service)
            and labels.get(COMPOSE_SERVICE_LABEL) == service,
            "the application service name differs from the running container's Compose service label",
        )
    environment = dict(
        value.split("=", 1) for value in inspect["Config"]["Env"] if "=" in value
    )
    require(
        all(
            environment.get(key) == "true"
            for key in (
                "OCR_OFFLINE",
                "OCR_RAPIDOCR_PERSISTENT",
                "OPEN_NOTEBOOK_ENABLE_DOCLING",
            )
        )
        and environment.get("OPEN_NOTEBOOK_ENABLE_CRAWL4AI", "false") == "false",
        "verified rollback requires offline Docling, persistent torch RapidOCR and disabled local Crawl4AI",
    )
    cache = PurePosixPath(environment.get("UV_CACHE_DIR", "/app/data/.cache/uv"))
    require(
        PurePosixPath("/app/data") in cache.parents and ".." not in cache.parts,
        "uv cache must be on the persistent app data volume",
    )
    mount = data_mount(inspect)
    program = probe_program(assets)
    status = probe(["docker", "exec", "-i", app, PYTHON, "-I", "-B", "-"], program)
    # uv needs scratch writes while reinstalling. Only a disposable container is
    # written; the target data/cache mount stays read-only and no network is attached.
    disposable = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "-i",
        "--mount",
        mount,
        "--entrypoint",
        "/bin/sh",
        "-e",
        "UV_OFFLINE=1",
        "-e",
        "UV_LINK_MODE=copy",
    ]
    for key in ENVIRONMENT:
        if key in environment:
            disposable += ["-e", f"{key}={environment[key]}"]
    disposable += [
        image,
        "-eu",
        "-c",
        'cache=$(mktemp -d); cp -a "$1/." "$cache"; export UV_CACHE_DIR="$cache"; exec "$2" "$3" -I -B -',
        "rb1-cache",
        str(cache),
        STOCK,
        PYTHON,
    ]
    probe(disposable, program)
    return "A-valid" if status == "already valid" else "B-recoverable"


def compose(app, dest):
    return {
        "services": {
            app: {
                "entrypoint": ENTRYPOINT,
                "command": [],
                "pull_policy": "never",
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(dest),
                        "target": MOUNT,
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }
                ],
            }
        }
    }


def _outside_checkout(dest, package_root):
    """The stage must survive the package / checkout being removed (12D13)."""
    resolved = Path(os.path.abspath(dest))
    if package_root is not None:
        work = Path(os.path.abspath(package_root)).parent
        require(
            work != resolved and work not in resolved.parents,
            "stage outside the package folder and its work folder ($WORK)",
        )
    require(
        not any((folder / ".git").exists() for folder in resolved.parents),
        "stage outside any source checkout",
    )


def stage_assets(
    assets,
    dest,
    app,
    image,
    deploy_tag,
    *,
    signed=None,
    package_root=None,
    allowed_signers=None,
    identity=None,
):
    """Stage the verified payload bytes (never re-read from the package) into a
    new persistent folder. With ``signed`` (manifest bytes, signature bytes) the
    stage also carries the signed package manifest, is verified with the
    trusted key BEFORE it is put in place and again where it lies, and is made
    read-only (12D13)."""
    require(
        dest.is_absolute() and not dest.is_symlink() and not dest.exists(),
        "stage in a new absolute trusted directory outside the source checkout",
    )
    _outside_checkout(dest, package_root)
    package._check_trusted_file(dest.parent, "RB-1 persistent parent")
    require(package.SERVICE_RE.fullmatch(app), "invalid application service name")
    require(
        package.IMAGE_ID_RE.fullmatch(image)
        and package.TAGGED_REF_RE.fullmatch(deploy_tag),
        "invalid baseline image or deployment tag",
    )
    payload = _payload(assets)
    verifier = _stage_verifier(payload)
    with tempfile.TemporaryDirectory(prefix=".rb1-", dir=dest.parent) as scratch:
        stage = Path(scratch) / "payload"
        for name in package.RB1_FILES:
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload[name])
            path.chmod(0o444)
        override = stage / "compose.json"
        override.write_text(
            json.dumps(verifier["override"](app, dest), indent=2) + "\n",
            encoding="utf-8",
        )
        override.chmod(0o444)
        generated = [
            ("baseline-image", image + "\n"),
            ("deploy-tag", deploy_tag + "\n"),
        ]
        if signed is not None:
            generated += [
                ("signed-manifest.json", signed[0]),
                ("signed-manifest.json.sig", signed[1]),
            ]
        for name, value in generated:
            pin = stage / name
            pin.write_bytes(value.encode("utf-8") if isinstance(value, str) else value)
            pin.chmod(0o444)
        # every staged file = the verified payload (full set, not only the pins)
        for name in package.RB1_FILES:
            require(
                (stage / name).read_bytes() == payload[name],
                f"staged {name} differs from the verified payload",
            )
        if signed is not None:
            _verify_stage(verifier, stage, dest, allowed_signers, identity, app)
        stage.rename(dest)
    for folder in sorted(
        (p for p in dest.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)
    ):
        folder.chmod(0o555)
    dest.chmod(0o555)
    if signed is not None:
        _verify_stage(verifier, dest, dest, allowed_signers, identity, app)


def _verify_stage(verifier, stage, location, allowed_signers, identity, app):
    try:
        result = verifier["verify"](
            stage, Path(allowed_signers), identity, app, location=location
        )
    except (verifier["Refused"], OSError, ValueError, KeyError, TypeError) as exc:
        raise package.Refused(
            f"RB-1 REFUSED: staged state could not be verified ({exc})",
            package.EXIT_PREFLIGHT,
        ) from None
    require(result.get("rb1_stage") == "verified", "staged state not verified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--allowed-signers", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--app-container", required=True)
    parser.add_argument("--baseline-image", required=True)
    parser.add_argument("--deploy-tag", required=True)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--app-service", default="open_notebook")
    args = parser.parse_args(argv)
    root = args.package_dir.resolve()
    try:
        package._check_trusted_file(root, "rollback package directory")
        # the manifest and its signature are read once: the bytes the signature
        # covers are the bytes every later check and the stage use (12D13)
        manifest_bytes = (root / package.MANIFEST).read_bytes()
        signature = (root / package.SIGNATURE).read_bytes()
        require(
            package.verify_signature_bytes(
                manifest_bytes, signature, args.allowed_signers, args.identity
            )
            == "valid",
            "trusted release signature is required",
        )
        manifest = package.verify_tree(root, None, "1.2.0", None)
        require(
            manifest == json.loads(manifest_bytes.decode("utf-8")),
            "package manifest changed during verification",
        )
        require(
            package.requires_rb1(manifest)
            and manifest["readiness"]["status"] == "READY",
            "package is not ready for the verified baseline",
        )
        payload = load_payload(root, manifest)
        result = preflight(
            payload,
            args.app_container,
            args.baseline_image,
            args.deploy_tag,
            service=args.app_service,
        )
        if args.stage:
            stage_assets(
                payload,
                args.stage,
                args.app_service,
                args.baseline_image,
                args.deploy_tag,
                signed=(manifest_bytes, signature),
                package_root=root,
                allowed_signers=args.allowed_signers,
                identity=args.identity,
            )
        print(json.dumps({"rollback": result, "staged": bool(args.stage)}))
        return 0
    except (package.Refused, OSError, ValueError, KeyError, IndexError) as exc:
        print(
            str(exc)
            if isinstance(exc, package.Refused)
            else "RB-1 REFUSED: unreadable package or deployment metadata",
            file=sys.stderr,
        )
        return package.EXIT_PREFLIGHT


if __name__ == "__main__":
    raise SystemExit(main())
