# ADR-012: Maker-checker approval of sources, scoped by a two-level notebook hierarchy

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: [PDR-001](PDR-001-single-user-first.md), [ADR-008](ADR-008-notebook-scoped-search.md), migrations 31–33, [CHANGELOG 1.0.8](../../../CHANGELOG.md)

## Context

ChatBot5400 serves a bank branch whose documents become the knowledge base everyone chats with, so content must be controlled before it is used. RBAC had two roles (admin, user) and only admins added sources. The branch needs staff to submit documents and designated reviewers, each responsible for a subject area, to approve them. Unapproved text must not reach search, RAG or chat, and processing is asynchronous, so approval races with the worker.

## Decision

**Add maker and checker roles and gate sources on an approval status, with reviewer scope derived from the notebook hierarchy.**

- **Roles**: `admin`, `approver` (checker), `contributor` (maker), `user`. Checkers review and manage notebooks but do not submit sources.
- **Hierarchy**: a notebook may have a `parent`; exactly two levels. A top-level notebook is a category whose `managers` are its approvers; their scope is the category plus its sub-notebooks.
- **State on the source**: a maker's source starts `pending`, is hidden everywhere (lists, single-source endpoints, chat context, search) and is not embedded until approved. Rejecting deletes it.
- **Approval fields are written only at creation and by targeted `UPDATE`s**, never by a full-record save, because the worker saves a copy loaded before extraction.

## Alternatives considered

- **Capability flags on `user` instead of roles** — rejected: every check and screen would need flag combinations.
- **A separate category table, or a submissions table copied into `source` on approval** — rejected: a `parent` link and a status column reuse the existing pages and processing pipeline.
- **Filter pending inside `fn::text_search` / `fn::vector_search`** — deferred: correct long term, but it redefines both functions in a migration that could not be run against a real database when this was written. Search filters in Python for now.
- **Keep rejected sources as rows** — rejected by the product owner: they accumulate as clutter.

## Consequences

- Any new code path that reads a source by id or searches must apply the visibility rule; a missed path leaks pending text.
- Search costs one extra query until the filter moves into the SurrealQL functions.
- Rolling back past migration 31 requires restoring a backup: older code cannot load users with the new roles.
