"""Defence in depth for background-job inputs (docs/security/BACKGROUND_JOB_SECURITY.md).

Background commands (``process_source`` & co.) must not trust their input even
when the API already validated it: the input travels through the job queue,
and other code paths (retries, sync execution, future callers) reach the same
worker code. These checks apply to every caller, admins included.

* File paths: canonical path (symlinks resolved) must be a regular file strictly
  inside UPLOADS_FOLDER; re-checked immediately before deletion.
* URLs: the existing ``validate_url`` policy (http/https only, no link-local /
  cloud-metadata addresses; private hosts allowed for self-hosting), applied in
  the worker to the URL and to every redirect hop.
* Record ids: must belong to the expected table.
"""

from __future__ import annotations

import os
from urllib.parse import urljoin

from loguru import logger

from open_notebook import config

MAX_REDIRECTS = 5


class UnsafeJobInput(ValueError):
    """Permanent rejection (ValueError => the job is not retried)."""


def _uploads_root() -> str:
    # Read at call time so tests / deployments with a different data dir work.
    return os.path.realpath(config.UPLOADS_FOLDER)


def resolve_upload_path(path: str) -> str:
    """Canonical path of an uploaded file, or UnsafeJobInput."""
    if not path or "\x00" in str(path):
        raise UnsafeJobInput("Invalid file path.")
    root = _uploads_root()
    resolved = os.path.realpath(path)
    if not resolved.startswith(root + os.sep):
        logger.warning(
            f"Rejected job file path outside the uploads directory: {path!r}"
        )
        raise UnsafeJobInput("File path must be inside the uploads directory.")
    if not os.path.isfile(resolved):
        raise UnsafeJobInput("Uploaded file not found.")
    return resolved


def same_upload(path_a: str | None, path_b: str | None) -> bool:
    if not path_a or not path_b:
        return False
    return os.path.realpath(path_a) == os.path.realpath(path_b)


def safe_delete_upload(path: str) -> bool:
    """Delete an uploaded file only if it is (still) inside the uploads directory.

    Re-validates right before deleting (a symlink swapped in after processing
    cannot redirect the delete). A symlink is removed itself, never its target.
    """
    root = _uploads_root()
    parent = os.path.realpath(os.path.dirname(os.path.abspath(path)))
    if parent != root and not parent.startswith(root + os.sep):
        logger.warning(
            f"Refused to delete a file outside the uploads directory: {path!r}"
        )
        return False
    if not os.path.islink(path):
        try:
            resolve_upload_path(path)
        except UnsafeJobInput:
            logger.warning(
                f"Refused to delete {path!r}: not a file inside the uploads directory"
            )
            return False
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        logger.warning(f"File not found while trying to delete: {path}")
    except OSError as e:
        logger.warning(f"Failed to delete source file {path}: {e}")
    return False


async def validate_source_url(url: str) -> None:
    """Existing URL policy, re-applied in the worker incl. every redirect hop."""
    from open_notebook.utils.url_validation import validate_url

    try:
        await validate_url(url, "source")
    except ValueError as e:
        raise UnsafeJobInput(str(e)) from e
    # Follow redirects ourselves (no body download) and validate each target.
    try:
        import httpx

        current = url
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            for _ in range(MAX_REDIRECTS):
                async with client.stream("GET", current) as resp:
                    location = resp.headers.get("location")
                    if (
                        resp.status_code not in (301, 302, 303, 307, 308)
                        or not location
                    ):
                        return
                current = urljoin(current, location)
                try:
                    await validate_url(current, "source")
                except ValueError as e:
                    raise UnsafeJobInput(f"Redirect to a disallowed URL: {e}") from e
        raise UnsafeJobInput("Too many redirects.")
    except UnsafeJobInput:
        raise
    except Exception as e:
        # Network trouble is not a policy violation: let extraction report it.
        logger.debug(f"Redirect pre-check skipped for {url}: {e}")


def require_record_id(value: str, table: str) -> str:
    """``value`` must be a record id of ``table`` (e.g. 'source:abc')."""
    text = str(value or "")
    prefix, sep, ident = text.partition(":")
    if (
        sep != ":"
        or prefix != table
        or not ident
        or any(c in ident for c in " ;\n\r\t")
    ):
        raise UnsafeJobInput(f"Invalid {table} id.")
    return text
