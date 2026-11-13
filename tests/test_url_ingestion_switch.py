"""URL ingestion switch (OPEN_NOTEBOOK_ENABLE_URL_INGESTION, D-29).

Switched OFF (the default) no source may be created or re-processed from a URL,
by any role, through any path — and nothing touches the network. Uploads, text
sources and stored content of older URL sources keep working. Switched ON, the
existing URL policy applies unchanged.

Only mocks and local stubs: no real host is contacted.
"""

import os
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.config import UPLOADS_FOLDER
from open_notebook.domain.notebook import Source
from open_notebook.utils import url_ingestion
from open_notebook.utils.url_ingestion import ENV_VAR, UrlIngestionDisabled

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.com/article"


@pytest.fixture
def switched_off(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


@pytest.fixture
def switched_on(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "true")


@pytest.fixture
def no_network(monkeypatch):
    """Any DNS lookup or connection attempt fails the test."""

    def boom(*a, **k):
        raise AssertionError("network activity while URL ingestion is switched off")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


# --- the switch itself ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, False),  # missing configuration never enables the feature
        ("", False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("enabled", False),  # not an accepted spelling: stays off
        ("maybe", False),
        ("2", False),
        ("true", True),
        (" TRUE ", True),
        ("1", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_switch_parsing(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, raw)
    assert url_ingestion.url_ingestion_enabled() is expected
    if expected:
        url_ingestion.assert_url_ingestion_enabled()
    else:
        with pytest.raises(UrlIngestionDisabled):
            url_ingestion.assert_url_ingestion_enabled()


def test_refusal_is_permanent_for_background_jobs():
    # stop_on: [ValueError] => the worker does not retry the job.
    assert issubclass(UrlIngestionDisabled, ValueError)


def test_switch_is_only_used_by_url_ingestion_code():
    """LLM / embedding / model download / OCR install code never consults it."""
    users = set()
    for folder in ("api", "commands", "open_notebook"):
        for path in (ROOT / folder).rglob("*.py"):
            if "url_ingestion" in path.read_text(encoding="utf-8"):
                users.add(str(path.relative_to(ROOT)))
    assert users == {
        "api/models.py",  # the read-only capabilities field
        "api/routers/capabilities.py",
        "api/routers/sources.py",
        "commands/source_commands.py",
        "open_notebook/graphs/source.py",
        "open_notebook/ocr/docling_extract.py",
        "open_notebook/utils/url_ingestion.py",
    }


# --- API: creating sources -----------------------------------------------------


class TestCreateSourceApi:
    def _post(self, client, path, payload, headers=None):
        with (
            patch.object(Source, "save", new_callable=AsyncMock) as save,
            patch(
                "api.routers.sources.validate_url", new_callable=AsyncMock
            ) as validate,
            patch(
                "api.routers.sources.CommandService.submit_command_job",
                new_callable=AsyncMock,
            ) as submit,
            patch("api.routers.sources.execute_command_sync") as execute,
            patch("api.routers.sources.Notebook.get", new_callable=AsyncMock),
        ):
            if path.endswith("/json"):
                r = client.post(path, json=payload, headers=headers or {})
            else:
                r = client.post(path, data=payload, headers=headers or {})
        return r, save, validate, submit, execute

    @pytest.mark.parametrize("async_processing", ["true", "false"])
    def test_link_refused_sync_and_async(
        self, client, switched_off, no_network, async_processing
    ):
        r, save, validate, submit, execute = self._post(
            client,
            "/api/sources",
            {
                "type": "link",
                "url": URL,
                "notebooks": '["notebook:1"]',
                "async_processing": async_processing,
            },
        )
        assert r.status_code == 403
        assert ENV_VAR in r.json()["detail"]
        save.assert_not_called()  # no source record
        validate.assert_not_called()  # not even the URL pre-check
        submit.assert_not_called()  # nothing queued
        execute.assert_not_called()  # nothing run synchronously

    def test_legacy_json_endpoint_refused(self, client, switched_off, no_network):
        r, save, validate, submit, execute = self._post(
            client,
            "/api/sources/json",
            {"type": "link", "url": URL, "notebooks": ["notebook:1"]},
        )
        assert r.status_code == 403
        for mock in (save, validate, submit, execute):
            mock.assert_not_called()

    # The roles allowed to add sources (api.auth.SUBMITTER_ROLES).
    @pytest.mark.parametrize("role", ["admin", "contributor"])
    def test_no_role_is_exempt(
        self, client, switched_off, no_network, monkeypatch, role
    ):
        from api.auth import create_access_token

        monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", "test-secret-url-switch")
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)
        token = create_access_token(f"user:{role}", role, role)
        r, save, validate, submit, execute = self._post(
            client,
            "/api/sources",
            {"type": "link", "url": URL, "notebooks": '["notebook:1"]'},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403 and ENV_VAR in r.json()["detail"]
        for mock in (save, validate, submit, execute):
            mock.assert_not_called()

    def test_text_source_still_accepted(self, client, switched_off):
        saved = []

        async def capture(self_source):
            saved.append(self_source)
            self_source.id = "source:fake"
            self_source.command = None

        with (
            patch.object(Source, "save", autospec=True, side_effect=capture),
            patch(
                "api.routers.sources.CommandService.submit_command_job",
                new_callable=AsyncMock,
                return_value="command:1",
            ) as submit,
            patch("api.routers.sources.Source.add_to_notebook", new_callable=AsyncMock),
            patch("api.routers.sources.Notebook.get", new_callable=AsyncMock),
        ):
            r = client.post(
                "/api/sources",
                data={
                    "type": "text",
                    "content": "Nội dung nhập tay",
                    "notebooks": '["notebook:1"]',
                    "async_processing": "true",
                },
            )
        assert r.status_code == 200, r.text
        submit.assert_awaited_once()
        assert "url" not in submit.await_args_list[0].args[2]["content_state"]

    def test_file_upload_still_accepted(self, client, switched_off):
        target = os.path.join(os.path.abspath(UPLOADS_FOLDER), "switch-doc.pdf")
        saved = []

        async def capture(self_source):
            saved.append(self_source)
            self_source.id = "source:fake"
            self_source.command = None

        with (
            patch.object(Source, "save", autospec=True, side_effect=capture),
            patch(
                "api.routers.sources.save_uploaded_file",
                new_callable=AsyncMock,
                return_value=target,
            ),
            patch(
                "api.routers.sources.CommandService.submit_command_job",
                new_callable=AsyncMock,
                return_value="command:1",
            ) as submit,
            patch("api.routers.sources.Source.add_to_notebook", new_callable=AsyncMock),
            patch("api.routers.sources.Notebook.get", new_callable=AsyncMock),
        ):
            r = client.post(
                "/api/sources",
                data={
                    "type": "upload",
                    "notebooks": '["notebook:1"]',
                    "async_processing": "true",
                },
                files={"file": ("switch-doc.pdf", b"%PDF-1.4", "application/pdf")},
            )
        assert r.status_code == 200, r.text
        assert saved and saved[0].asset.file_path == target
        submit.assert_awaited_once()

    def test_enabled_keeps_the_existing_url_policy(self, client, switched_on):
        # Accepted URL: the existing pre-check runs, then the job is queued.
        r, save, validate, submit, _ = self._post(
            client,
            "/api/sources",
            {
                "type": "link",
                "url": URL,
                "notebooks": '["notebook:1"]',
                "async_processing": "true",
            },
        )
        validate.assert_awaited_once_with(URL, "source")
        assert r.status_code != 403
        # Rejected URL: the policy (not the switch) answers 400.
        with (
            patch(
                "api.routers.sources.validate_url",
                new_callable=AsyncMock,
                side_effect=ValueError("blocked address"),
            ),
            patch("api.routers.sources.Notebook.get", new_callable=AsyncMock),
            patch.object(Source, "save", new_callable=AsyncMock) as save,
        ):
            r = client.post(
                "/api/sources",
                data={
                    "type": "link",
                    "url": "http://169.254.169.254/latest/",
                    "notebooks": '["notebook:1"]',
                },
            )
        save.assert_not_called()
        assert r.status_code == 400 and "blocked address" in r.json()["detail"]


# --- API: retry / re-process and reading old URL sources ------------------------


def _source(asset=None, full_text=None):
    source = MagicMock()
    source.id = "source:1"
    source.command = None
    source.title = "Old source"
    source.topics = []
    source.full_text = full_text
    source.asset = asset
    source.approval_status = "approved"
    source.submitted_by = None
    source.review_note = None
    source.save = AsyncMock()
    source.get_embedded_chunks = AsyncMock(return_value=3)
    return source


class TestRetryAndOldSources:
    def _retry(self, client, source, headers=None):
        with (
            patch(
                "api.routers.sources.Source.get",
                new_callable=AsyncMock,
                return_value=source,
            ),
            patch(
                "api.routers.sources.repo_query",
                new_callable=AsyncMock,
                return_value=["notebook:1"],
            ),
            patch(
                "api.routers.sources.CommandService.submit_command_job",
                new_callable=AsyncMock,
                return_value="command:9",
            ) as submit,
        ):
            r = client.post("/api/sources/source:1/retry", headers=headers or {})
        return r, submit

    def test_retry_of_url_source_refused(self, client, switched_off, no_network):
        source = _source(asset=MagicMock(file_path=None, url=URL), full_text="đã lưu")
        r, submit = self._retry(client, source)
        assert r.status_code == 403 and ENV_VAR in r.json()["detail"]
        submit.assert_not_called()
        source.save.assert_not_called()
        assert source.full_text == "đã lưu"  # stored content untouched

    def test_retry_refused_for_admin_too(
        self, client, switched_off, no_network, monkeypatch
    ):
        from api.auth import create_access_token

        monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", "test-secret-url-switch")
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)
        token = create_access_token("user:admin", "admin", "admin")
        source = _source(asset=MagicMock(file_path=None, url=URL))
        r, submit = self._retry(
            client, source, headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        submit.assert_not_called()

    def test_retry_of_text_source_still_works(self, client, switched_off):
        r, submit = self._retry(client, _source(asset=None, full_text="văn bản"))
        assert r.status_code == 200, r.text
        submit.assert_awaited_once()
        assert submit.await_args_list[0].args[2]["content_state"] == {
            "content": "văn bản"
        }

    def test_retry_of_url_source_when_enabled(self, client, switched_on):
        source = _source(asset=MagicMock(file_path=None, url=URL))
        r, submit = self._retry(client, source)
        assert r.status_code == 200, r.text
        assert submit.await_args_list[0].args[2]["content_state"] == {"url": URL}

    def test_old_url_source_content_is_still_readable(
        self, client, switched_off, no_network
    ):
        """Reading never re-downloads: the stored text and the URL are returned."""
        from open_notebook.domain.notebook import Asset

        source = Source(
            id="source:old",
            title="Bài viết cũ",
            topics=[],
            asset=Asset(url=URL),
            full_text="Nội dung đã trích xuất trước khi tắt URL ingestion.",
        )
        with (
            patch(
                "api.routers.sources.Source.get",
                new_callable=AsyncMock,
                return_value=source,
            ),
            patch.object(
                Source, "get_embedded_chunks", new_callable=AsyncMock, return_value=2
            ),
            patch.object(
                Source, "get_status", new_callable=AsyncMock, return_value=None
            ),
            patch(
                "api.routers.sources.repo_query",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            r = client.get("/api/sources/source:old")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["full_text"].startswith("Nội dung đã trích xuất")
        assert body["asset"]["url"] == URL


# --- worker command -------------------------------------------------------------


class TestWorkerCommand:
    def _input(self, content_state):
        from commands.source_commands import SourceProcessingInput

        return SourceProcessingInput(
            source_id="source:1",
            content_state=content_state,
            notebook_ids=["notebook:1"],
            transformations=[],
            embed=False,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "state", [{"url": URL}, {"url": URL, "content": "already extracted"}]
    )
    async def test_url_job_refused_before_any_work(
        self, switched_off, no_network, state
    ):
        """Covers jobs queued before the switch was turned off, retries and
        anything that writes a job without going through the API."""
        from commands import source_commands

        with (
            patch.object(source_commands.Source, "get", new=AsyncMock()) as get,
            patch.object(source_commands, "source_graph") as graph,
        ):
            with pytest.raises(UrlIngestionDisabled):
                await source_commands.process_source_command(self._input(state))
        get.assert_not_called()
        graph.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_text_job_reaches_the_graph(self, switched_off):
        from commands import source_commands

        src = SimpleNamespace(id="source:1", asset=None, command=None, save=AsyncMock())
        with (
            patch.object(
                source_commands.Source, "get", new=AsyncMock(return_value=src)
            ),
            patch.object(source_commands, "source_graph") as graph,
        ):
            graph.ainvoke = AsyncMock(side_effect=RuntimeError("stop after the guard"))
            with pytest.raises(Exception, match="stop after the guard"):
                await source_commands.process_source_command(
                    self._input({"content": "văn bản"})
                )
        graph.ainvoke.assert_awaited_once()


# --- graph node and OCR URL path ------------------------------------------------


@pytest.fixture
def graph(monkeypatch):
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
    validate = AsyncMock()
    monkeypatch.setattr(source_graph, "validate_source_url", validate)
    return source_graph, extract, validate


class TestGraphNode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "state", [{"url": URL}, {"url": URL, "content": "already extracted"}]
    )
    async def test_url_refused_before_validation_and_fetch(
        self, graph, switched_off, no_network, state
    ):
        source_graph, extract, validate = graph
        with pytest.raises(UrlIngestionDisabled):
            await source_graph.content_process({"content_state": state})
        validate.assert_not_called()  # no redirect pre-check request either
        extract.assert_not_called()  # content-core never called

    @pytest.mark.asyncio
    async def test_file_and_text_still_processed(
        self, graph, switched_off, tmp_path, monkeypatch
    ):
        source_graph, extract, _ = graph
        up = tmp_path / "uploads"
        up.mkdir()
        monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(up))
        doc = up / "doc.txt"
        doc.write_text("hello")
        out = await source_graph.content_process(
            {"content_state": {"file_path": str(doc), "delete_source": False}}
        )
        assert out["extraction"].content == "text"
        out = await source_graph.content_process(
            {"content_state": {"content": "văn bản nhập tay"}}
        )
        assert out["extraction"].content == "text"
        assert extract.await_count == 2

    @pytest.mark.asyncio
    async def test_enabled_runs_the_existing_url_validation(self, graph, switched_on):
        source_graph, extract, validate = graph
        monkeypatch_target = "open_notebook.graphs.source.should_use_native_ocr_for_url"
        with patch(monkeypatch_target, new=AsyncMock(return_value=False)):
            await source_graph.content_process({"content_state": {"url": URL}})
        validate.assert_awaited_once_with(URL)
        extract.assert_awaited_once()
        assert extract.await_args_list[0].kwargs["url"] == URL

    @pytest.mark.asyncio
    async def test_ocr_url_path_refused_before_any_request(
        self, switched_off, no_network
    ):
        """Both OCR-layer URL functions: the MIME probe and the download."""
        from open_notebook.ocr import docling_extract
        from open_notebook.ocr.options import OcrSettings

        ocr = OcrSettings(engine="tesseract_best")
        with (
            patch(
                "content_core.processors.url.detect_remote_mime", new=AsyncMock()
            ) as probe,
            patch(
                "content_core.extraction._download_remote_file", new=AsyncMock()
            ) as download,
            patch.object(docling_extract, "native_path_required", return_value=True),
        ):
            with pytest.raises(UrlIngestionDisabled):
                await docling_extract.should_use_native_ocr_for_url(URL, "auto", ocr)
            with pytest.raises(UrlIngestionDisabled):
                await docling_extract.extract_url_with_selected_ocr(
                    URL, MagicMock(), ocr
                )
        probe.assert_not_called()
        download.assert_not_called()


# --- what the frontend is told ---------------------------------------------------


class TestCapabilities:
    def test_reported_from_the_backend(self, client, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert client.get("/api/capabilities").json()["url_ingestion_enabled"] is False
        monkeypatch.setenv(ENV_VAR, "true")
        assert client.get("/api/capabilities").json()["url_ingestion_enabled"] is True
        monkeypatch.setenv(ENV_VAR, "definitely")
        assert client.get("/api/capabilities").json()["url_ingestion_enabled"] is False

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_cannot_be_changed_through_the_api(self, client, switched_off, method):
        r = getattr(client, method)("/api/capabilities")
        assert r.status_code == 405
        assert url_ingestion.url_ingestion_enabled() is False

    def test_settings_api_cannot_enable_it(self, switched_off):
        import api.models as models

        for name in ("SettingsUpdate", "SettingsResponse"):
            model = getattr(models, name, None)
            if model is None:
                continue
            assert not [f for f in model.model_fields if "ingestion" in f.lower()]
