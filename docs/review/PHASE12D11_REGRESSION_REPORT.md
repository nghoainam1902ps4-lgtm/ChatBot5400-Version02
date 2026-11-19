# Phase 12D11 · Regression results

The independent RED run was on a clean `2cc824f` snapshot with the audit test imported unchanged. `python -m pytest tests/test_phase12d10_review_controls.py --runxfail -q --tb=short -p no:cacheprovider` returned **13 failed, 3 passed** in 5.01 s. Failures reproduce the nine finding groups. The transcript is in `~/cb5400-d11.uxsCxh8k/red.log` under Ubuntu WSL.

GREEN runs used normal pytest. All **16 independent controls** passed on WSL and native Windows. The remediation copy removes only the xfail decorators. The independent review commit retains the original file and strict markers.

| Suite | Environment and result |
|---|---|
| Full backend before RB-1 integration | **3511 passed, 10 failed, 69 skipped**, zero xfails. The 10 failures match the 12D9 baseline by name. Scope is supplemented by the RB-1 offline regression. |
| 12D2 / 12D4 audits | **32 passed / 139 passed** respectively. |
| 12D8 audit | 274 passed in unprivileged WSL. The remaining isolated test passed when run separately under WSL root. Total **275 passed**, no xfails. |
| 12D9 tests | **126 passed** across crop quality, conversion failure safety, Standard expected-diff and text preservation. |
| OCR, text preservation and AST parity | **98 passed** with Tesseract 5.5.0 including real OCR, source ordering and literal/caption fixtures. The OCR fixtures use a deterministic test layout. |
| Final Standard identity and 12D10 controls | **51 passed** after adding the bound engine/artifact checks, including the synthetic PDF through Tesseract and Docling with strict release mode. |
| Source publication and deletion | **67 passed** across the Phase 12D10 controls, embedded SurrealDB writes and domain tests. One known settings-default failure was deselected here and remains in the full result. |
| Final PDF integrity and format follow-up | **110 passed**, including the native worker, the three empty-document serialization controls, the explicitly patched non-PDF control, and Docling and Legal parity. |
| Build lock and offline/transaction follow-up | **41 passed** with the 12D4 build audit, persistent rename control, 12D10 controls, embedded fingerprints and embedding tests. |
| RB-1 integration and offline regression | **458 passed, 1 skipped**. Covers the signed package, preflight decisions, startup order and restore, 12D2/12D4, and 12D8 offline tests. The skip is the root-only test verified separately. |
| Final D10-09 supplement | **8/8** original F0 mutations detected. N0 **PASS** with real embedded SurrealDB LIVE metadata changes and equal schema and business digests. |
| Native Windows targeted backend | **25 passed, 1 skipped**. The Windows test interpreter did not have the rendered OCR fixture's system tools. Its WSL counterpart passed. |
| Offline tokenizer and 12D4 reaudit | **53 passed** using the SHA-verified `o200k_base` cache. |
| Approval and embedding transaction follow-up | **75 passed**. Real embedded `reference` link creation and deletion are exercised alongside the stale embedding job. |
| Frontend on Windows | **438 passed** in 64 files. `tsc --noEmit` and `npm run build` passed. ESLint returned zero errors and seven existing warnings. |
| Backend lint | Ruff passed for changed Python files. Repository-wide Ruff reported `I001` in `tests/test_auth.py:3` and `F811` in `tests/test_url_ingestion_switch.py:279`, both outside the remediation diff. |

The 12D8 scripts still assert outcomes for the previously failing scenarios. For example the geometry fixtures compare legal identifiers and ordering, the diff controls assert rejection codes, and the offline controls check surviving artifacts and no-writes failures. The 12D8 manual F1/F2 fixture gained valid per-table digests to exercise the new input contract. Its acceptance assertions are unchanged.

The SurrealDB cases use the real embedded engine and the application migrations with synthetic records. They exercise rollback and vector-content fingerprinting. Offline package fault injection uses fake Docker commands. The actual Windows Docker image, standalone SurrealDB worker integration and Local corpus remain in the Local checklist. No changes were made to Windows ACLs or the deployment environment.

The ten baseline failures are `tests/test_domain.py::TestContentSettings::test_content_settings_defaults`
and these `tests/test_models_api.py::TestModelsProviderAvailability` cases: `test_blank_anthropic_compatible_env_vars_are_unavailable`, `test_generic_env_var_enables_all_modes`, `test_individual_mode_embedding_only`, `test_individual_mode_llm_only`, `test_individual_mode_stt_only`, `test_individual_mode_tts_only`, `test_mixed_config_generic_and_mode_specific`, `test_mode_specific_env_vars_llm_embedding`, and `test_no_env_vars_set`. The 12D9 count was 3461 passed, 10 failed, 67 skipped. The current environment additionally skipped the isolated root-only case (verified separately) and one Tesseract runtime/model readiness case.
