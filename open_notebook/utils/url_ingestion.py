"""Deployment switch for adding sources from a URL (docs/security, D-29).

The worker's URL check is a pre-check: content-core / Docling fetch the URL
again and follow redirects themselves, so a server that answers the second
request differently, or DNS rebinding, can still reach an internal address
(docs/security/BACKGROUND_JOB_SECURITY.md, residual risk). The mitigation
chosen for the internal bank deployment is to switch the feature off.

``OPEN_NOTEBOOK_ENABLE_URL_INGESTION``

* unset, empty or anything that is not an explicit "true" -> DISABLED. A missing
  or mistyped value never turns the feature on.
* ``true`` / ``1`` / ``yes`` / ``on`` -> enabled, with the existing URL policy
  (``validate_url`` + redirect pre-check). The residual SSRF risk is then back.

It is deployment configuration read by the backend on every call: there is no
API to change it and no role (admin included) is exempt. Already extracted
content of older URL sources stays readable; nothing is deleted.
"""

from __future__ import annotations

import os

ENV_VAR = "OPEN_NOTEBOOK_ENABLE_URL_INGESTION"
_TRUE = ("1", "true", "yes", "on")

DISABLED_MESSAGE = (
    "Adding or re-processing sources from a URL is disabled on this deployment "
    f"({ENV_VAR} is not enabled). Upload the document as a file or paste its text "
    "instead."
)


class UrlIngestionDisabled(ValueError):
    """Permanent refusal (ValueError => a background job is not retried)."""


def url_ingestion_enabled() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in _TRUE


def assert_url_ingestion_enabled() -> None:
    """Raise before ANY network activity when URL ingestion is switched off."""
    if not url_ingestion_enabled():
        raise UrlIngestionDisabled(DISABLED_MESSAGE)
