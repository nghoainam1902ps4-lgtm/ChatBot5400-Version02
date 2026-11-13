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
| source graph `content_process` | `file_path`: canonical path (symlinks resolved) must be a regular file strictly inside `UPLOADS_FOLDER`; `url`: `validate_url()` + every hop of a redirect pre-check re-validated (see §5); delete re-checked immediately before `unlink` (a symlink is removed itself, never its target) |
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

**Status after Phase 9A:** the URL-related items below are **mitigated when URL ingestion
is switched off** (the default, §6) and **still present when it is switched on**.

- The redirect check is a **pre-check**. The worker validates the URL and each hop of the
  redirect chain the server returns to its own request. content-core/Docling then fetch the
  URL again and follow redirects themselves, so the pre-check does not cover:
  - a server that answers the second request differently (e.g. 200 first, then a 302 to an
    internal address);
  - DNS rebinding between the check and the fetch;
  - network errors during the pre-check, in which case only the URL itself is checked.

  Closing this fully would need the worker to download through a pinned client and hand the
  file to extraction (a content-core behaviour change, not done here). Private hosts remain
  reachable by design.
- `api/routers/sources.py` submits jobs on behalf of non-admin roles as before; those
  routes keep their existing checks (approval workflow, containment).

## 6. URL ingestion switch (Phase 9A, docs/ocr D-29)

`OPEN_NOTEBOOK_ENABLE_URL_INGESTION` — adding a source from a web address, and
re-fetching an existing URL source.

| | |
|---|---|
| Default | **Off.** Unset, empty, or any value other than `true` / `1` / `yes` / `on` keeps it off. A missing or mistyped value never enables it. |
| Who can change it | Whoever controls the container environment. There is no API or Settings field; `GET /api/capabilities` only reports it. |
| Exemptions | None. Admin, approver and contributor are refused alike. |
| Read at | Every call (not cached at import). |

Enforcement when off — each layer refuses **before** any DNS lookup or request:

| Layer | Path | Result |
|---|---|---|
| API | `POST /api/sources` and `POST /api/sources/json` with `type=link` (sync and async) | 403, no source record, no job |
| API | `POST /api/sources/{id}/retry` for a source whose asset is a URL | 403, nothing queued |
| Worker | `process_source` with `content_state.url` — also jobs queued before the switch was turned off, retries, and anything that writes a job without the API | permanent failure (`ValueError`, not retried), before the source is loaded |
| Graph | `content_process` with a `url`, with or without `content` | refused before `validate_source_url` and before content-core |
| OCR layer | `should_use_native_ocr_for_url`, `extract_url_with_selected_ocr` | refused before the MIME probe / download |

Not affected: file uploads, pasted text, OCR, Layout / TableFormer, transformations,
embeddings, search, chat, provider (LLM / embedding) calls, OCR model installation and
online preparation. A test pins the list of modules that consult the switch
(`tests/test_url_ingestion_switch.py::test_switch_is_only_used_by_url_ingestion_code`).
Existing URL sources are kept: their stored text, insights and embeddings stay readable
and searchable; only the re-download is refused. Nothing is deleted or migrated.

What this does and does not claim:

- **Off:** the application offers no way to make the server fetch a user-supplied URL
  through source ingestion, so the redirect / DNS-rebinding weakness of §5 cannot be
  reached through it. This is a mitigation by removal of the feature, not a fix of the
  downloader.
- **On:** behaviour and policy are exactly as before (`validate_url` + redirect
  pre-check). **The residual SSRF risk of §5 is back.** SSRF is not claimed to be fixed.
- Out of scope of the switch (unchanged, admin-configured, already validated with
  `validate_url`): provider / credential base URLs, model discovery, the optional
  remote Crawl4AI / Firecrawl / Jina endpoints (only used by URL ingestion, so idle
  while it is off), Hugging Face / model downloads during online preparation.
- A release for the internal bank environment is assessed **only** with the switch off,
  unless an additional control (for example an approved network egress policy for the
  application container) is in place.

Upgrade note: a deployment that used URL sources must set
`OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true` explicitly to keep the feature.

Tests: `tests/test_url_ingestion_switch.py` (43), `frontend/src/components/sources/steps/SourceTypeStep.test.tsx` (3).

## 7. Phase 9B review: role enforcement outside the job API (docs/ocr D-31)

The Phase 9B independent review found authorization gaps that predate the OCR work
(present at `5e04227`) and that undercut §6:

| Finding | Before | After |
|---|---|---|
| `/api/credentials` writes, `test`, `discover`, `register-models`, `migrate-*`; `/api/models` create / delete / test / defaults / sync / auto-assign | any logged-in account. Repointing a credential's `base_url` sent the stored API key and later chat traffic to another host; "test connection" reached internal addresses **regardless of the URL-ingestion switch** | administrator only (`require_admin`) |
| Transformation create / update / delete / execute / default prompt, `POST /api/embed`, `POST /api/embeddings/rebuild`, `DELETE /api/insights/{id}` | any logged-in account (the UI only showed them to administrators) | administrator only |
| `POST /api/sources/json` with a caller-supplied `file_path` inside the uploads folder | any submitter: could read, and with `delete_source` remove, a file uploaded by someone else | administrator only; other roles must upload the file with the request |

So the statement in §6 that provider / credential base URLs are "admin-configured" is
now enforced by the backend, not only by the UI.

Still open to every account, by product design or pending an owner decision: podcast
generation / retry / deletion and episode / speaker profiles; `GET /api/podcasts/jobs/{id}`
returns the status of any command id (ids are random; OCR job ids are only shown to
administrators). `Source.delete()` unlinks the stored asset path without the containment
re-check used by the worker (the path can now only come from a server-side upload or an
administrator).

Tests: `tests/test_admin_route_authorization.py` (role matrix per route, plus a test that
pins every POST / PUT / DELETE route as either role-guarded or deliberately open).
