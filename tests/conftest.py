"""
Pytest configuration file.

This file ensures that the project root is in the Python path,
allowing tests to import from the api and open_notebook modules.
"""

import os
import sys
from pathlib import Path

# Ensure password auth is disabled for tests BEFORE any imports
# The PasswordAuthMiddleware skips auth when this env var is not set
# Set to empty string instead of deleting to prevent it from being reloaded
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""

# Disable JWT auth enforcement for the test suite so endpoint tests can call
# protected routes without minting a token. Dedicated auth tests
# (test_auth.py) toggle this off explicitly to verify real enforcement.
os.environ["OPEN_NOTEBOOK_DISABLE_AUTH"] = "true"

# Load environment variables from .env file
# This must be done BEFORE any imports that depend on environment variables
from dotenv import load_dotenv

# Load .env file from project root
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"Loaded environment variables from {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}")

# The test suite must never talk to a database it was not explicitly given.
# tests/db_isolation.py explains the rules; in short: the ordinary SURREAL_*
# settings (shell or .env) are discarded, every connection goes to a closed
# port unless a disposable loopback database is designated through the
# OPEN_NOTEBOOK_TEST_SURREAL_* variables, and a designation whose isolation
# cannot be verified aborts the run. This runs after loading .env, so a
# developer's settings cannot undo it, and before any project import.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "db_isolation", Path(__file__).parent / "db_isolation.py"
)
assert _spec is not None and _spec.loader is not None
db_isolation = importlib.util.module_from_spec(_spec)
sys.modules["db_isolation"] = db_isolation
_spec.loader.exec_module(db_isolation)

_DATABASE_PLAN = None
_DATABASE_PLAN_ERROR = None
try:
    _DATABASE_PLAN = db_isolation.apply(os.environ)
except db_isolation.DatabaseIsolationError as exc:  # environment already closed
    _DATABASE_PLAN_ERROR = str(exc)

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


import pytest  # noqa: E402


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose each phase's report as item.rep_<phase> (used by acceptance reports)."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def pytest_configure(config):
    """Abort before collection when the test database cannot be verified, and
    check the URL the application would really use."""
    if _DATABASE_PLAN_ERROR is not None:
        raise pytest.UsageError(
            "test database isolation: "
            + _DATABASE_PLAN_ERROR
            + " No test was run. See tests/README.md."
        )
    from open_notebook.database import repository

    try:
        db_isolation.verify_effective(_DATABASE_PLAN, repository.get_database_url())
    except db_isolation.DatabaseIsolationError as exc:
        raise pytest.UsageError(f"test database isolation: {exc}")
    db_isolation.guard_connections(_DATABASE_PLAN, repository)
    config._database_plan = _DATABASE_PLAN


def pytest_report_header(config):
    plan = getattr(config, "_database_plan", None)
    return plan.describe() if plan is not None else None


@pytest.fixture(scope="session")
def database_plan(pytestconfig):
    """The database decision of this test run (tests/db_isolation.py)."""
    return pytestconfig._database_plan
