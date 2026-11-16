"""Regression tests for the test suite's database isolation.

No test here opens a network connection: decisions are checked on plain
dictionaries, and connection attempts are intercepted before a client object
is even constructed.
"""

import os
import subprocess
import sys
from pathlib import Path

import db_isolation
import pytest

from open_notebook.database import repository

REPO_ROOT = Path(__file__).resolve().parent.parent

# An application-default endpoint, as a developer shell or a .env would carry.
AMBIENT_URL = "ws://localhost:8000/rpc"

VALID = {
    db_isolation.ALLOW_VAR: "1",
    db_isolation.TEST_URL_VAR: "ws://127.0.0.1:18765/rpc",
    db_isolation.TEST_USER_VAR: "throwaway",
    db_isolation.TEST_PASSWORD_VAR: "throwaway-password",
    db_isolation.TEST_NAMESPACE_VAR: "pytest_ns",
    db_isolation.TEST_DATABASE_VAR: "pytest_db",
}


def _with(**changes):
    env = dict(VALID)
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


# ---------------------------------------------------------------- decisions


def test_no_configuration_means_closed_port():
    plan = db_isolation.resolve({})
    assert plan.mode == "closed"
    assert plan.url == db_isolation.CLOSED_URL
    assert plan.env == {"SURREAL_URL": db_isolation.CLOSED_URL}


@pytest.mark.parametrize(
    "ambient",
    [
        {"SURREAL_URL": AMBIENT_URL},
        {"SURREAL_ADDRESS": "localhost", "SURREAL_PORT": "8000"},
        {
            "SURREAL_URL": "ws://db.example.internal:8000/rpc",
            "SURREAL_USER": "root",
            "SURREAL_PASSWORD": "deployment-password",
            "SURREAL_NAMESPACE": "open_notebook",
            "SURREAL_DATABASE": "open_notebook",
        },
    ],
)
def test_ordinary_settings_never_select_the_database(ambient):
    env = dict(ambient)
    plan = db_isolation.apply(env)
    assert plan.mode == "closed"
    assert env == {"SURREAL_URL": db_isolation.CLOSED_URL}
    assert set(plan.removed) == set(ambient)


@pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe"])
def test_only_an_explicit_true_value_opts_in(value):
    plan = db_isolation.resolve(_with(**{db_isolation.ALLOW_VAR: value}))
    assert plan.mode == "closed"


def test_opt_in_alone_does_not_fall_back_to_a_default_database():
    with pytest.raises(db_isolation.DatabaseIsolationError, match="no default"):
        db_isolation.resolve({db_isolation.ALLOW_VAR: "1", "SURREAL_URL": AMBIENT_URL})


@pytest.mark.parametrize(
    "missing",
    [
        db_isolation.TEST_URL_VAR,
        db_isolation.TEST_USER_VAR,
        db_isolation.TEST_PASSWORD_VAR,
        db_isolation.TEST_NAMESPACE_VAR,
        db_isolation.TEST_DATABASE_VAR,
    ],
)
def test_every_part_of_the_designation_is_required(missing):
    with pytest.raises(db_isolation.DatabaseIsolationError, match=missing):
        db_isolation.resolve(_with(**{missing: None}))
    with pytest.raises(db_isolation.DatabaseIsolationError, match=missing):
        db_isolation.resolve(_with(**{missing: "   "}))


@pytest.mark.parametrize(
    "url",
    [
        "ws://localhost:8000/rpc",  # application default
        "ws://127.0.0.1:8000/rpc",
        "ws://[::1]:8000/rpc",
        "http://127.0.0.2:8000",
        "ws://localhost/rpc",  # no explicit port
        "ws://localhost/rpc:8000",  # legacy fallback shape: no real port
        "localhost:18765",  # no scheme
        "mem://",
        "file:///tmp/x.db",
        "ws://surrealdb:18765/rpc",  # not loopback: cannot be verified
        "ws://db.example.internal:18765/rpc",
        "ws://192.0.2.10:18765/rpc",
        "ws://127.0.0.1:notaport/rpc",
        "::not a url::",
    ],
)
def test_unverifiable_endpoints_are_refused(url):
    with pytest.raises(db_isolation.DatabaseIsolationError):
        db_isolation.resolve(_with(**{db_isolation.TEST_URL_VAR: url}))


