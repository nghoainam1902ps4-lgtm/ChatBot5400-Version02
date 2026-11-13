"""Validates scripts/ocr/acceptance_api.py (the Docker E2E driver) against a stub
HTTP server. This checks the DRIVER's protocol handling (login, multipart upload,
job/status polling, exit codes) — it is NOT product acceptance; the real run is
scripts/ocr/docker-acceptance.sh on a deployment machine.
"""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "ocr" / "acceptance_api.py"


class _State:
    def __init__(self, runtime="ready", source_text="Số: 1234/2024/QĐ-MẪU"):
        self.runtime = runtime
        self.source_text = source_text
        self.uploaded = b""
        self.calls: list[str] = []
        self.engine_ready = False
        self.active = "rapidocr"
        self.readiness = {"state": "pipeline_not_verified"}
        self.prepare_makes_ready = True
        self.notebooks: list[dict] = []


def _server(state: _State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _authed(self):
            return self.headers.get("Authorization") == "Bearer tok"

        def do_GET(self):  # noqa: N802
            state.calls.append("GET " + self.path)
            if self.path == "/health":
                return self._send(200, {"status": "ok"})
            if not self._authed():
                return self._send(401, {"detail": "no"})
            if self.path == "/api/ocr/engines":
                return self._send(
                    200,
                    {
                        "general": {
                            "docling_available": True,
                            "dependency_problems": [],
                            "layout_model": "layout_heron",
                            "table_model": "docling_tableformer (accurate)",
                        },
                        "config": {},
                        "engines": [],
                    },
                )
            if self.path == "/api/notebooks":
                return self._send(200, state.notebooks)
            if self.path.startswith("/api/ocr/engines/"):
                return self._send(
                    200,
                    {
                        "builtin": False,
                        "ready": state.engine_ready,
                        "state": "ready" if state.engine_ready else "not_installed",
                        "runtime": {"status": state.runtime, "detail": "x"},
                        "model": {
                            "status": "installed"
                            if state.engine_ready
                            else "not_installed"
                        },
                        "active": state.active == "tesseract_best",
                        "readiness": state.readiness,
                    },
                )
            if self.path.startswith("/api/ocr/jobs/"):
                job = self.path.rsplit("/", 1)[1]
                result = (
                    {
                        "result": {
                            "success": True,
                            "ocr_models": ["TesseractOcrCliModel"],
                            "cer": 0.0,
                        }
                    }
                    if job == "test1"
                    else {}
                )
                return self._send(
                    200, {"job_id": job, "status": "completed", "result": result}
                )
            if self.path.endswith("/status"):
                return self._send(200, {"status": "completed", "message": "ok"})
            if self.path.startswith("/api/sources/"):
                return self._send(
                    200, {"id": "source:1", "full_text": state.source_text}
                )
            return self._send(404, {})

        def do_POST(self):  # noqa: N802
            body = self._body()
            state.calls.append("POST " + self.path)
            if self.path == "/api/auth/login":
                return self._send(200, {"access_token": "tok", "user": {}})
            if not self._authed():
                return self._send(401, {"detail": "no"})
            if self.path.endswith("/install"):
                state.engine_ready = True
                return self._send(
                    202,
                    {
                        "job_id": "inst1",
                        "engine_id": "tesseract_best",
                        "state": "pending",
                    },
                )
            if self.path.endswith("/activate"):
                state.active = "tesseract_best"
                return self._send(200, {"active": True})
            if self.path.endswith("/prepare") or self.path.endswith("/readiness-check"):
                if state.prepare_makes_ready:
                    state.readiness = {
                        "state": "offline_ready",
                        "offline_verified": self.path.endswith("/readiness-check"),
                        "last_check": {
                            "mode": "offline",
                            "layout_model": "layout_heron",
                        },
                    }
                return self._send(
                    202,
                    {
                        "job_id": "prep1",
                        "engine_id": "tesseract_best",
                        "state": "pending",
                    },
                )
            if self.path.endswith("/test"):
                return self._send(
                    202,
                    {
                        "job_id": "test1",
                        "engine_id": "tesseract_best",
                        "state": "pending",
                    },
                )
            if self.path == "/api/notebooks":
                state.notebooks.append(json.loads(body or b"{}"))
                return self._send(200, {"id": "notebook:1"})
            if self.path == "/api/sources":
                state.uploaded = body
                return self._send(200, {"id": "source:1"})
            return self._send(404, {})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run(state, *args):
    srv = _server(state)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(DRIVER),
                "--api",
                f"http://127.0.0.1:{srv.server_port}",
                "--timeout",
                "10",
                *args,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        srv.shutdown()
    return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])


