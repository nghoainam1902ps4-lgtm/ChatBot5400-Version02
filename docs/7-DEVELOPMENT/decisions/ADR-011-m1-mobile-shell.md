# ADR-011: Mobile / responsive chat (M1) is a below-lg presentation layer

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: "ChatBot 5400 — M1 Handoff: Mobile / Responsive Chat" (approved, frozen 2026-09-27), ADR-009, ADR-010

## Context
Below 1024px the app showed the desktop sidebar rail, a stacked notebook header, card-framed columns and a desktop composer. M1 needed a phone/tablet layout (drawer, compact top bar, tab pages, pinned composer, bottom sheets, keyboard-safe height) while Design B desktop and the B2 modal system stay pixel-identical, with no API, data-flow or session changes.

## Decision
- Every mobile rule lives behind `max-lg:` (or in `lg:hidden` elements); default/`lg:` classes of shared components are not edited. `sm` (640) splits phone and tablet; `lg` (1024) remains the only desktop boundary.
- Mobile-only presentation is opt-in through additive props that default to the old rendering: `AppSidebar variant="drawer"`, `SourcesColumn/NotesColumn mobile`, `SourceCard variant="list"`, `ContextIndicator variant="chip"`, `AppShell hideMobileTopBar`, `ChatPanel sessionTriggerContainer`.
- `AppShell` provides a small presentation context (`MobileNavContext`): open the drawer, and a top-bar node where the visible `ChatPanel` portals its session button — dialog state stays in `ChatPanel`, no global store.
- Height: `100dvh`, and below lg the shell follows `visualViewport` (`--vvh`, `--vv-top`) so the keyboard never covers the composer; `viewport-fit=cover` + `env(safe-area-inset-*)`.
- Source / insight detail render as a bottom sheet below lg by passing `MOBILE_SHEET_CLASSES` to the B2 `DialogContent`; the shared Dialog is not turned into a sheet.

## Alternatives considered
- JS breakpoint branches (`useIsDesktop`) for markup: first render is always "mobile" (SSR), causing a desktop flash and remounts.
- A separate Sheet primitive for source/insight: duplicates focus/escape handling the B2 dialog already has.

## Consequences
- A shared-component class that contains `size-` on an svg inside `Button` opts out of the button's `size-4` rule at every width — keep icon classes unchanged or use `h-/w-`.
- tailwind-merge collapses `break-*` utilities into one group; use arbitrary properties when a `max-lg:` word-break override is needed.
- The notebook page still mounts the hidden desktop `ChatColumn` below lg (pre-existing); M1 did not change request counts.
