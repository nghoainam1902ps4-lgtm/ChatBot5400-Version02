# ADR-009: Design B is a presentation-only change with self-hosted fonts

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: "ChatBot 5400 — Handoff phương án B sang Claude Code" (approved, frozen 2026-09-25)

## Context
Design B (icon rail, one tabbed Sources/Notes context panel, flat chat with a 760px reading column) had to land without touching API, data hooks, citation parsing or mobile layout, and the app must run fully offline. `SourcesColumn`, `NotesColumn`, `SourceCard` and `ChatPanel` are rendered both by the desktop layout and by the unchanged mobile tab layout.

## Decision
- Fonts are self-hosted WOFF2 under `frontend/src/app/fonts/` (with each font's `OFL.txt`) loaded via `next/font/local`: Be Vietnam Pro (400–700) for `--font-sans`, Bricolage Grotesque variable (wght 200–800) for `--font-display`. `--font-mono` uses the system monospace stack, because Spline Sans Mono has no Vietnamese glyphs (ơ, ư, ạ…) and would fall back mid-word.
- Desktop-only presentation is opt-in through **additive optional props** that default to the old rendering: `embedded` on `SourcesColumn`/`NotesColumn` and `variant: 'card' | 'row'` on `SourceCard`. Existing props and callbacks are unchanged, so the mobile tree keeps its output.
- The context panel reuses the existing `sourcesCollapsed` flag of `notebook-columns-store`; the sidebar rail is `sidebar-store`'s existing `isCollapsed`, now defaulting to `true`.
- The "Nguồn dẫn" block splits the output of `convertReferencesToCompactMarkdown` at the reference-list marker it writes itself; `source-references.tsx` is not modified.

## Alternatives considered
- Responsive-class-only changes inside the columns: cannot express the single collapse flag or the row layout without changing mobile output.
- Duplicating the columns into new desktop components: two copies of the data/dialog logic to keep in sync.
- Self-hosting Spline Sans Mono anyway: violates the "no mid-word fallback" requirement for Vietnamese.

## Consequences
- Mobile keeps its layout; the shared `ChatPanel` content (messages, composer) is the one place where mobile also receives the new look.
- Anyone changing a column must keep both `embedded` branches working; tests cover the default branch.
- No runtime font requests: builds and deployments work without internet access.
