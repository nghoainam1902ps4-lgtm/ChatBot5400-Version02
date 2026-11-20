"""Phase 12D13 - RB-1 hardening controls (the residual points of Phase 12D12 R08).

Synthetic package metadata, real ssh-keygen signatures, a fake ``docker``.
Each control names the D12 point it closes:

1. the selector never answers "no override" for broken metadata;
2. every staged file is checked against the signed manifest (not only the pins);
3. the bytes verified are the bytes probed and staged (no verify -> stage gap);
4. the persistent stage is a trust boundary: owner / mode / exact file set,
   verified with the operator's key after staging (verify_stage.py);
5. the application service must be the running container's Compose label;
6. the stage does not depend on the package / checkout (and cannot be inside it);
7. fail-closed startup is unchanged (tests/test_phase12d11_rb1.py keeps it).
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.offline import offline_package as package
from scripts.offline import rb1_setup as setup

ASSETS = Path(setup.__file__).with_name("rb1")
IMAGE = "sha256:" + "a" * 64
OTHER = "sha256:" + "c" * 64
TAG = "chatbot5400:local"
IDENTITY = "release@test"

posix = pytest.mark.skipif(os.name != "posix", reason="Linux target staging")
keygen = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen")


def _signed_manifest(payload: dict) -> bytes:
    files = {
        f"{package.RB1_DIR}/{name}": {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for name, data in payload.items()
    }
    return json.dumps({"files": files}, sort_keys=True).encode()


@pytest.fixture
def signer(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    key = keys / "release"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", str(key)],
        check=True,
    )
    signers = keys / "allowed_signers"
    signers.write_text(f"{IDENTITY} " + (keys / "release.pub").read_text())

    def sign(data: bytes) -> bytes:
        subject = keys / "subject"
        subject.write_bytes(data)
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-Y",
                "sign",
                "-f",
                str(key),
                "-n",
                package.SIG_NAMESPACE,
                str(subject),
            ],
            check=True,
            capture_output=True,
        )
        return (keys / "subject.sig").read_bytes()

    return SimpleNamespace(allowed=signers, sign=sign, keys=keys)


def _payload():
    return {name: (ASSETS / name).read_bytes() for name in package.RB1_FILES}


def _stage(tmp_path, signer, payload=None, name="state"):
    payload = payload or _payload()
    signed = _signed_manifest(payload)
    parent = tmp_path / "persistent"
    parent.mkdir(exist_ok=True)
    dest = parent / name
    setup.stage_assets(
        payload,
        dest,
        "open_notebook",
        IMAGE,
        TAG,
        signed=(signed, signer.sign(signed)),
        package_root=tmp_path / "work" / "pkg",
        allowed_signers=signer.allowed,
        identity=IDENTITY,
    )
    return dest


def _verify(dest, signer, *extra):
    out = subprocess.run(
        [
            "python3",
            "-I",
            str(dest / "verify_stage.py"),
            "--allowed-signers",
            str(signer.allowed),
            "--identity",
            IDENTITY,
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])


def _select(dest, tmp_path, image=IMAGE):
    fake = tmp_path / "bin" / "docker"
    fake.parent.mkdir(exist_ok=True)
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_IMAGE"\n')
    fake.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
        TEST_IMAGE=image,
    )
    return subprocess.run(
        ["/bin/sh", str(dest / "select-compose.sh")],
        env=env,
        capture_output=True,
        text=True,
    )


def _writable(path: Path):
    """Undo the read-only stage for one negative case (the test runs as the owner)."""
    for p in (path, *path.parents):
        if p.name == "persistent":
            break
        p.chmod(p.stat().st_mode | 0o200)


# --------------------------------------------------------------------------- #
# 1. selector: broken metadata is never "no override"
# --------------------------------------------------------------------------- #


@posix
@keygen
@pytest.mark.parametrize(
    "name,raw",
    [
        ("baseline-image", (IMAGE[:-3] + "\n").encode()),  # truncated
        ("baseline-image", (IMAGE + "\r\n").encode()),  # CRLF
        ("baseline-image", (IMAGE.upper() + "\n").encode()),  # case
        ("baseline-image", (IMAGE + "\n" + IMAGE + "\n").encode()),  # two lines
        ("baseline-image", IMAGE.encode()),  # no LF
        ("baseline-image", b""),  # empty
        ("deploy-tag", (TAG + "\r\n").encode()),
        ("deploy-tag", b"\n"),
    ],
)
def test_selector_refuses_malformed_pins_instead_of_answering_no_override(
    tmp_path, signer, name, raw
):
    dest = _stage(tmp_path, signer)
    assert _select(dest, tmp_path).stdout.strip() == str(dest / "compose.json")
    _writable(dest / name)
    (dest / name).write_bytes(raw)
    for image in (IMAGE, OTHER):  # whatever the tag points to
        result = _select(dest, tmp_path, image)
        assert result.returncode != 0 and result.stdout == "", (name, raw, result)


@posix
@keygen
def test_selector_contract_and_docker_errors(tmp_path, signer):
    dest = _stage(tmp_path, signer)
    assert _select(dest, tmp_path, OTHER).returncode == 0
    assert _select(dest, tmp_path, OTHER).stdout == ""  # tag on another image
    for broken in ("", "sha256:short", IMAGE + "x"):
        assert _select(dest, tmp_path, broken).returncode != 0
    _writable(dest / "compose.json")
    (dest / "compose.json").unlink()
    assert _select(dest, tmp_path, IMAGE).returncode != 0


@posix
@keygen
def test_an_emptied_selector_is_caught_by_the_stage_verifier(tmp_path, signer):
    dest = _stage(tmp_path, signer)
    assert _verify(dest, signer)[0] == 0
    _writable(dest / "select-compose.sh")
    (dest / "select-compose.sh").write_bytes(b"")
    # an empty selector exits 0 with no output (= "no override") ...
    assert _select(dest, tmp_path).returncode == 0
    assert _select(dest, tmp_path).stdout == ""
    # ... which is why every start runs the verifier first
    code, report = _verify(dest, signer)
    assert code == 3 and "select-compose.sh" in report["reason"]


# --------------------------------------------------------------------------- #
# 2-4. staged bytes = signed bytes; the stage is a verified trust boundary
# --------------------------------------------------------------------------- #


@posix
@keygen
def test_stage_is_complete_signed_read_only_and_verifiable_without_the_package(
    tmp_path, signer
):
    dest = _stage(tmp_path, signer)
    code, report = _verify(dest, signer, "--service", "open_notebook")
    assert code == 0 and report["rb1_stage"] == "verified", report
    assert report["baseline_image"] == IMAGE and report["deploy_tag"] == TAG
    for name in package.RB1_FILES:
        assert (dest / name).read_bytes() == (ASSETS / name).read_bytes()
    assert not dest.stat().st_mode & 0o222  # folder read-only
    assert all(not p.stat().st_mode & 0o222 for p in dest.rglob("*"))
    config = json.loads((dest / "compose.json").read_text())
    assert config == setup.compose("open_notebook", dest)
    # 6. no reference to the package / checkout: the verifier runs from the stage
    assert str(ASSETS) not in (dest / "compose.json").read_text()
    assert _verify(dest, signer, "--service", "other")[0] == 3


@posix
@keygen
@pytest.mark.parametrize(
    "tamper",
    [
        "dictionary byte",
        "runtime gate",
        "startup",
        "verifier key",
        "extra file",
        "missing file",
        "compose image",
        "compose writable mount",
        "group writable file",
        "symlink",
        "other signer",
        "manifest swapped",
    ],
)
def test_stage_verifier_refuses_any_change_after_staging(tmp_path, signer, tamper):
    dest = _stage(tmp_path, signer)
    assert _verify(dest, signer)[0] == 0
    target = {
        "dictionary byte": "assets/rapidocr/ppocrv6_dict.txt",
        "runtime gate": "runtime_gate.py",
        "startup": "startup.sh",
        "verifier key": "verify_stage.py",
    }.get(tamper)
    if target:
        _writable(dest / target)
        data = (dest / target).read_bytes()
        if target.endswith((".py", ".sh")):  # still runs, but not the signed bytes
            (dest / target).write_bytes(data + b"\n# tampered\n")
        else:
            (dest / target).write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    elif tamper == "extra file":
        _writable(dest)
        (dest / "notes.txt").write_text("x")
    elif tamper == "missing file":
        _writable(dest / "LICENSE.txt")
        (dest / "LICENSE.txt").unlink()
    elif tamper.startswith("compose"):
        _writable(dest / "compose.json")
        config = json.loads((dest / "compose.json").read_text())
        service = config["services"]["open_notebook"]
        if tamper == "compose image":
            service["image"] = "chatbot5400:other"
        else:
            service["volumes"][0]["read_only"] = False
        (dest / "compose.json").write_text(json.dumps(config))
    elif tamper == "group writable file":
        (dest / "runtime_gate.py").chmod(0o664)
    elif tamper == "symlink":
        _writable(dest / "LICENSE.txt")
        (dest / "LICENSE.txt").unlink()
        (dest / "LICENSE.txt").symlink_to(ASSETS / "LICENSE.txt")
    elif tamper == "other signer":
        other = tmp_path / "other"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)],
            check=True,
        )
        _writable(dest / "signed-manifest.json.sig")
        subject = tmp_path / "subject"
        subject.write_bytes((dest / "signed-manifest.json").read_bytes())
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-Y",
                "sign",
                "-f",
                str(other),
                "-n",
                package.SIG_NAMESPACE,
                str(subject),
            ],
            check=True,
            capture_output=True,
        )
        (dest / "signed-manifest.json.sig").write_bytes(
            (tmp_path / "subject.sig").read_bytes()
        )
    else:  # replace the dictionary AND the manifest next to it (12D12 R08)
        _writable(dest / "manifest.json")
        _writable(dest / "assets/rapidocr/ppocrv6_dict.txt")
        (dest / "assets/rapidocr/ppocrv6_dict.txt").write_bytes(b"forged")
        meta = json.loads((dest / "manifest.json").read_text())
        meta["assets"]["dictionary"].update(
            size=6, sha256=hashlib.sha256(b"forged").hexdigest()
        )
        (dest / "manifest.json").write_text(json.dumps(meta))
    assert _verify(dest, signer)[0] == 3, tamper


@posix
@keygen
def test_staged_bytes_are_the_verified_bytes_not_a_later_disk_read(tmp_path, signer):
    root = tmp_path / "work" / "pkg"
    shutil.copytree(ASSETS, root / package.RB1_DIR)
    payload = setup.load_payload(root, json.loads(_signed_manifest(_payload())))
    # the package file changes AFTER verification (12D12 R08 verify -> stage gap)
    gate = root / package.RB1_DIR / "runtime_gate.py"
    gate.write_bytes(gate.read_bytes() + b"\nraise SystemExit(0)\n")
    dest = _stage(tmp_path, signer, payload=payload)
    assert (dest / "runtime_gate.py").read_bytes() == (
        ASSETS / "runtime_gate.py"
    ).read_bytes()
    assert "raise SystemExit(0)" not in setup.probe_program(payload)


@posix
def test_payload_is_checked_against_the_signed_manifest_for_every_file(tmp_path):
    root = tmp_path / "pkg"
    shutil.copytree(ASSETS, root / package.RB1_DIR)
    good = json.loads(_signed_manifest(_payload()))
    assert set(setup.load_payload(root, good)) == set(package.RB1_FILES)
    for name in (
        "startup.sh",
        "runtime_gate.py",
        "select-compose.sh",
        "verify_stage.py",
    ):
        bad = json.loads(json.dumps(good))
        bad["files"][f"{package.RB1_DIR}/{name}"]["sha256"] = "0" * 64
        with pytest.raises(package.Refused, match="signed manifest"):
            setup.load_payload(root, bad)
    missing = json.loads(json.dumps(good))
    del missing["files"][f"{package.RB1_DIR}/verify_stage.py"]
    with pytest.raises(package.Refused, match="signed manifest"):
        setup.load_payload(root, missing)
    (root / package.RB1_DIR / "startup.sh").chmod(0o666)
    with pytest.raises(package.Refused, match="writable"):
        setup.load_payload(root, good)


# --------------------------------------------------------------------------- #
# 6. the stage cannot live inside the package, $WORK or a source checkout
# --------------------------------------------------------------------------- #


@posix
@keygen
def test_stage_location_is_outside_package_work_and_checkout(tmp_path, signer):
    payload = _payload()
    signed = _signed_manifest(payload)
    common = dict(
        signed=(signed, signer.sign(signed)),
        allowed_signers=signer.allowed,
        identity=IDENTITY,
    )
    work = tmp_path / "work"
    (work / "pkg").mkdir(parents=True)
    with pytest.raises(package.Refused, match="WORK"):
        setup.stage_assets(
            payload,
            work / "state",
            "open_notebook",
            IMAGE,
            TAG,
            package_root=work / "pkg",
            **common,
        )
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "deploy").mkdir()
    with pytest.raises(package.Refused, match="checkout"):
        setup.stage_assets(
            payload,
            checkout / "deploy" / "state",
            "open_notebook",
            IMAGE,
            TAG,
            package_root=work / "pkg",
            **common,
        )
    assert (
        not (work / "state").exists() and not (checkout / "deploy" / "state").exists()
    )


# --------------------------------------------------------------------------- #
# 5. the service named in the override is the running container's service
# --------------------------------------------------------------------------- #


def _inspect(labels):
    return {
        "Image": IMAGE,
        "State": {"Running": True},
        "Config": {
            "Env": [
                "OCR_OFFLINE=true",
                "OCR_RAPIDOCR_PERSISTENT=true",
                "OPEN_NOTEBOOK_ENABLE_DOCLING=true",
            ],
            "Labels": labels,
        },
        "Mounts": [{"Destination": "/app/data", "Type": "volume", "Name": "lab_data"}],
    }


@pytest.mark.parametrize(
    "labels,ok",
    [
        ({"com.docker.compose.service": "open_notebook"}, True),
        ({"com.docker.compose.service": "worker"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_preflight_binds_the_service_name_to_the_compose_label(monkeypatch, labels, ok):
    monkeypatch.setattr(
        package,
        "docker_inspect_image",
        lambda ref: {"Id": IMAGE, "Config": {"Entrypoint": [setup.STOCK]}},
    )

    def run(args, **kwargs):
        if args[1] == "inspect":
            return SimpleNamespace(stdout=json.dumps([_inspect(labels)]))
        return SimpleNamespace(
            returncode=0, stdout="RB1 " + json.dumps({"result": "already valid"})
        )

    monkeypatch.setattr(package, "run", run)

    def call():
        return setup.preflight(
            _payload(), "b" * 64, IMAGE, TAG, service="open_notebook"
        )

    if ok:
        assert call() == "A-valid"
    else:
        with pytest.raises(package.Refused, match="Compose service label"):
            call()


def test_verifier_file_list_matches_the_package_list():
    namespace = setup._stage_verifier(_payload())
    assert set(namespace["SIGNED"]) == set(package.RB1_FILES)
    assert (
        namespace["MOUNT"] == setup.MOUNT
        and namespace["ENTRYPOINT"] == setup.ENTRYPOINT
    )
