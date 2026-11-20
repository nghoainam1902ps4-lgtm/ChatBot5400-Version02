# Phase 12D11 · Targeted release blocker remediation

The implementation starts at `2cc824f66638d6db229993b4cc98948300e6bd8b`. The official v1.2.0 baseline is `f2fdf2714a7c0b5b196132f71cfc091928befc06`. The independent audit remains at `abbcc37c89f5c72f14bcd3aadd52c70817f36120` on `review/phase12d10-codex-targeted`. The four files were imported into the remediation worktree. On the implementation branch the 12D10 test removes its strict xfail markers and retains the assertions, inputs, and three passing controls.

Implementation and verification used Codex `gpt-6.2-sol` in Windows 11 25H2 (26200.9974) and Ubuntu WSL2. Backend verification used CPython 3.12.16, Tesseract 5.5.0 on generated fixtures and an isolated SurrealDB engine embedded via SDK 1.0.8. Frontend checks used Node.js 24.19.0 and npm 11.17.0 on Windows. Targeted Windows Python tests used CPython 3.12.14. Windows deployment, real Docker rollback and the isolated SurrealDB server rehearsal remain Local gates.

Scope is D10-01 through D10-09. VERSION stays 1.2.0. No schema migration, dependency change, model upgrade, bulk OCR, or embedding rebuild is part of this phase. PR #50 remains Draft. Automatic updating remains EXPERIMENTAL. E2-01 and E2-02 remain NEEDS LOCAL EVIDENCE.

| Finding | Original failure | Implementation | Verification and local gate |
|---|---|---|---|
| D10-01 | Native remote PDF continued after source hash mismatch | Guard the pinned content-core callback after download, before native conversion | 12D10 control, PDF integrity report, D11-W01 |
| D10-02 extraction | Native export discarded verdict before Source persistence | Shared outcome rejection before export, sync timeout fences late publication | Native worker controls and real OCR fault fixtures, D11-W02 |
| D10-02 embedding | Existing chunks deleted before provider completed | Generate first, guard revision, publish in one SurrealQL transaction | 12D10 concurrent failure control and embedded DB suite, D11-W03 |
| D10-03 | Vertical displacement fused cells across a gutter | Require a compatible line margin and nearby line geometry for closing a hyphen | 12D10 geometry control and 12D9 OCR/Legal regression, D11-W04 |
| D10-04 | Footnote bypassed Legal text serializer | Use same text serializer and preserve literal footnote syntax | 12D10 literal control and prior caption/footnote controls, D11-W04 |
| D10-05 | Universal-newline normalization and glob hid differences | Raw bytes, manifest inventory and conversion checks | 12D10 LF/CRLF and missing outputs controls, D11-W05 |
| D10-06 | Unbound orientation file and different weights could pass | Release mode binds both images/runs, evidence hashes, source cells and output spans | 12D10 model/orientation controls, bound gate tests, D11-W05 |
| D10-07 | Same substring counted twice | Diagnostic counts consume distinct spans, release requires source row identity | 12D10 duplicate-token control, bound occurrence tests, D11-W05 |
| D10-08 | Persistent rename failure discarded the staged hash | Keep prepared hashes until a verified pair exists, refuse unrecoverable pairs | 12D10 persistent error and interrupted publish controls, D11-W06 |
| D10-09 | Same-ID vector mutations missed by metadata fingerprints | Server-side canonical content digests, strict no-writes comparison | 12D10 vector control, eight F0 cases and N0, D11-W07 |

Reports: [PDF integrity](PHASE12D11_PDF_INTEGRITY_REPORT.md), [embedding](PHASE12D11_EMBEDDING_SAFETY_REPORT.md), [acceptance gate](PHASE12D11_ACCEPTANCE_GATE_REPORT.md), [offline safety](PHASE12D11_OFFLINE_SAFETY_REPORT.md), [regression](PHASE12D11_REGRESSION_REPORT.md), [Local checklist](PHASE12D11_LOCAL_ACCEPTANCE_CHECKLIST.md), [finding status](PHASE12D11_FINDING_STATUS.json).

The RB-1 supplement integrates the verified Local dictionary helper into the signed manual package and starts it before supervisord. RB-G10 passed on all 22 tables in the Windows lab. RB-G11 remains pending. [RB-1 integration report](PHASE12D11_RB1_INTEGRATION_REPORT.md)

Local acceptance and release are separate decisions. Production was untouched.