@pytest.mark.parametrize(
    "variable", [db_isolation.TEST_NAMESPACE_VAR, db_isolation.TEST_DATABASE_VAR]
)
@pytest.mark.parametrize(
    "name", ["open_notebook", "OPEN_NOTEBOOK", "production", "main", "te st", "a;b"]
)
def test_names_that_could_be_a_deployment_are_refused(variable, name):
    with pytest.raises(db_isolation.DatabaseIsolationError):
        db_isolation.resolve(_with(**{variable: name}))


@pytest.mark.parametrize("ambient", ["SURREAL_PASSWORD", "SURREAL_PASS"])
def test_reusing_the_ordinary_password_is_refused(ambient):
    env = _with(**{ambient: VALID[db_isolation.TEST_PASSWORD_VAR]})
    with pytest.raises(db_isolation.DatabaseIsolationError, match="own credentials"):
        db_isolation.resolve(env)


def test_designating_the_configured_endpoint_is_refused():
    env = _with(SURREAL_URL="ws://localhost:18765/rpc")  # same endpoint, other spelling
    with pytest.raises(db_isolation.DatabaseIsolationError, match="configured one"):
        db_isolation.resolve(env)


def test_a_verifiable_designation_is_accepted_and_replaces_everything():
    env = _with(
        SURREAL_URL=AMBIENT_URL,
        SURREAL_USER="root",
        SURREAL_PASSWORD="deployment-password",
        SURREAL_PASS="legacy-password",
        SURREAL_ADDRESS="localhost",
        SURREAL_PORT="8000",
        SURREAL_NAMESPACE="open_notebook",
        SURREAL_DATABASE="open_notebook",
    )
    plan = db_isolation.apply(env)
    assert plan.mode == "designated"
    assert env["SURREAL_URL"] == VALID[db_isolation.TEST_URL_VAR]
    assert env["SURREAL_USER"] == "throwaway"
    assert env["SURREAL_PASSWORD"] == "throwaway-password"
    assert env["SURREAL_NAMESPACE"] == "pytest_ns"
    assert env["SURREAL_DATABASE"] == "pytest_db"
    for leftover in ("SURREAL_PASS", "SURREAL_ADDRESS", "SURREAL_PORT"):
        assert leftover not in env
    assert "deployment-password" not in env.values()
    assert "throwaway" not in plan.describe()  # header never shows credentials


def test_a_refused_configuration_leaves_the_environment_closed():
    env = _with(
        **{db_isolation.TEST_URL_VAR: AMBIENT_URL},
        SURREAL_URL=AMBIENT_URL,
        SURREAL_PASSWORD="deployment-password",
    )
    with pytest.raises(db_isolation.DatabaseIsolationError):
        db_isolation.apply(env)
    assert env["SURREAL_URL"] == db_isolation.CLOSED_URL
    for name in db_isolation.AMBIENT_VARS:
        if name != "SURREAL_URL":
            assert name not in env


def test_effective_url_must_be_the_planned_one():
    plan = db_isolation.resolve({})
    db_isolation.verify_effective(plan, db_isolation.CLOSED_URL)
    for other in (AMBIENT_URL, "ws://localhost/rpc:8000", "", None):
        with pytest.raises(db_isolation.DatabaseIsolationError):
            db_isolation.verify_effective(plan, other)


# ------------------------------------------------------- this very test run


def test_this_run_uses_the_planned_endpoint(database_plan):
    assert repository.get_database_url() == database_plan.url
    assert os.environ["SURREAL_URL"] == database_plan.url
    assert "SURREAL_ADDRESS" not in os.environ
    assert "SURREAL_PORT" not in os.environ
    assert "SURREAL_PASS" not in os.environ
    if database_plan.mode == "closed":
        assert database_plan.url == db_isolation.CLOSED_URL
        assert "SURREAL_PASSWORD" not in os.environ
        assert "SURREAL_USER" not in os.environ


def test_the_repository_is_guarded_in_this_run(database_plan):
    guard = repository.AsyncSurreal
    assert getattr(guard, "plan", None) is database_plan
    assert callable(guard.original)


