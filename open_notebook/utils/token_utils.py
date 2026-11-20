"""
Token utilities for Open Notebook.
Handles token counting and cost calculations for language models.

Phase 12D5 (findings F-22, R2-10): every token count of the application goes
through ONE guarded loader, :func:`get_encoding`:

* ``OCR_OFFLINE=true`` (air-gapped deployment): the encoding is read ONLY from
  the cache file, whose SHA-256 must be the expected one. A missing or different
  file raises :class:`TokenizerUnavailableError` at once - tiktoken is never
  asked to download (it has no timeout and hangs behind a firewall that drops
  packets), and no estimate is used: chunking / embedding / context building
  fail clearly instead of producing chunks of unknown size.
* otherwise: v1.2.0 behaviour, unchanged - ``tiktoken.get_encoding``, which may
  download the file once, and if that fails the v1.2.0 estimate ``words x 1.3``
  (now logged once per process instead of once per call). That estimate
  UNDER-counts text without spaces, numbers and codes (measured in
  docs/review/phase12d5/token_ratio_vietnamese_fixtures.json); it is kept because
  only an online machine whose download failed reaches it - the air-gapped
  deployment runs with ``OCR_OFFLINE=true`` and the verified cache, which the
  readiness check ``python -m open_notebook.utils.token_utils --check`` proves.
"""

import hashlib
import os
import threading
from typing import Any, Optional

from open_notebook.config import TIKTOKEN_CACHE_DIR
from open_notebook.exceptions import ConfigurationError

# Set tiktoken cache directory before importing tiktoken to ensure
# tokenizer encodings are cached persistently in the data folder
os.environ["TIKTOKEN_CACHE_DIR"] = TIKTOKEN_CACHE_DIR


# The encoding ChatBot5400 counts tokens with, and where tiktoken caches it:
# the file name is the SHA-1 of the download URL (tiktoken/load.py).
TIKTOKEN_ENCODING = "o200k_base"
TIKTOKEN_BLOB_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)
TIKTOKEN_BLOB_SHA256 = (
    "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
)


class TokenizerUnavailableError(ConfigurationError, ValueError):
    """The token encoding cannot be used offline (missing or wrong cache file).

    A ConfigurationError (the API answers 422 with the message) and a
    ValueError (background jobs stop at once instead of retrying a problem that
    only the operator can fix)."""


def tiktoken_cache_file() -> str:
    """Path of the cached encoding file inside TIKTOKEN_CACHE_DIR."""
    key = hashlib.sha1(TIKTOKEN_BLOB_URL.encode()).hexdigest()  # noqa: S324 - tiktoken's own key
    return os.path.join(os.environ.get("TIKTOKEN_CACHE_DIR", TIKTOKEN_CACHE_DIR), key)


