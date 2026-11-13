# ADR-014: Background job API is admin-only; workers re-validate job input

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: [ADR-004](ADR-004-background-workers.md) (background workers), [ADR-012](ADR-012-approval-workflow.md) (approval workflow), [docs/security/BACKGROUND_JOB_SECURITY.md](../../security/BACKGROUND_JOB_SECURITY.md), [docs/ocr/DECISIONS.md](../../ocr/DECISIONS.md) D-19

## Context

`POST /api/commands/jobs` accepted any registered command with arbitrary input from any
authenticated user. `process_source` with a crafted `content_state` could read any file the
worker can read (`file_path`), delete it (`delete_source`), or fetch internal URLs (SSRF);
other commands could write data or spend provider credits. The worker trusted job input
because it assumed only the API's feature endpoints created jobs.

## Decision

- The generic commands router requires an admin. Generic submission is disabled by an
  empty allow-list (deny by default). Each feature keeps its own endpoint, with its own
  authorization checks, that submits its own command.
- Workers do not trust job input (`open_notebook/utils/job_input_guard.py`):
  - upload paths must resolve, via realpath, inside `UPLOADS_FOLDER`;
  - files are only deleted inside uploads;
  - URLs pass `validate_url()` on every redirect hop;
  - record ids must belong to the expected table;
  - `process_source` only processes the file/URL that is the source's own asset.
- Invalid job input raises `ValueError`, which marks the job permanently failed (no retry).

## Consequences

- External scripts that submitted jobs through `/api/commands/jobs` must use the feature
  endpoints, or must be added to the allow-list with a reviewed input schema.
- Job status and listing are admin-only. The frontend only used them from admin screens.
- Residual risk: DNS rebinding between the worker's validation and the fetch. Private hosts
  stay reachable by design (self-hosted model servers).