@pytest.fixture
def no_real_client(monkeypatch):
    """Replace the real client constructor behind the guard: a test below can
    then prove that a refused connection never reaches it."""
    calls = []

    def fake_client(url, *args, **kwargs):
        calls.append(url)
        raise AssertionError("a database client was constructed")

    monkeypatch.setattr(repository.AsyncSurreal, "original", fake_client)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        AMBIENT_URL,
        "ws://127.0.0.1:8000/rpc",
        "ws://surrealdb:8000/rpc",
        "ws://db.example.internal:8000/rpc",
        "ws://127.0.0.1:19/rpc",  # loopback, but not the planned port
    ],
)
async def test_a_redirected_environment_cannot_connect(
    monkeypatch, no_real_client, url
):
    monkeypatch.setenv("SURREAL_URL", url)
    assert repository.get_database_url() == url
    with pytest.raises(db_isolation.DatabaseIsolationError, match="refused"):
        async with repository.db_connection():
            pass
    with pytest.raises(db_isolation.DatabaseIsolationError, match="refused"):
        await repository.repo_query("RETURN 1")
    assert no_real_client == []


@pytest.mark.asyncio
async def test_the_application_default_endpoint_cannot_connect(
    monkeypatch, no_real_client
):
    """With every setting removed the application falls back to its built-in
    default endpoint; the test run must refuse it as well."""
    for name in db_isolation.AMBIENT_VARS:
        monkeypatch.delenv(name, raising=False)
    assert "localhost" in repository.get_database_url()
    with pytest.raises(db_isolation.DatabaseIsolationError, match="refused"):
        async with repository.db_connection():
            pass
    assert no_real_client == []


# ------------------------------------------------- whole-process behaviour

_PROBE = """
import os
from open_notebook.database import repository

def test_probe():
    print("EFFECTIVE=" + repository.get_database_url())
    print("PASSWORD_SET=" + str("SURREAL_PASSWORD" in os.environ))
    print("GUARDED=" + str(hasattr(repository.AsyncSurreal, "plan")))
"""


def _run_pytest(tmp_path, extra_env, dotenv=None):
    """Run a one-test probe in a copy of the test configuration. The probe
    only reads the decision; it never connects."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    for name in ("conftest.py", "db_isolation.py"):
        (project / "tests" / name).write_text(
            (REPO_ROOT / "tests" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (project / "tests" / "test_probe.py").write_text(_PROBE, encoding="utf-8")
    if dotenv is not None:
        (project / ".env").write_text(dotenv, encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SURREAL_", "OPEN_NOTEBOOK_TEST_"))
    }
    env.update(extra_env)
    env["PYTHONPATH"] = str(REPO_ROOT)  # the probe imports the real package
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-s", "-p", "no:cacheprovider", "tests"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_process_with_deployment_settings_runs_against_the_closed_port(tmp_path):
    result = _run_pytest(
        tmp_path,
        {"SURREAL_URL": AMBIENT_URL, "SURREAL_PASSWORD": "shell-password"},
        dotenv=(
            "SURREAL_URL=ws://localhost:8000/rpc\n"
            "SURREAL_USER=root\n"
            "SURREAL_PASSWORD=dotenv-password\n"
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "EFFECTIVE=" + db_isolation.CLOSED_URL in result.stdout
    assert "PASSWORD_SET=False" in result.stdout
    assert "GUARDED=True" in result.stdout
    assert "closed port" in result.stdout
    assert "dotenv-password" not in result.stdout + result.stderr
    assert "shell-password" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "extra",
    [
        {},  # opt-in with nothing designated
        {db_isolation.TEST_URL_VAR: AMBIENT_URL},  # the application default
        {db_isolation.TEST_NAMESPACE_VAR: "open_notebook"},
    ],
)
def test_process_aborts_before_any_test_when_isolation_is_unverified(tmp_path, extra):
    env = {db_isolation.ALLOW_VAR: "1", "SURREAL_URL": AMBIENT_URL}
    if extra:
        env.update(_with(**extra))
    result = _run_pytest(tmp_path, env)
    assert result.returncode == 4, result.stdout + result.stderr  # usage error
    assert "test database isolation" in result.stderr
    assert "No test was run" in result.stderr
    assert "EFFECTIVE=" not in result.stdout
    assert "throwaway-password" not in result.stdout + result.stderr
