"""Database isolation for the test suite (fail-closed).

The application's default database endpoint is ``ws://localhost:8000``. On a
machine that also runs a deployment that endpoint can be a live database, and a
developer ``.env`` in the project root can carry a deployment's credentials.
The test suite must therefore never derive its database from the ordinary
``SURREAL_*`` settings.

Rules implemented here (``tests/conftest.py`` applies them before any project
module is imported):

1. Every ordinary ``SURREAL_*`` connection variable — from the shell or from
   ``.env`` — is discarded. Nothing the application would use in a deployment
   can select the database of a test run.
2. Without an explicit opt-in every connection is pointed at a closed loopback
   port: tests that reach the database layer fail to connect, immediately.
3. With ``OPEN_NOTEBOOK_TEST_ALLOW_DATABASE=1`` the database must be designated
   through the dedicated ``OPEN_NOTEBOOK_TEST_SURREAL_*`` variables, all of
   them, with no defaults. The designation is accepted only when its isolation
   can be checked from the values alone:

   - loopback host and an explicit port that is not the application default;
   - namespace and database names that are marked as test names and are not
     the application defaults;
   - credentials that are not the ones found in the ordinary settings.

   Anything else aborts the run before a single test — there is no fallback.
4. At connection time ``guard_connections`` refuses every endpoint other than
   the one decided here, whatever a test did to the environment meanwhile.

The checks never open a connection.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import urlsplit

#: Nothing listens on the discard port of the loopback interface.
CLOSED_URL = "ws://127.0.0.1:9/rpc"

ALLOW_VAR = "OPEN_NOTEBOOK_TEST_ALLOW_DATABASE"
TEST_URL_VAR = "OPEN_NOTEBOOK_TEST_SURREAL_URL"
TEST_USER_VAR = "OPEN_NOTEBOOK_TEST_SURREAL_USER"
TEST_PASSWORD_VAR = "OPEN_NOTEBOOK_TEST_SURREAL_PASSWORD"
TEST_NAMESPACE_VAR = "OPEN_NOTEBOOK_TEST_SURREAL_NAMESPACE"
TEST_DATABASE_VAR = "OPEN_NOTEBOOK_TEST_SURREAL_DATABASE"

#: Ordinary connection settings of the application. Never used by a test run.
AMBIENT_VARS: Tuple[str, ...] = (
    "SURREAL_URL",
    "SURREAL_ADDRESS",
    "SURREAL_PORT",
    "SURREAL_USER",
    "SURREAL_PASSWORD",
    "SURREAL_PASS",
    "SURREAL_NAMESPACE",
    "SURREAL_DATABASE",
)

#: Port of the application's default endpoint (and of every example compose).
DEFAULT_APPLICATION_PORT = 8000
#: Namespace / database names of a default deployment.
DEFAULT_APPLICATION_NAMES = frozenset({"open_notebook"})

_ALLOWED_SCHEMES = frozenset({"ws", "wss", "http", "https"})
_TRUE = frozenset({"1", "true", "yes"})
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


class DatabaseIsolationError(RuntimeError):
    """The test database configuration cannot be shown to be isolated."""


@dataclass(frozen=True)
class DatabasePlan:
    """What the test run is allowed to connect to."""

    mode: str  # "closed" | "designated"
    url: str
    env: Dict[str, str] = field(default_factory=dict)
    removed: Tuple[str, ...] = ()

    def describe(self) -> str:
        """One line for the pytest header. Never contains credentials."""
        if self.mode == "closed":
            return "database isolation: closed port (no database is reachable)"
        endpoint = normalize_endpoint(self.url)
        assert endpoint is not None
        return (
            "database isolation: designated test database on "
            f"loopback port {endpoint[1]} "
            f"({self.env['SURREAL_NAMESPACE']}/{self.env['SURREAL_DATABASE']})"
        )


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_endpoint(url: object) -> Optional[Tuple[str, int]]:
    """``(host, port)`` of a database URL, or ``None`` when it has no explicit
    host and port. Every loopback spelling maps to the same host."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in _ALLOWED_SCHEMES or not host or port is None:
        return None
    return ("loopback" if _is_loopback(host) else host.lower(), port)


