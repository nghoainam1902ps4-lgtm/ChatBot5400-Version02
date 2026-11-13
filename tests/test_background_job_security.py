"""Background-job security (docs/security/BACKGROUND_JOB_SECURITY.md).

Uses only synthetic canary files inside pytest temp dirs and a local stub HTTP
server — never system files, secrets or real documents.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.utils import job_input_guard as guard

ENDPOINTS = [
    (
        "post",
        "/api/commands/jobs",
        {"command": "process_source", "app": "open_notebook", "input": {}},
    ),
    ("get", "/api/commands/jobs", None),
    ("get", "/api/commands/jobs/command:abc", None),
    ("delete", "/api/commands/jobs/command:abc", None),
    ("get", "/api/commands/registry/debug", None),
]


@pytest.fixture(autouse=True)
def _url_ingestion_enabled(monkeypatch):
    """This module covers behaviour WITH URL ingestion switched on (URL policy,
    engine routing). The deployment default is OFF (D-29); the switched-off
    behaviour is covered by tests/test_url_ingestion_switch.py."""
    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_URL_INGESTION", "true")


def _call(client, method, path, body, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is not None:
        return getattr(client, method)(path, json=body, headers=headers)
    return getattr(client, method)(path, headers=headers)


class TestGenericJobApiAuthorization:
    @pytest.fixture(autouse=True)
    def _enforce_auth(self, monkeypatch):
        monkeypatch.setenv(
            "OPEN_NOTEBOOK_JWT_SECRET", "test-secret-key-for-job-security-tests"
        )
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)

    @pytest.fixture
    def client(self):
        from api.main import app

        return TestClient(app)

    @pytest.mark.parametrize("method,path,body", ENDPOINTS)
    def test_unauthenticated_rejected(self, client, method, path, body):
        assert _call(client, method, path, body).status_code == 401

    @pytest.mark.parametrize("role", ["user", "contributor", "approver"])
    @pytest.mark.parametrize("method,path,body", ENDPOINTS)
    def test_non_admin_forbidden(self, client, role, method, path, body):
        from api.auth import create_access_token

        token = create_access_token(f"user:{role}", role, role)
        with patch(
            "api.routers.commands.CommandService.submit_command_job", new=AsyncMock()
        ) as submit:
            r = _call(client, method, path, body, token)
        assert r.status_code == 403
        submit.assert_not_called()

    @pytest.mark.parametrize(
        "command",
        [
            "process_source",
            "run_transformation",
            "rebuild_embeddings",
            "generate_podcast",
            "ocr_install_model",
        ],
    )
    def test_generic_submission_disabled_even_for_admin(self, client, command):
        from api.auth import create_access_token

        token = create_access_token("user:admin", "admin", "admin")
        body = {
            "command": command,
            "app": "open_notebook",
            "input": {"content_state": {"file_path": "/etc/hostname"}},
        }
        with patch(
            "api.routers.commands.CommandService.submit_command_job", new=AsyncMock()
        ) as submit:
            r = _call(client, "post", "/api/commands/jobs", body, token)
        assert r.status_code == 403 and "disabled" in r.json()["detail"]
        submit.assert_not_called()

    def test_admin_can_poll_job_status(self, client):
        from api.auth import create_access_token

        token = create_access_token("user:admin", "admin", "admin")
        status = {
            "job_id": "command:abc",
            "status": "completed",
            "result": {"ok": True},
        }
        with patch(
            "api.routers.commands.CommandService.get_command_status",
            new=AsyncMock(return_value=status),
        ):
            r = _call(client, "get", "/api/commands/jobs/command:abc", None, token)
        assert r.status_code == 200 and r.json()["status"] == "completed"

    def test_admin_list_exposes_no_payload(self, client):
        from api.auth import create_access_token

        token = create_access_token("user:admin", "admin", "admin")
        r = _call(client, "get", "/api/commands/jobs", None, token)
        assert r.status_code == 200
        assert all("args" not in j and "result" not in j for j in r.json())


# --- Worker-side guards --------------------------------------------------------


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    up = tmp_path / "uploads"
    up.mkdir()
    monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(up))
    outside = tmp_path / "outside"
    outside.mkdir()
    canary = outside / "canary.txt"
    canary.write_text("CANARY-do-not-read")
    return up, canary


class TestUploadPaths:
    def test_inside_accepted(self, uploads):
        up, _ = uploads
        f = up / "doc.pdf"
        f.write_bytes(b"%PDF")
        assert guard.resolve_upload_path(str(f)) == str(f.resolve())

    @pytest.mark.parametrize(
        "make", ["outside", "traversal", "symlink", "missing", "nul", "root"]
    )
    def test_rejected(self, uploads, make):
        up, canary = uploads
        if make == "outside":
            p = str(canary)
        elif make == "traversal":
            p = str(up / ".." / "outside" / "canary.txt")
        elif make == "symlink":
            link = up / "innocent.pdf"
            link.symlink_to(canary)
            p = str(link)
        elif make == "missing":
            p = str(up / "nope.pdf")
        elif make == "nul":
            p = str(up / "a\x00.pdf")
        else:
            p = str(up)
        with pytest.raises(guard.UnsafeJobInput):
            guard.resolve_upload_path(p)

    def test_delete_outside_refused(self, uploads):
        _, canary = uploads
        assert guard.safe_delete_upload(str(canary)) is False
        assert canary.exists()

    def test_delete_symlink_removes_link_not_target(self, uploads):
        up, canary = uploads
        link = up / "trap.pdf"
        link.symlink_to(canary)
        assert guard.safe_delete_upload(str(link)) is True
        assert not link.exists() and canary.exists()

    def test_delete_inside_ok(self, uploads):
        up, _ = uploads
        f = up / "doc.pdf"
        f.write_bytes(b"%PDF")
        assert guard.safe_delete_upload(str(f)) is True and not f.exists()

    def test_record_ids(self):
        assert guard.require_record_id("source:abc", "source") == "source:abc"
        for bad in ("notebook:abc", "source:", "abc", "source:a b", "source:x;DELETE"):
            with pytest.raises(guard.UnsafeJobInput):
                guard.require_record_id(bad, "source")


class _Redirect(BaseHTTPRequestHandler):
    target = "http://169.254.169.254/latest/meta-data/"

    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(302)
        self.send_header("Location", self.target if self.path == "/evil" else "/ok")
        self.end_headers()


@pytest.fixture
def stub_server(monkeypatch):
    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.delenv(var, raising=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Redirect)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


class TestUrls:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://x",
            "http://169.254.169.254/latest/meta-data/",
            "http://[fd00:ec2::254]/",
            "ftp://example.org/a.pdf",
        ],
    )
    async def test_disallowed_urls(self, url):
        with pytest.raises(guard.UnsafeJobInput):
            await guard.validate_source_url(url)

    @pytest.mark.asyncio
    async def test_redirect_to_metadata_blocked(self, stub_server):
        with pytest.raises(guard.UnsafeJobInput, match="Redirect"):
            await guard.validate_source_url(f"{stub_server}/evil")

    @pytest.mark.asyncio
    async def test_allowed_redirect_passes(self, stub_server):
        await guard.validate_source_url(f"{stub_server}/fine")


class TestContentProcessGuards:
    @pytest.fixture
    def graph(self, monkeypatch):
        from open_notebook.graphs import source as source_graph

        class S:
            youtube_preferred_languages = None
            default_content_processing_engine_url = None
            default_content_processing_engine_doc = "simple"
            docling_ocr = True
            docling_formulas = False
            docling_vision = False

        async def gi():
            return S()

        monkeypatch.setattr(source_graph.ContentSettings, "get_instance", gi)
        monkeypatch.setattr(
            source_graph.ContentSettings, "clear_instance", classmethod(lambda c: None)
        )

        class MM:
            async def get_defaults(self):
                return SimpleNamespace(default_speech_to_text_model=None)

        monkeypatch.setattr(source_graph, "ModelManager", MM)
        extract = AsyncMock(return_value=SimpleNamespace(title="t", content="text"))
        monkeypatch.setattr(source_graph, "extract_content", extract)
        return source_graph, extract

    @pytest.mark.asyncio
    async def test_file_outside_uploads_never_read(self, uploads, graph):
        source_graph, extract = graph
        _, canary = uploads
        with pytest.raises(guard.UnsafeJobInput):
            await source_graph.content_process(
                {"content_state": {"file_path": str(canary), "delete_source": True}}
            )
        extract.assert_not_called()
        assert canary.exists()

    @pytest.mark.asyncio
    async def test_unsafe_url_never_fetched(self, graph):
        source_graph, extract = graph
        with pytest.raises(guard.UnsafeJobInput):
            await source_graph.content_process(
                {"content_state": {"url": "http://169.254.169.254/latest/"}}
            )
        extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_upload_processed_and_deleted(self, uploads, graph):
        source_graph, extract = graph
        up, _ = uploads
        f = up / "doc.txt"
        f.write_text("hello")
        out = await source_graph.content_process(
            {"content_state": {"file_path": str(f), "delete_source": True}}
        )
        assert out["extraction"].content == "text"
        extract.assert_awaited_once()
        assert not f.exists()


class TestCommandInputValidation:
    def _input(self, **kw):
        from commands.source_commands import SourceProcessingInput

        base = dict(
            source_id="source:1",
            content_state={"content": "x"},
            notebook_ids=["notebook:1"],
            transformations=[],
            embed=False,
        )
        base.update(kw)
        return SourceProcessingInput(**base)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kw",
        [
            {"source_id": "notebook:1"},
            {"notebook_ids": ["source:9"]},
            {"transformations": ["source:9"]},
            {"content_state": {"content": "x", "document_engine": "docling"}},
        ],
    )
    async def test_malformed_input_rejected_before_any_work(self, kw):
        from commands import source_commands

        with (
            patch.object(source_commands.Source, "get", new=AsyncMock()) as get,
            patch.object(source_commands, "source_graph") as g,
        ):
            with pytest.raises(ValueError):
                await source_commands.process_source_command(self._input(**kw))
        get.assert_not_called()
        g.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["file_path", "url"])
    async def test_content_must_match_source_asset(self, uploads, field):
        from commands import source_commands

        up, _ = uploads
        mine = up / "mine.pdf"
        other = up / "other.pdf"
        mine.write_bytes(b"%PDF")
        other.write_bytes(b"%PDF")
        asset = SimpleNamespace(file_path=str(mine), url="https://example.org/mine.pdf")
        src = SimpleNamespace(
            id="source:1", asset=asset, command=None, save=AsyncMock()
        )
        state = (
            {"file_path": str(other)}
            if field == "file_path"
            else {"url": "https://example.org/other.pdf"}
        )
        with (
            patch.object(
                source_commands.Source, "get", new=AsyncMock(return_value=src)
            ),
            patch.object(source_commands, "source_graph") as g,
        ):
            with pytest.raises(ValueError, match="does not match"):
                await source_commands.process_source_command(
                    self._input(content_state=state)
                )
        g.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_matching_asset_reaches_the_graph(self, uploads):
        from commands import source_commands

        up, _ = uploads
        mine = up / "mine.pdf"
        mine.write_bytes(b"%PDF")
        src = SimpleNamespace(
            id="source:1",
            asset=SimpleNamespace(file_path=str(mine), url=None),
            command=None,
            save=AsyncMock(),
        )
        with (
            patch.object(
                source_commands.Source, "get", new=AsyncMock(return_value=src)
            ),
            patch.object(source_commands, "source_graph") as g,
        ):
            g.ainvoke = AsyncMock(side_effect=RuntimeError("stop after validation"))
            with patch.object(
                source_commands, "_source_is_gone", new=AsyncMock(return_value=False)
            ):
                with pytest.raises(RuntimeError, match="stop after validation"):
                    await source_commands.process_source_command(
                        self._input(content_state={"file_path": str(mine)})
                    )
        g.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_commands_validate_ids(self):
        from commands import embedding_commands, source_commands

        with pytest.raises(ValueError):
            await source_commands.run_transformation_command(
                source_commands.RunTransformationInput(
                    source_id="notebook:1", transformation_id="transformation:1"
                )
            )
        with pytest.raises(ValueError):
            await embedding_commands.embed_source_command(
                embedding_commands.EmbedSourceInput(source_id="note:1")
            )
        with pytest.raises(ValueError):
            await embedding_commands.embed_note_command(
                embedding_commands.EmbedNoteInput(note_id="source:1")
            )

    @pytest.mark.asyncio
    async def test_ocr_command_nonce_still_required(self, tmp_path, monkeypatch):
        from commands import ocr_commands

        monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
        out = await ocr_commands.ocr_install_model_command(
            ocr_commands.OcrJobInput(engine_id="easyocr", nonce="guess")
        )
        assert out.success is False and out.error_message == "Unauthorised job"
