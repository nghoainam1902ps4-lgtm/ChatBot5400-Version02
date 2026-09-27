# ADR-010: One shared modal shell with size variants (B2)

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: "ChatBot 5400 — B2 Handoff: Login + Modal System" (approved, frozen 2026-09-27), ADR-009

## Context
About 35 `DialogContent`/`AlertDialogContent` usages each set their own width, max-height and scroll container (`sm:max-w-*`, `max-h-[90vh] overflow-y-auto`, `grid-rows-[…]`, `p-0` rebuilds). Footers were pushed off-screen on short viewports, and confirmation dialogs showed an X that let users dismiss a decision without making it.

## Decision
- `DialogContent` and `AlertDialogContent` take `size: 'sm' | 'md' | 'lg' | 'xl'` (420 / 560 / 760 / 1040 px max-width; default `md` for Dialog, `sm` for AlertDialog), `max-h-[88vh]`, and `calc(100% - 2rem)` below 640px. Consumers pick a size; they do not pass width classes.
- The shell is a flex column: `DialogHeader` (fixed, border-b, optional semantic `icon`/`iconTone`), `DialogBody` / `AlertDialogBody` (the only scroll region), `DialogFooter` (fixed, border-t, stacked primary-on-top below 640px). Forms wrap body + footer as `flex min-h-0 flex-1 flex-col`.
- `AlertDialog` never renders an X; `AlertDialogAction` takes `variant="destructive"` instead of raw colour classes.
- Presentation only: no handler, hook, API or validation changes.

## Alternatives considered
- Per-dialog fixes: already tried; every new dialog re-invented the scroll/footer bug.
- Converting confirmations to `Dialog`: loses AlertDialog focus/role semantics.

## Consequences
- New dialogs choose a size and use Body/Footer; a width class on `DialogContent` is a review smell.
- Dialogs with bespoke layouts (Source detail, Generate podcast, Session manager) still use the shell and size but keep their inner layout.
