# Tests

Run the backend suite from the repository root:

```bash
uv run pytest tests/
```

## Database isolation

The suite never uses the application's ordinary database settings. `tests/conftest.py` applies the rules of
`tests/db_isolation.py` before any project module is imported:

- every `SURREAL_*` connection variable — from the shell or from a `.env` in the project root — is discarded, so a
  deployment's endpoint or credentials can never select the database of a test run;
- by default every connection is pointed at a closed loopback port: tests that reach the database layer fail to
  connect immediately (the suite is written to tolerate that);
- at connection time, any endpoint other than the one decided for the run is refused, whatever a test did to the
  environment in the meantime.

The pytest header shows the decision, e.g. `database isolation: closed port (no database is reachable)`.

To run against a **disposable** database, designate it explicitly — all six variables, there are no defaults:

```bash
OPEN_NOTEBOOK_TEST_ALLOW_DATABASE=1 \
OPEN_NOTEBOOK_TEST_SURREAL_URL=ws://127.0.0.1:18000/rpc \
OPEN_NOTEBOOK_TEST_SURREAL_USER=... \
OPEN_NOTEBOOK_TEST_SURREAL_PASSWORD=... \
OPEN_NOTEBOOK_TEST_SURREAL_NAMESPACE=pytest_ns \
OPEN_NOTEBOOK_TEST_SURREAL_DATABASE=pytest_db \
uv run pytest tests/
```

The designation is accepted only when its isolation can be checked from the values alone: a loopback host with an
explicit port other than the application default (8000), namespace and database names that contain `test` and are not
`open_notebook`, and credentials different from the ordinary `SURREAL_*` ones. Anything else aborts the run before a
single test is executed — there is no fallback. Never point these variables at a database that holds real data.

Regression tests for these rules: `tests/test_database_isolation.py`.
