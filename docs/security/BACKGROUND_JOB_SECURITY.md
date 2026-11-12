# Background Job Security

Phase 8A remediation of the high-severity issue recorded in
[`docs/ocr/OCR_COMMANDS_JOBS_RISK.md`](../ocr/OCR_COMMANDS_JOBS_RISK.md).

## 1. Threat

The generic surreal-commands router (`api/routers/commands.py`) only required a
login. Any authenticated account could submit **any** registered command with
**arbitrary input**, read any job's result, or call the cancel/debug routes.
Through `process_source` that meant: read an arbitrary server file into a source,
delete an arbitrary file (`delete_source=true`, worker runs as root), SSRF with a
URL that never went through `validate_url()`, and overwrite another user's source.

## 2. Inventory

| Endpoint | Before | After | Frontend use |
|---|---|---|---|
| `POST /api/commands/jobs` | any login, any command + input | **admin only AND command in `GENERIC_SUBMIT_ALLOWLIST` (empty ⇒ disabled)**, 403 | none |
| `GET /api/commands/jobs` | any login (returns `[]`) | admin only; never returns args/results | none |
| `GET /api/commands/jobs/{id}` | any login, any job incl. `result` | admin only | admin-only insight polling (`lib/api/insights.ts`; `POST /sources/{id}/insights` is already admin-only) |
| `DELETE /api/commands/jobs/{id}` | any login (no-op stub) | admin only | none |
| `GET /api/commands/registry/debug` | any login | admin only | none |

Feature endpoints keep submitting their own jobs with their own validation and
authorisation (sources, insights, podcasts, embeddings, OCR). OCR jobs keep their
one-time nonce.

| Command | Input now validated in the worker (all callers, admins included) |
|---|---|
| `process_source` | `source_id`/`notebook_ids`/`transformations` must be ids of the right table; `content_state` keys limited to `url`, `file_path`, `content`, `delete_source`; `file_path`/`url` must equal the source's own asset |
| source graph `content_process` | `file_path`: canonical path (symlinks resolved) must be a regular file strictly inside `UPLOADS_FOLDER`; `url`: `validate_url()` + every redirect hop re-validated; delete re-checked immediately before `unlink` (a symlink is removed itself, never its target) |
| `run_transformation` | `source:` / `transformation:` ids |
| `create_insight`, `embed_source` | `source:` id |
| `embed_note` | `note:` id |
| `embed_insight` | `source_insight:` id |
| `ocr_install_model`, `ocr_test_engine` | unchanged: nonce written by the admin-only OCR API |

Rejections raise `UnsafeJobInput` (a `ValueError`) ⇒ permanent failure, no retries.

URL policy is the existing one (`open_notebook/utils/url_validation.py`): http/https
only; link-local and cloud-metadata addresses blocked; private/loopback hosts stay
allowed on purpose (self-hosted deployments). It now also covers the worker and
redirect targets, for both the content-core path and the OCR layer path.

## 3. Old jobs without ownership

Jobs are not given owners: with every generic job route admin-only, ownership is not
needed to authorise them and nothing is guessed. Existing (old) jobs are readable by
admins only — the same audience as before for the only frontend consumer.

## 4. Tests

`tests/test_background_job_security.py` (57 tests, synthetic canary files + local
stub HTTP server only):

- 401 without login, 403 for `user` / `contributor` / `approver` on all 5 routes;
- generic submission refused even for admins (5 commands), submit never called;
- admin status polling and list (no payload) still work;
- upload paths: outside, `../` traversal, symlink escape, missing, NUL, root dir;
- delete: outside refused, symlink link removed but canary target kept;
- URLs: `file:`, `gopher:`, `ftp:`, IPv4/IPv6 metadata, **redirect to metadata** (live stub);
- source graph: canary outside uploads never read nor deleted; unsafe URL never fetched;
  valid upload processed and deleted;
- `process_source`: wrong-table ids, unknown `content_state` keys, file/URL not matching
  the source asset ⇒ rejected before any work; matching asset reaches the graph;
- other commands' id checks; OCR nonce still enforced.

## 5. Residual risk

- DNS rebinding between the worker's validation and content-core's own fetch (same
  window as the API had before); private hosts remain reachable by design.
- `api/routers/sources.py` submits jobs on behalf of non-admin roles as before; those
  routes keep their existing checks (approval workflow, containment).
