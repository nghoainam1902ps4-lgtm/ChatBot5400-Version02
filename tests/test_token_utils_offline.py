"""Token counting on an air-gapped deployment (Phase 12D3, finding F-22).

tiktoken downloads its encoding file with no timeout; behind a firewall that
drops packets the call hangs and the word-count fallback never runs. With
OCR_OFFLINE=true the download is never attempted.
"""

import hashlib

from open_notebook.utils import token_utils


def test_cache_file_name_is_tiktokens_own_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    key = hashlib.sha1(token_utils.TIKTOKEN_BLOB_URL.encode()).hexdigest()  # noqa: S324
    assert token_utils.tiktoken_cache_file() == str(tmp_path / key)
    import inspect

    import tiktoken_ext.openai_public as public

    source = inspect.getsource(public.o200k_base)
    assert token_utils.TIKTOKEN_BLOB_URL in source
    assert token_utils.TIKTOKEN_BLOB_SHA256 in source


def test_offline_without_cache_never_calls_tiktoken(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))  # empty cache
    monkeypatch.setenv("OCR_OFFLINE", "true")
    import tiktoken

    def forbidden(name):
        raise AssertionError(
            "tiktoken.get_encoding must not be called offline without a cache"
        )

    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)
    text = "Điều 5. Lãi suất cho vay tối đa 7,5%/năm"
    assert token_utils.token_count(text) == int(len(text.split()) * 1.3)


def test_offline_with_cache_uses_tiktoken(monkeypatch, tmp_path):
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_OFFLINE", "true")
    (
        tmp_path / hashlib.sha1(token_utils.TIKTOKEN_BLOB_URL.encode()).hexdigest()
    ).write_bytes(b"x")  # noqa: S324
    import tiktoken

    called = []

    class Enc:
        def encode(self, s, disallowed_special=()):
            return [1, 2, 3]

    monkeypatch.setattr(
        tiktoken, "get_encoding", lambda name: called.append(name) or Enc()
    )
    assert token_utils.token_count("abc") == 3 and called == ["o200k_base"]


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
