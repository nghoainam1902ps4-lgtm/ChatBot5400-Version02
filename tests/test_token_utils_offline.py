"""Token counting offline (findings F-22, R2-10; Phase 12D3, tightened in 12D5).

tiktoken downloads its encoding file with no timeout; behind a firewall that
drops packets that hangs. Phase 12D5: every token count goes through ONE
guarded loader (``token_utils.get_encoding``). Offline (``OCR_OFFLINE=true``) the
encoding comes ONLY from the cache file, checked by SHA-256; missing or
different -> ``TokenizerUnavailableError`` at once (no download, no estimate, no
chunk of unknown size). Online the v1.2.0 path stays unchanged, including its
``words x 1.3`` estimate when tiktoken fails (now logged once, not per call).

The last part runs against the REAL o200k_base encoding when a verified cache is
available (``CB5400_TIKTOKEN_CACHE_DIR``, or the app's own cache directory); it
is skipped elsewhere with the reason.
"""

import hashlib
import inspect
import os
import time
from pathlib import Path

import pytest

from open_notebook.utils import token_utils


@pytest.fixture(autouse=True)
def _fresh_state():
    token_utils._verified.clear()
    token_utils._warned["fallback"] = False
    yield
    token_utils._verified.clear()
    token_utils._warned["fallback"] = False


def _cache_name():
    return hashlib.sha1(token_utils.TIKTOKEN_BLOB_URL.encode()).hexdigest()  # noqa: S324


def test_cache_file_name_is_tiktokens_own_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    assert token_utils.tiktoken_cache_file() == str(tmp_path / _cache_name())
    import tiktoken_ext.openai_public as public

    source = inspect.getsource(public)
    assert token_utils.TIKTOKEN_BLOB_URL in source
    assert token_utils.TIKTOKEN_BLOB_SHA256 in source


def _forbid_tiktoken(monkeypatch):
    import tiktoken

    def forbidden(name):
        raise AssertionError("tiktoken.get_encoding must not be called offline")

    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)


def test_offline_without_cache_fails_clearly_and_never_calls_tiktoken(
    monkeypatch, tmp_path
):
    """was: test_offline_without_cache_never_calls_tiktoken, which accepted the
    words x 1.3 estimate (R2-10: a 160 000-character run = 1 token = 1 chunk)."""
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    _forbid_tiktoken(monkeypatch)
    started = time.perf_counter()
    with pytest.raises(token_utils.TokenizerUnavailableError) as err:
        token_utils.token_count("Điều 1. Văn bản kiểm tra.")
    assert time.perf_counter() - started < 1  # no download, no hang
    message = str(err.value)
    assert "not cached" in message and "OCR_OFFLINE" in message
    assert token_utils.TIKTOKEN_BLOB_SHA256 in message  # how to fix it


def test_offline_with_a_wrong_cache_file_fails_clearly(monkeypatch, tmp_path):
    """A truncated / replaced cache file would make tiktoken re-download (and
    hang): its SHA-256 is checked first."""
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    (tmp_path / _cache_name()).write_bytes(b"not the encoding")
    _forbid_tiktoken(monkeypatch)
    with pytest.raises(token_utils.TokenizerUnavailableError, match="SHA-256"):
        token_utils.token_count("abc")


def test_offline_failure_is_a_configuration_and_a_value_error():
    from open_notebook.exceptions import ConfigurationError

    assert issubclass(token_utils.TokenizerUnavailableError, ConfigurationError)
    assert issubclass(token_utils.TokenizerUnavailableError, ValueError)