def test_wait_ready(tmp_path):
    code, out = _run(_State(), "wait-ready")
    assert code == 0 and out["result"] == "PASS"


def test_full_flow_pass(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    state = _State()
    code, out = _run(
        state,
        "ocr-e2e",
        "--engine",
        "tesseract_best",
        "--pdf",
        str(pdf),
        "--expect",
        "1234/2024/QĐ-MẪU",
    )
    assert code == 0, out
    order = [c.split("?")[0] for c in state.calls if c.startswith("POST")]
    assert order == [
        "POST /api/auth/login",
        "POST /api/ocr/engines/tesseract_best/install",
        "POST /api/ocr/engines/tesseract_best/activate",
        "POST /api/ocr/engines/tesseract_best/test",
        "POST /api/notebooks",
        "POST /api/sources",
    ]
    assert (
        b'name="file"; filename="doc.pdf"' in state.uploaded
        and b"%PDF-1.4 fake" in state.uploaded
    )
    assert b'name="async_processing"' in state.uploaded


def test_missing_expected_text_fails(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    code, out = _run(
        _State(source_text="khác"),
        "ocr-e2e",
        "--engine",
        "tesseract_best",
        "--pdf",
        str(pdf),
        "--expect",
        "1234/2024",
    )
    assert (
        code == 1
        and out["result"] == "FAIL"
        and out["steps"]["expected_missing"] == ["1234/2024"]
    )


def test_missing_runtime_is_not_verified(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    code, out = _run(
        _State(runtime="missing"), "ocr-e2e", "--engine", "easyocr", "--pdf", str(pdf)
    )
    assert code == 2 and out["result"] == "NOT VERIFIED"


@pytest.mark.parametrize("script", ["docker-acceptance.sh"])
def test_shell_scripts_parse(script):
    assert (
        subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "ocr" / script)]
        ).returncode
        == 0
    )


def test_prepare_requires_offline_ready():
    state = _State()
    code, out = _run(state, "prepare", "--engine", "tesseract_best")
    assert code == 0 and out["readiness"]["state"] == "offline_ready"
    assert "POST /api/ocr/engines/tesseract_best/install" in state.calls
    assert "POST /api/ocr/engines/tesseract_best/prepare" in state.calls


def test_readiness_check_reports_offline_verification():
    code, out = _run(
        _State(), "readiness-check", "--engine", "tesseract_best", "--require-offline"
    )
    assert code == 0 and out["offline_verified"] is True and out["mode"] == "offline"


def test_prepare_fails_when_never_offline_ready():
    state = _State()
    state.prepare_makes_ready = False
    state.readiness = {
        "state": "not_offline_ready",
        "last_check": {"error": "Heron missing"},
    }
    code, out = _run(state, "prepare", "--engine", "tesseract_best")
    assert code == 1 and out["result"] == "FAIL" and out["error"] == "Heron missing"


def test_seed_and_check_data():
    state = _State()
    assert _run(state, "seed-data")[0] == 0
    assert _run(state, "check-data")[0] == 0
    empty = _State()
    assert _run(empty, "check-data")[0] == 1
