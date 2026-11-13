"""Bounded network timeouts for the Hugging Face Hub client (DECISIONS D-24).

Docling resolves Layout Heron / TableFormer with ``snapshot_download``, whose
``api.repo_info()`` call passes NO timeout (huggingface_hub 0.36). When a
server loses its Internet link while the worker still holds a keep-alive
connection to huggingface.co from the online phase, that request waits for TCP
to give up (``tcp_retries2`` ≈ 15 minutes) before the Hub client falls back to
the local cache: the first document after going offline hangs ~16 minutes
(found in Phase 8B, Docker acceptance step 3).

Every Hub request that does not choose its own timeout gets a bounded one, so
the client raises ``requests.Timeout`` — which it already treats as "offline,
use the cache" — within seconds. Requests that pass an explicit timeout (file
downloads during online preparation) are untouched.
"""

from __future__ import annotations

import math
import os
from typing import Any

DEFAULT_TIMEOUT = 20.0
# An unbounded value would bring the ~15 minute hang back, and ``inf`` is not a
# timeout the socket layer accepts (every Hub request would fail).
MAX_TIMEOUT = 300.0


def hub_timeout() -> float:
    try:
        value = float(os.environ.get("OCR_HF_HUB_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT
    if not math.isfinite(value) or value <= 0:  # nan, inf, zero, negative
        return DEFAULT_TIMEOUT
    return min(value, MAX_TIMEOUT)


def bound_hub_timeouts() -> bool:
    """Install the bounded-timeout session factory once (idempotent).

    Returns True when the factory is installed (now or before), False when
    huggingface_hub is not available (Docling not installed).
    """
    try:
        return _install()
    except Exception as e:  # a hub version that moved these internals
        # Never fail a document over this: without the bound, the only loss is
        # the slow fallback to the local cache on a dead link (D-24).
        from loguru import logger

        logger.warning(f"Hugging Face Hub timeout bound not installed: {e}")
        return False


def _install() -> bool:
    try:
        from huggingface_hub import configure_http_backend
        from huggingface_hub.utils import _http as hub_http
    except ImportError:
        return False
    current = getattr(hub_http, "_GLOBAL_BACKEND_FACTORY", None)
    if getattr(current, "_ocr_bounded_timeout", False):
        return True
    base = current or hub_http._default_backend_factory

    def factory() -> Any:
        session = base()
        send = session.request

        def request(method: Any, url: Any, *args: Any, **kwargs: Any) -> Any:
            # Session.request(method, url, params, data, headers, cookies,
            # files, auth, timeout, ...): timeout is args[6] if positional.
            if len(args) <= 6 and kwargs.get("timeout") is None:
                kwargs["timeout"] = hub_timeout()
            return send(method, url, *args, **kwargs)

        session.request = request  # type: ignore[method-assign]
        return session

    factory._ocr_bounded_timeout = True  # type: ignore[attr-defined]
    configure_http_backend(backend_factory=factory)
    return True
