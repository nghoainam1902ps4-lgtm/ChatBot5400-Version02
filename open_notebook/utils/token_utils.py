"""
Token utilities for Open Notebook.
Handles token counting and cost calculations for language models.
"""

import os

from open_notebook.config import TIKTOKEN_CACHE_DIR

# Set tiktoken cache directory before importing tiktoken to ensure
# tokenizer encodings are cached persistently in the data folder
os.environ["TIKTOKEN_CACHE_DIR"] = TIKTOKEN_CACHE_DIR


# The encoding ChatBot5400 counts tokens with, and where tiktoken caches it:
# the file name is the SHA-1 of the download URL (tiktoken/load.py).
TIKTOKEN_ENCODING = "o200k_base"
TIKTOKEN_BLOB_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)
TIKTOKEN_BLOB_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"


def tiktoken_cache_file() -> str:
    """Path of the cached encoding file inside TIKTOKEN_CACHE_DIR."""
    import hashlib

    key = hashlib.sha1(TIKTOKEN_BLOB_URL.encode()).hexdigest()  # noqa: S324 - tiktoken's own key
    return os.path.join(os.environ.get("TIKTOKEN_CACHE_DIR", TIKTOKEN_CACHE_DIR), key)


def _offline_declared() -> bool:
    return os.environ.get("OCR_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def token_count(input_string: str) -> int:
    """
    Count the number of tokens in the input string using the 'o200k_base' encoding.

    Args:
        input_string (str): The input string to count tokens for.

    Returns:
        int: The number of tokens in the input string.
    """
    try:
        if _offline_declared() and not os.path.isfile(tiktoken_cache_file()):
            # Air-gapped deployment (OCR_OFFLINE=true) without the cached
            # encoding: tiktoken would try to download it with no timeout and
            # hang behind a firewall that drops packets. Never touch the
            # network; use the word-count estimate below (Phase 12D3, F-22).
            raise OSError(
                f"tiktoken encoding {TIKTOKEN_ENCODING} is not cached at "
                f"{tiktoken_cache_file()} and the deployment is offline"
            )
        import tiktoken

        encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING)
        # disallowed_special=() treats sequences like "<|endoftext|>" as ordinary
        # text instead of raising ValueError. User/source content can legitimately
        # contain these substrings, and we only need a token count here.
        tokens = encoding.encode(input_string, disallowed_special=())
        return len(tokens)
    except (ImportError, OSError) as e:
        # Fallback: handles ImportError (tiktoken not installed) AND network/OS
        # errors such as urllib.error.URLError or ConnectionError raised in
        # offline environments when the encoding file cannot be downloaded.
        from loguru import logger

        logger.warning(
            "tiktoken unavailable, falling back to word-count estimation: {}", e
        )
        return int(len(input_string.split()) * 1.3)


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