def _offline_declared() -> bool:
    return os.environ.get("OCR_OFFLINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


offline_declared = _offline_declared

# cache file -> (size, mtime_ns) whose SHA-256 was checked in this process
_verified: dict = {}
_lock = threading.Lock()
_warned = {"fallback": False}


def cache_problem() -> Optional[str]:
    """None when the cached encoding file is there and is the expected one, byte
    for byte (SHA-256); otherwise what is wrong. Never touches the network."""
    path = tiktoken_cache_file()
    try:
        st = os.stat(path)
    except OSError:
        return f"the {TIKTOKEN_ENCODING} encoding is not cached at {path}"
    key = (st.st_size, st.st_mtime_ns)
    with _lock:
        if _verified.get(path) == key:
            return None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as e:
        return f"the cached {TIKTOKEN_ENCODING} encoding {path} is unreadable ({e.strerror})"
    if digest.hexdigest() != TIKTOKEN_BLOB_SHA256:
        return (
            f"the cached file {path} is not the {TIKTOKEN_ENCODING} encoding "
            f"(SHA-256 {digest.hexdigest()[:16]}…, expected {TIKTOKEN_BLOB_SHA256[:16]}…)"
        )
    with _lock:
        _verified[path] = key
    return None


def get_encoding() -> Any:
    """THE way ChatBot5400 loads its token encoding (all code paths use it).

    Raises TokenizerUnavailableError offline when the cache is missing or not
    the expected file; ImportError / OSError when tiktoken itself fails online.
    """
    if _offline_declared():
        problem = cache_problem()
        if problem is not None:
            raise TokenizerUnavailableError(
                f"{problem}. The deployment is offline (OCR_OFFLINE=true), so the "
                "encoding is never downloaded. Fix: use an image built with the "
                "encoding baked in (TIKTOKEN_CACHE_DIR=/app/tiktoken-cache), or copy "
                f"the verified file to {tiktoken_cache_file()} "
                f"(SHA-256 {TIKTOKEN_BLOB_SHA256})."
            )
    import tiktoken

    return tiktoken.get_encoding(TIKTOKEN_ENCODING)


def fallback_token_count(text: str) -> int:
    """The v1.2.0 estimate used ONLINE when tiktoken cannot load (never offline).
    Not a bound: it under-counts runs without whitespace, numbers and codes."""
    return int(len(text.split()) * 1.3)


def token_count(input_string: str) -> int:
    """
    Count the number of tokens in the input string using the 'o200k_base' encoding.

    Args:
        input_string (str): The input string to count tokens for.

    Returns:
        int: The number of tokens in the input string.

    Raises:
        TokenizerUnavailableError: offline (OCR_OFFLINE=true) without the
            verified cache file - never an estimate in that case.
    """
    try:
        encoding = get_encoding()
        # disallowed_special=() treats sequences like "<|endoftext|>" as ordinary
        # text instead of raising ValueError. User/source content can legitimately
        # contain these substrings, and we only need a token count here.
        return len(encoding.encode(input_string, disallowed_special=()))
    except TokenizerUnavailableError:
        raise
    except (ImportError, OSError) as e:
        # Online only: tiktoken not installed or the download failed (URLError
        # and ConnectionError are OSErrors). The v1.2.0 estimate, logged once.
        if not _warned["fallback"]:
            _warned["fallback"] = True
            from loguru import logger

            logger.warning(
                "tiktoken unavailable, falling back to word-count estimation: {} "
                "(logged once; offline deployments must set OCR_OFFLINE=true and "
                "ship the verified encoding cache)",
                e,
            )
        return fallback_token_count(input_string)


def token_cost(token_count: int, cost_per_million: float = 0.150) -> float:
    """
    Calculate the cost of tokens based on the token count and cost per million tokens.

    Args:
        token_count (int): The number of tokens.
        cost_per_million (float): The cost per million tokens. Default is 0.150.

    Returns:
        float: The calculated cost for the given token count.
    """
    return cost_per_million * (token_count / 1_000_000)


def main(argv: Optional[list] = None) -> int:
    """``python -m open_notebook.utils.token_utils --check``: exit 0 only when the
    REAL encoding loads (offline: from the verified cache) and counts a known
    text; never an estimate. Used by the offline health checks and operators."""
    import argparse
    import json

    p = argparse.ArgumentParser(description=main.__doc__)
    p.add_argument("--check", action="store_true", required=True)
    p.parse_args(argv)
    report: dict = {
        "encoding": TIKTOKEN_ENCODING,
        "offline": _offline_declared(),
        "cache_file": tiktoken_cache_file(),
        "cache_problem": cache_problem(),
    }
    try:
        tokens = get_encoding().encode("Điều 1. Kiểm tra bộ đếm token.")
        report["tokens"] = len(tokens)
        ok = len(tokens) > 0
    except Exception as e:  # noqa: BLE001 - reported
        report["error"] = f"{type(e).__name__}: {e}"
        ok = False
    report["result"] = "PASS" if ok else "FAIL"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