def _required(environ: Mapping[str, str], name: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise DatabaseIsolationError(
            f"{ALLOW_VAR} is set but {name} is not: a test database must be "
            "designated explicitly (there is no default)."
        )
    return value


def _check_name(kind: str, variable: str, value: str) -> None:
    if not _NAME_RE.match(value):
        raise DatabaseIsolationError(
            f"{variable}: the test {kind} name may only contain letters, "
            "digits and underscores."
        )
    if value.lower() in DEFAULT_APPLICATION_NAMES:
        raise DatabaseIsolationError(
            f"{variable}: the test {kind} must not be the application default name."
        )
    if "test" not in value.lower():
        raise DatabaseIsolationError(
            f"{variable}: the test {kind} name must contain 'test' so that it "
            "cannot be mistaken for a deployment."
        )


def resolve(environ: Mapping[str, str]) -> DatabasePlan:
    """Decide what a test run may connect to. Raises ``DatabaseIsolationError``
    when a database was requested but its isolation cannot be verified."""
    removed = tuple(name for name in AMBIENT_VARS if name in environ)

    if (environ.get(ALLOW_VAR) or "").strip().lower() not in _TRUE:
        return DatabasePlan(
            mode="closed",
            url=CLOSED_URL,
            env={"SURREAL_URL": CLOSED_URL},
            removed=removed,
        )

    url = _required(environ, TEST_URL_VAR)
    user = _required(environ, TEST_USER_VAR)
    password = _required(environ, TEST_PASSWORD_VAR)
    namespace = _required(environ, TEST_NAMESPACE_VAR)
    database = _required(environ, TEST_DATABASE_VAR)

    endpoint = normalize_endpoint(url)
    if endpoint is None:
        raise DatabaseIsolationError(
            f"{TEST_URL_VAR} must be a ws:// / wss:// / http:// / https:// URL "
            "with an explicit host and port."
        )
    host, port = endpoint
    if host != "loopback":
        raise DatabaseIsolationError(
            f"{TEST_URL_VAR} must point at the loopback interface: the "
            "isolation of a database on another host cannot be verified."
        )
    if port == DEFAULT_APPLICATION_PORT:
        raise DatabaseIsolationError(
            f"{TEST_URL_VAR} uses port {DEFAULT_APPLICATION_PORT}, the "
            "application's default database port: it may be a deployment. "
            "Start the disposable test database on another port."
        )

    _check_name("namespace", TEST_NAMESPACE_VAR, namespace)
    _check_name("database", TEST_DATABASE_VAR, database)

    ambient_secrets = {
        (environ.get(name) or "").strip()
        for name in ("SURREAL_PASSWORD", "SURREAL_PASS")
    } - {""}
    if password in ambient_secrets:
        raise DatabaseIsolationError(
            f"{TEST_PASSWORD_VAR} equals the password of the ordinary "
            "SURREAL_* settings: a test database must have its own "
            "credentials."
        )
    ambient_endpoint = normalize_endpoint(environ.get("SURREAL_URL"))
    if ambient_endpoint is not None and ambient_endpoint == endpoint:
        raise DatabaseIsolationError(
            f"{TEST_URL_VAR} is the endpoint of the ordinary SURREAL_URL "
            "setting: a test database must not be the configured one."
        )

    return DatabasePlan(
        mode="designated",
        url=url,
        env={
            "SURREAL_URL": url,
            "SURREAL_USER": user,
            "SURREAL_PASSWORD": password,
            "SURREAL_NAMESPACE": namespace,
            "SURREAL_DATABASE": database,
        },
        removed=removed,
    )


def apply(environ: Dict[str, str]) -> DatabasePlan:
    """Resolve and rewrite ``environ`` in place. When the configuration is
    refused the environment is closed first and the error is raised after, so
    nothing can connect even if the caller mishandles the exception."""
    try:
        plan = resolve(environ)
    except DatabaseIsolationError:
        for name in AMBIENT_VARS:
            environ.pop(name, None)
        environ["SURREAL_URL"] = CLOSED_URL
        raise
    for name in AMBIENT_VARS:
        environ.pop(name, None)
    environ.update(plan.env)
    return plan


def is_allowed(plan: DatabasePlan, url: object) -> bool:
    """True only for the endpoint decided by ``plan``."""
    endpoint = normalize_endpoint(url)
    return endpoint is not None and endpoint == normalize_endpoint(plan.url)


def verify_effective(plan: DatabasePlan, effective_url: object) -> None:
    """Check the URL the application would really use against the plan."""
    if effective_url != plan.url:
        raise DatabaseIsolationError(
            "the effective database URL of the application is not the one "
            "decided for this test run; refusing to run tests."
        )


def guard_connections(plan: DatabasePlan, repository_module) -> Callable:
    """Make ``repository_module`` refuse to open any connection whose endpoint
    is not the planned one — checked on every call, with the URL actually
    passed, so a test that changes the environment cannot redirect it."""
    original = repository_module.AsyncSurreal

    def guarded_async_surreal(url, *args, **kwargs):
        if not is_allowed(plan, url):
            raise DatabaseIsolationError(
                "test isolation: connection to a database endpoint outside "
                "the test run's plan was refused."
            )
        return guarded_async_surreal.original(url, *args, **kwargs)

    guarded_async_surreal.original = original  # type: ignore[attr-defined]
    guarded_async_surreal.plan = plan  # type: ignore[attr-defined]
    repository_module.AsyncSurreal = guarded_async_surreal
    return guarded_async_surreal
