# ADR-012: Maker-checker approval of sources, scoped by a two-level notebook hierarchy

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: [PDR-001](PDR-001-single-user-first.md) (single-user first; this is the ChatBot5400 multi-user extension), [ADR-004](ADR-004-background-workers.md) (background workers), [ADR-008](ADR-008-notebook-scoped-search.md) (search functions), migrations 31–33

## Context

ChatBot5400 serves a bank branch where documents become the knowledge base everyone chats with, so content must be controlled before it is used. The existing RBAC had two roles (admin, user) and admins added every source. The branch needs staff to submit documents and designated reviewers, each responsible for a subject area (credit, accounting, …), to approve them. Forces: unapproved text must not reach search, RAG or chat; reviewers must be limited to their area; processing is asynchronous, so approval races with the worker.

## Decision

**Add two roles and gate sources on an approval status, with reviewer scope derived from the notebook hierarchy.**

- **Roles**: `admin`, `approver` (checker), `contributor` (maker), `user` (read/chat). Makers submit; checkers review and manage notebooks but do not submit new sources (separation of duties).
- **Hierarchy**: notebooks get an optional `parent`. Exactly two levels: a top-level notebook is a *category*; `managers` on a category lists its approvers. An approver's scope is their categories plus the direct sub-notebooks.
- **Approval state lives on the source** (`approval_status`, audit fields, optional `assigned_approver` chosen by the maker). A maker's source starts `pending`; admin content is `approved` at creation.
- **Pending is invisible**: list endpoints filter it, single-source endpoints return 404 to callers who may not see it, notebook context skips it, and search results drop hits whose source is pending (filtered in Python after the SurrealQL functions, with a widening fetch when hits were dropped).
- **Pending is not embedded.** Embedding happens once, when the source is both approved and has text; `approve()` and the processing job each claim it with one conditional `UPDATE` (`approval_embed_queued`).
- **Approval fields are written only at creation and by targeted `UPDATE`s**; `Source.save()` refuses in-memory edits to them, because the worker saves a copy loaded before extraction.
- **Reject deletes** the source and everything attached to it.

## Alternatives considered

- **Capability flags on `user` instead of roles** — rejected: every check and screen would need flag combinations; four named roles match how the branch describes staff.
- **A separate `category` table** — rejected: a `parent` link reuses notebooks, their pages and the `reference` edge.
- **A separate submissions table, copied into `source` on approval** — rejected: processing, insights and the review window all operate on sources; a status column avoids a second pipeline.
- **Filter pending inside `fn::text_search` / `fn::vector_search`** — deferred: correct long term (no post-filter), but it means redefining both functions in a migration that could not be exercised against a real database when this was written.
- **Keep rejected sources as `rejected` rows** — rejected by the product owner: they accumulate as clutter.
- **Unlimited nesting** — rejected: scope resolution and the UI stay one query and one indent deep.

## Consequences

- Any new code path that reads sources by id or searches must apply the visibility rule (`assert_can_view_source`, `is_approved`, or the search helpers); a missed path leaks pending text.
- Search costs one extra query (two for text-search insight hits); moving the filter into the SurrealQL functions would remove it.
- Changing approval fields needs a targeted `UPDATE`, not `save()`.
- An approver's scope is cached for 10 seconds for read checks only; write checks resolve it fresh.
- Insights of a pending source are still generated (and embedded) before approval, so a rejected document has already cost model calls.
- Rolling back to a version before migration 31 requires restoring a backup: older code cannot load users with the new roles.
