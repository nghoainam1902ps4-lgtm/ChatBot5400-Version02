#!/usr/bin/env python3
"""End-to-end API driver for the OCR Engine Manager acceptance (stdlib only).

Runs INSIDE the app container (copied in with `docker cp`, executed with the
container's Python) so it reaches the API on 127.0.0.1 even when the container
has no Internet. Every step is a real HTTP call against the running backend +
surreal-commands worker — no CLI shortcuts.

Sub-commands (all print one JSON line and exit 0 = PASS, 1 = FAIL, 2 = NOT VERIFIED):

  wait-ready     API /health answers and admin login works
  ocr-e2e        install -> job status -> activate -> test -> upload PDF ->
                 source processed -> expected text present -> engine in worker log
  settings-set   write a marker setting (for upgrade tests)
  settings-check verify the marker + active OCR engine survived an upgrade
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

PASS, FAIL, NOT_VERIFIED = 0, 1, 2


class Api:
    def __init__(self, base: str, timeout: float = 60.0):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        raw: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
                return resp.status, json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(text)
            except ValueError:
                return e.code, text

    def login(self, user: str, password: str) -> None:
        status, body = self.call(
            "POST", "/api/auth/login", {"username": user, "password": password}
        )
        if status != 200:
            raise RuntimeError(f"login failed: HTTP {status} {body}")
        self.token = body["access_token"]

    def upload(self, path: Path, fields: dict[str, str]) -> tuple[int, Any]:
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in fields.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            )
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
            + path.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return self.call(
            "POST",
            "/api/sources",
            raw=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
        )


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def out(result: dict[str, Any], code: int) -> int:
    result["result"] = {PASS: "PASS", FAIL: "FAIL", NOT_VERIFIED: "NOT VERIFIED"}[code]
    print(json.dumps(result, ensure_ascii=False))
    return code


def poll(fn, timeout: float, interval: float = 3.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last is not None:
            return last
        time.sleep(interval)
    return None


def wait_job(api: Api, job_id: str, timeout: float) -> dict[str, Any] | None:
    def check():
        status, body = api.call("GET", f"/api/ocr/jobs/{job_id}")
        if status == 200 and body.get("status") in ("completed", "failed", "canceled"):
            return body
        return None

    return poll(check, timeout)


def engine(api: Api, engine_id: str) -> dict[str, Any]:
    status, body = api.call("GET", f"/api/ocr/engines/{engine_id}")
    if status != 200:
        raise RuntimeError(f"GET engine {engine_id}: HTTP {status} {body}")
    return body


def cmd_wait_ready(a) -> int:
    api = Api(a.api)

    def ready():
        try:
            status, _ = api.call("GET", "/health")
            return True if status == 200 else None
        except Exception:
            return None

    if not poll(ready, a.timeout, 5):
        return out({"step": "api_ready"}, FAIL)
    try:
        api.login(a.user, a.password)
    except Exception as e:
        return out({"step": "admin_login", "error": str(e)}, FAIL)
    if a.no_ocr:  # a version without the OCR Engine Manager (upgrade test)
        return out({"step": "ready", "ocr_api": False}, PASS)
    status, body = api.call("GET", "/api/ocr/engines")
    if status != 200:
        return out({"step": "ocr_api", "http": status, "body": body}, FAIL)
    return out(
        {
            "step": "ready",
            "docling_available": body["general"]["docling_available"],
            "dependency_problems": body["general"].get("dependency_problems"),
        },
        PASS,
    )


def cmd_ocr_e2e(a) -> int:
    api = Api(a.api, timeout=120)
    report: dict[str, Any] = {"engine": a.engine, "steps": {}}
    steps = report["steps"]
    api.login(a.user, a.password)

    status, eng = api.call("GET", "/api/ocr/engines")
    general = eng["general"]
    steps["docling_runtime"] = general["docling_available"]
    steps["layout_model"] = general.get("layout_model")
    steps["table_model"] = general.get("table_model")
    if not general["docling_available"]:
        report["error"] = (
            "Docling runtime not available (OPEN_NOTEBOOK_ENABLE_DOCLING=true?)"
        )
        return out(report, NOT_VERIFIED)
    if general.get("dependency_problems"):
        report["error"] = f"dependency problems: {general['dependency_problems']}"
        return out(report, FAIL)

    e = engine(api, a.engine)
    if e["runtime"]["status"] != "ready":
        report["error"] = (
            f"runtime {e['runtime']['status']}: {e['runtime'].get('detail')}"
        )
        return out(report, NOT_VERIFIED)
    if not e["builtin"] and not e["ready"]:
        status, job = api.call("POST", f"/api/ocr/engines/{a.engine}/install")
        steps["install_http"] = status
        if status != 202:
            report["error"] = f"install refused: {job}"
            return out(report, FAIL)
        done = wait_job(api, job["job_id"], a.timeout)
        steps["install_job"] = (done or {}).get("status")
        e = engine(api, a.engine)
        steps["install_sources"] = (e.get("model") or {}).get("status")
        if not e["ready"]:
            report["error"] = (
                f"engine not ready after install: {e.get('state')} {e.get('error')}"
            )
            return out(report, FAIL)
    steps["model_status"] = e["model"]["status"]

    status, body = api.call("POST", f"/api/ocr/engines/{a.engine}/activate")
    steps["activate_http"] = status
    if status != 200 or not body.get("active"):
        report["error"] = f"activate failed: {body}"
        return out(report, FAIL)

    status, job = api.call("POST", f"/api/ocr/engines/{a.engine}/test")
    steps["test_http"] = status
    done = wait_job(api, job["job_id"], a.timeout) if status == 202 else None
    test_result = ((done or {}).get("result") or {}).get("result") or {}
    steps["test_success"] = test_result.get("success")
    steps["test_ocr_models"] = test_result.get("ocr_models")
    steps["test_cer"] = test_result.get("cer")
    if not test_result.get("success"):
        report["error"] = f"engine test failed: {test_result.get('error') or done}"
        return out(report, FAIL)

    status, nb = api.call(
        "POST",
        "/api/notebooks",
        {"name": f"OCR acceptance {a.engine} {int(time.time())}"},
    )
    if status not in (200, 201):
        report["error"] = f"create notebook: HTTP {status} {nb}"
        return out(report, FAIL)
    status, src = api.upload(
        Path(a.pdf),
        {
            "type": "upload",
            "notebooks": json.dumps([nb["id"]]),
            "embed": "false",
            "async_processing": "true",
            "title": "",
        },
    )
    steps["upload_http"] = status
    if status not in (200, 201):
        report["error"] = f"upload: HTTP {status} {src}"
        return out(report, FAIL)
    source_id = src["id"]

    def processed():
        s, body = api.call("GET", f"/api/sources/{source_id}/status")
        if s == 200 and body.get("status") in ("completed", "failed"):
            return body
        return None

    final = poll(processed, a.timeout, 5)
    steps["source_status"] = (final or {}).get("status")
    if not final or final.get("status") != "completed":
        report["error"] = f"source processing did not complete: {final}"
        return out(report, FAIL)
    s, full = api.call("GET", f"/api/sources/{source_id}")
    text = norm(full.get("full_text") or "")
    missing = [p for p in a.expect if norm(p) not in text]
    steps["expected_missing"] = missing
    # Lets a caller compare two runs (online vs offline) without printing the text.
    steps["text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    steps["source_id"] = source_id
    if missing:
        report["error"] = "expected text missing from the processed source"
        return out(report, FAIL)
    return out(report, PASS)


def _queue_and_wait(
    api: Api, path: str, timeout: float
) -> tuple[dict[str, Any] | None, int]:
    status, job = api.call("POST", path)
    if status != 202:
        return {"http": status, "body": job}, status
    return wait_job(api, job["job_id"], timeout), status


def cmd_prepare(a) -> int:
    """Online preparation via the API/worker; PASS only when offline_ready."""
    api = Api(a.api, timeout=120)
    api.login(a.user, a.password)
    report: dict[str, Any] = {"engine": a.engine}
    e = engine(api, a.engine)
    if e["runtime"]["status"] != "ready":
        report["error"] = (
            f"runtime {e['runtime']['status']}: {e['runtime'].get('detail')}"
        )
        return out(report, NOT_VERIFIED)
    if not e["builtin"] and not e["ready"]:
        done, status = _queue_and_wait(
            api, f"/api/ocr/engines/{a.engine}/install", a.timeout
        )
        report["install"] = (done or {}).get("status")
    done, status = _queue_and_wait(
        api, f"/api/ocr/engines/{a.engine}/prepare", a.timeout
    )
    report["prepare_job"] = (done or {}).get("status")
    result = ((done or {}).get("result") or {}).get("result") or {}
    report["steps"] = result.get("steps")
    readiness = engine(api, a.engine).get("readiness") or {}
    report["readiness"] = {
        k: readiness.get(k)
        for k in ("state", "pipeline_ok", "local_only_verified", "offline_verified")
    }
    if readiness.get("state") != "offline_ready":
        report["error"] = result.get("error") or (
            readiness.get("last_check") or {}
        ).get("error")
        return out(report, FAIL)
    return out(report, PASS)


def cmd_readiness_check(a) -> int:
    api = Api(a.api, timeout=120)
    api.login(a.user, a.password)
    done, status = _queue_and_wait(
        api, f"/api/ocr/engines/{a.engine}/readiness-check", a.timeout
    )
    readiness = engine(api, a.engine).get("readiness") or {}
    last = readiness.get("last_check") or {}
    report = {
        "engine": a.engine,
        "job": (done or {}).get("status"),
        "state": readiness.get("state"),
        "mode": last.get("mode"),
        "offline_verified": readiness.get("offline_verified"),
        "layout_model": last.get("layout_model"),
        "table": f"{last.get('table_model')} ({last.get('table_mode')})",
        "error": last.get("error"),
    }
    ok = readiness.get("state") == "offline_ready"
    if a.require_offline:
        ok = ok and bool(readiness.get("offline_verified"))
    return out(report, PASS if ok else FAIL)


MARKER_NOTEBOOK = "OCR acceptance marker notebook"


def cmd_page_orientation(a) -> int:
    """What the API reports about page-orientation correction (D-25 / D-27)."""
    api = Api(a.api)
    api.login(a.user, a.password)
    status, body = api.call("GET", "/api/ocr/engines")
    if status != 200:
        return out({"step": "ocr_api", "http": status}, FAIL)
    po = (body.get("general") or {}).get("page_orientation") or {}
    report = {
        "page_orientation": po,
        "quality": {e["id"]: e.get("quality") for e in body.get("engines", [])},
    }
    if a.expect == "available" and not po.get("available"):
        return out(report, FAIL)
    if a.expect == "unavailable" and (po.get("available") or po.get("reason") == "ok"):
        return out(report, FAIL)
    return out(report, PASS)


def cmd_seed_data(a) -> int:
    api = Api(a.api)
    api.login(a.user, a.password)
    s, nb = api.call(
        "POST",
        "/api/notebooks",
        {"name": MARKER_NOTEBOOK, "description": "kept across upgrades"},
    )
    return out({"step": "seed_data", "http": s}, PASS if s in (200, 201) else FAIL)


def cmd_check_data(a) -> int:
    api = Api(a.api)
    api.login(a.user, a.password)
    s, nbs = api.call("GET", "/api/notebooks")
    found = s == 200 and any(n.get("name") == MARKER_NOTEBOOK for n in (nbs or []))
    return out(
        {"step": "check_data", "marker_notebook": found}, PASS if found else FAIL
    )


MARKER_THREADS = 3


def cmd_settings_set(a) -> int:
    api = Api(a.api)
    api.login(a.user, a.password)
    s1, b1 = api.call("PUT", "/api/settings", {"podcast_enabled": False})
    s2, b2 = (
        api.call("PUT", "/api/ocr/config", {"docling_ocr_num_threads": MARKER_THREADS})
        if a.with_ocr
        else (200, None)
    )
    ok = s1 == 200 and s2 == 200
    return out(
        {"step": "settings_set", "settings": s1, "ocr_config": s2}, PASS if ok else FAIL
    )


def cmd_settings_check(a) -> int:
    api = Api(a.api)
    api.login(a.user, a.password)
    s, settings = api.call("GET", "/api/settings")
    result: dict[str, Any] = {
        "step": "settings_check",
        "podcast_enabled": settings.get("podcast_enabled"),
    }
    ok = s == 200 and settings.get("podcast_enabled") is False
    if a.with_ocr:
        s2, cfg = api.call("GET", "/api/ocr/config")
        result["ocr_config"] = cfg
        ok = ok and cfg.get("docling_ocr_num_threads") == MARKER_THREADS
        if a.engine:
            ok = ok and cfg.get("docling_ocr_engine") == a.engine
    return out(result, PASS if ok else FAIL)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:5055")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--timeout", type=float, default=1800)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait-ready")
    w.add_argument("--no-ocr", action="store_true", help="target predates /api/ocr")
    e = sub.add_parser("ocr-e2e")
    e.add_argument("--engine", required=True)
    e.add_argument("--pdf", required=True)
    e.add_argument("--expect", action="append", default=[])
    s = sub.add_parser("settings-set")
    s.add_argument("--with-ocr", action="store_true")
    c = sub.add_parser("settings-check")
    c.add_argument("--with-ocr", action="store_true")
    c.add_argument("--engine")
    p = sub.add_parser("prepare")
    p.add_argument("--engine", required=True)
    r = sub.add_parser("readiness-check")
    r.add_argument("--engine", required=True)
    r.add_argument("--require-offline", action="store_true")
    o = sub.add_parser("page-orientation")
    o.add_argument("--expect", choices=["available", "unavailable", ""], default="")
    sub.add_parser("seed-data")
    sub.add_parser("check-data")
    a = ap.parse_args()
    try:
        return {
            "prepare": cmd_prepare,
            "readiness-check": cmd_readiness_check,
            "seed-data": cmd_seed_data,
            "page-orientation": cmd_page_orientation,
            "check-data": cmd_check_data,
            "wait-ready": cmd_wait_ready,
            "ocr-e2e": cmd_ocr_e2e,
            "settings-set": cmd_settings_set,
            "settings-check": cmd_settings_check,
        }[a.cmd](a)
    except Exception as exc:  # report, never a traceback-only failure
        return out({"step": a.cmd, "error": f"{type(exc).__name__}: {exc}"}, FAIL)


if __name__ == "__main__":
    sys.exit(main())