def test_offline_with_the_verified_cache_uses_tiktoken_once_verified(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    blob = b"stand-in encoding file"
    (tmp_path / _cache_name()).write_bytes(blob)
    monkeypatch.setattr(
        token_utils, "TIKTOKEN_BLOB_SHA256", hashlib.sha256(blob).hexdigest()
    )
    import tiktoken

    called = []

    class Enc:
        def encode(self, s, disallowed_special=()):
            return [1, 2, 3]

    monkeypatch.setattr(
        tiktoken, "get_encoding", lambda name: called.append(name) or Enc()
    )
    reads = []
    real_open = open

    def counting_open(path, *a, **kw):
        if str(path).endswith(_cache_name()):
            reads.append(path)
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", counting_open)
    assert token_utils.token_count("abc") == 3
    assert token_utils.token_count("abc") == 3
    assert called == ["o200k_base", "o200k_base"]
    assert len(reads) == 1  # hashed once per (size, mtime), not per call


def test_online_behaviour_is_unchanged(monkeypatch, tmp_path):
    """Without OCR_OFFLINE the code path is the one of v1.2.0."""
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OCR_OFFLINE", raising=False)
    import tiktoken

    called = []

    class Enc:
        def encode(self, s, disallowed_special=()):
            return [1]

    monkeypatch.setattr(
        tiktoken, "get_encoding", lambda name: called.append(name) or Enc()
    )
    assert token_utils.token_count("abc") == 1 and called == ["o200k_base"]


def test_online_failure_keeps_the_v1_2_0_estimate_logged_once(monkeypatch, tmp_path):
    """Online (no OCR_OFFLINE) a failed download still gives the v1.2.0 estimate:
    Standard behaviour is kept. Its under-count is why the offline path refuses
    to estimate at all (test above)."""
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OCR_OFFLINE", raising=False)
    import tiktoken

    def offline(name):
        raise OSError("download failed")

    monkeypatch.setattr(tiktoken, "get_encoding", offline)
    text = "Lãi suất cho vay ngắn hạn tối đa 4,5%/năm."
    assert token_utils.token_count(text) == int(len(text.split()) * 1.3)
    from loguru import logger

    seen = []
    handler = logger.add(lambda m: seen.append(m), level="WARNING")
    try:
        for _ in range(50):
            token_utils.token_count(text)
    finally:
        logger.remove(handler)
    assert seen == []  # already warned once in this process (above)


def test_chunking_offline_without_cache_raises_and_makes_no_chunk(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    _forbid_tiktoken(monkeypatch)
    from open_notebook.utils.chunking import chunk_text

    with pytest.raises(token_utils.TokenizerUnavailableError):
        chunk_text("A1B2C3D4" * 20000)


def test_every_code_path_uses_the_one_guarded_loader():
    """R2-10: no module of the application loads the encoding on its own."""
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("open_notebook", "api", "commands"):
        for path in (root / folder).rglob("*.py"):
            if path.name == "token_utils.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "tiktoken.get_encoding" in text or "encoding_for_model" in text:
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
    from open_notebook.utils import context_builder

    assert "get_encoding()" in inspect.getsource(context_builder)


def test_context_builder_fallback_is_token_counts_estimate(monkeypatch):
    from open_notebook.utils import context_builder

    rendered = "x " * 1000
    assert context_builder.fallback_token_count(rendered) == 1300
    assert context_builder._rendered_source_context_tokens(
        {"id": "source:1", "title": "t", "full_text": rendered}, [], None
    ) == token_utils.fallback_token_count(
        context_builder.format_source_context(
            {
                "sources": [{"id": "source:1", "title": "t", "full_text": rendered}],
                "insights": [],
            }
        )
    )


# --------------------------------------------------------------------------- #
# The REAL encoding (needs a cache verified by SHA-256)
# --------------------------------------------------------------------------- #


def _real_cache_dir():
    for candidate in (
        os.environ.get("CB5400_TIKTOKEN_CACHE_DIR", ""),
        os.environ.get("TIKTOKEN_CACHE_DIR", ""),
        token_utils.TIKTOKEN_CACHE_DIR,
    ):
        if not candidate:
            continue
        path = Path(candidate) / _cache_name()
        if path.is_file():
            if (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == token_utils.TIKTOKEN_BLOB_SHA256
            ):
                return candidate
    return None


REAL = _real_cache_dir()
needs_real = pytest.mark.skipif(
    REAL is None,
    reason="no verified o200k_base cache here (set CB5400_TIKTOKEN_CACHE_DIR to a "
    "directory holding the file with SHA-256 "
    f"{token_utils.TIKTOKEN_BLOB_SHA256}); runs on the build machine / Windows Local",
)

CASES = {
    "160 000 characters without whitespace": "A1B2C3D4" * 20000,
    "Vietnamese legal text": (
        "Điều 5. Lãi suất cho vay. 1. Ngân hàng và khách hàng thỏa thuận về lãi suất "
        "cho vay theo cung cầu vốn thị trường, nhu cầu vay vốn và mức độ tín nhiệm của "
        "khách hàng, trừ trường hợp quy định tại khoản 2 Điều này. "
    )
    * 400,
    "a table of numbers": "\n".join(
        f"| {i} | Dư nợ nhóm {i % 5 + 1} | {i * 1234567:,} | {i % 97},{i % 10}% |"
        for i in range(3000)
    ),
    "URLs and e-mail addresses": " ".join(
        f"https://agribank.com.vn/van-ban/{i}/quy_dinh_{i}.pdf?ma=QD{i}&nam=2024 "
        f"ho_tro_{i}@agribank.com.vn"
        for i in range(2000)
    ),
    "business codes": " ".join(
        f"TK_VND_{i:06d}/QĐ-NHNo-KHCN-{i % 13}" for i in range(6000)
    ),
}


@needs_real
@pytest.mark.parametrize("case", sorted(CASES))
def test_real_encoding_offline_chunks_never_exceed_the_limit(monkeypatch, case):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", REAL)
    monkeypatch.setenv("OCR_OFFLINE", "true")
    from open_notebook.utils import chunking

    text = CASES[case]
    enc = token_utils.get_encoding()
    total = len(enc.encode(text, disallowed_special=()))
    assert token_utils.token_count(text) == total
    chunks = chunking.chunk_text(text)
    assert len(chunks) > 1
    worst = max(token_utils.token_count(c) for c in chunks)
    assert worst <= chunking.CHUNK_SIZE, (worst, chunking.CHUNK_SIZE)


@needs_real
def test_real_encoding_check_command_passes_offline(monkeypatch, capsys):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", REAL)
    monkeypatch.setenv("OCR_OFFLINE", "true")
    assert token_utils.main(["--check"]) == 0
    assert '"result": "PASS"' in capsys.readouterr().out


def test_check_command_fails_offline_without_cache(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    _forbid_tiktoken(monkeypatch)
    assert token_utils.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert '"result": "FAIL"' in out and "TokenizerUnavailableError" in out
