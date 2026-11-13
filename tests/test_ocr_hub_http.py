"""Bounded HF Hub timeouts (open_notebook/ocr/hub_http.py, DECISIONS D-24).

Phase 8B regression: after the server lost its Internet link, the worker's
first Docling job hung ~16 minutes on ``snapshot_download``'s untimed
``repo_info`` request over a dead keep-alive connection. The test uses a REAL
socket that accepts and never answers (a black-holed link) and a real local
Hub cache — no mocks of the Hub client.
"""

import socket
import threading

import pytest

pytest.importorskip("huggingface_hub")

from huggingface_hub import configure_http_backend, snapshot_download  # noqa: E402
from huggingface_hub.utils import _http as hub_http  # noqa: E402

from open_notebook.ocr import hub_http as ours  # noqa: E402

REPO = "docling-project/fake-layout"
SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def blackhole():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    conns = []
    stop = threading.Event()

    def accept():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conns.append(srv.accept()[0])  # accept, never reply
            except OSError:
                pass

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}"
    stop.set()
    t.join(2)
    for c in conns:
        c.close()
    srv.close()


@pytest.fixture
def cached_repo(tmp_path):
    root = tmp_path / "hub" / f"models--{REPO.replace('/', '--')}"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text(SHA)
    snap = root / "snapshots" / SHA
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    return tmp_path / "hub", snap


@pytest.fixture
def restore_backend():
    before = hub_http._GLOBAL_BACKEND_FACTORY
    yield
    configure_http_backend(backend_factory=before)


def _download(endpoint, cache_dir, box):
    try:
        box["path"] = snapshot_download(REPO, cache_dir=cache_dir, endpoint=endpoint)
    except Exception as e:  # pragma: no cover - reported by the assertion
        box["error"] = e


def test_dead_link_falls_back_to_cache_within_timeout(
    blackhole, cached_repo, restore_backend, monkeypatch
):
    from huggingface_hub import constants

    if constants.HF_HUB_OFFLINE:
        pytest.skip("HF_HUB_OFFLINE is set: the Hub is never contacted")
    # Independent of the harness proxy: the black hole must be reached directly
    # (a proxy would turn it into ProxyError, which the Hub re-raises).
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("OCR_HF_HUB_TIMEOUT", "1")
    cache_dir, snap = cached_repo
    assert ours.bound_hub_timeouts() is True
    box: dict = {}
    t = threading.Thread(
        target=_download, args=(blackhole, cache_dir, box), daemon=True
    )
    t.start()
    t.join(30)
    assert not t.is_alive(), "Hub request hung on a black-holed link"
    assert "error" not in box, box.get("error")
    assert box["path"] == str(snap)


def test_install_is_idempotent_and_keeps_explicit_timeouts(
    restore_backend, monkeypatch
):
    assert ours.bound_hub_timeouts() is True
    first = hub_http._GLOBAL_BACKEND_FACTORY
    assert ours.bound_hub_timeouts() is True
    assert hub_http._GLOBAL_BACKEND_FACTORY is first  # not wrapped twice

    seen = []
    session = first()
    inner = session.request

    import requests

    def fake_send(self, request, **kw):
        seen.append(kw.get("timeout"))
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"{}"
        resp.request = request
        resp.url = request.url
        return resp

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)
    inner("GET", "http://127.0.0.1:9/x")
    inner("GET", "http://127.0.0.1:9/x", timeout=123)
    assert seen == [ours.hub_timeout(), 123]


@pytest.mark.parametrize("raw,expected", [("5", 5.0), ("0", 20.0), ("x", 20.0)])
def test_timeout_env(monkeypatch, raw, expected):
    monkeypatch.setenv("OCR_HF_HUB_TIMEOUT", raw)
    assert ours.hub_timeout() == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("nan", 20.0),
        ("inf", 20.0),
        ("-inf", 20.0),
        ("1e400", 20.0),  # parses to inf
        ("-3", 20.0),
        ("", 20.0),
        ("0.5", 0.5),
        ("300", 300.0),
        ("100000", 300.0),  # capped: an unbounded wait is the bug D-24 fixed
    ],
)
def test_timeout_env_rejects_non_finite_and_caps(monkeypatch, raw, expected):
    """Phase 9B: the value always ends up a finite, positive, bounded number."""
    monkeypatch.setenv("OCR_HF_HUB_TIMEOUT", raw)
    value = ours.hub_timeout()
    assert value == expected and 0 < value <= ours.MAX_TIMEOUT
