# Phase 12D11 · Local acceptance checklist

Use one final feature commit and image for all checks. Apply the existing 12D9 Local checklist with the stricter G-H1, G-04 and G-09 criteria below. Keep production isolated. Keep PDF content, OCR evidence and Agri weights on the acceptance machine.

| ID | Check | Required result |
|---|---|---|
| D11-W01 | Fresh and cached selected/native converters and worker processes, PDF text layer, RAPID/default, OCR disabled, controlled test URL | Version/source guard failures stop conversion; native retains and checks verdict after download; URL switch and redirects remain guarded |
| D11-W02 | 12D9 E2-G1 to G6 plus native partial/success-with-error and sync wait timeout | No partial text or new embeddings. Existing valid Source persists on reprocess failure. A late OCR result after sync failure cannot restore the deleted Source |
| D11-W03 | Isolated SurrealDB server, concurrent jobs, reprocess, insert rollback and stale job | Valid embedding sets survive failure. Only the matching version publishes. Validate worker against the actual server version |
| D11-W04 | G-H2 to G-H4 and repeated hyphen IDs, different widths and columns | Correct legal order, separators, literal footnotes, caption, reference deduplication and per-occurrence content |
| D11-W05 | G-H1 and G-04 in release mode, 22 PDFs per configured engine, synthetic controls first | Image/commit and model/config bound. Exit 0 only for all proved documents. Any unsupported or orientation difference stays NOT VERIFIED |
| D11-W06 | G-07a, G-07c/d, G-08a, G-09-TRUST/RB | PS 5.1/7 with and without uv, real publish interruption and persistent lock, trust, backup/restore and rollback with stable DB |
| D11-W07 | G-09 F1/F2 and after image swap | All eight content fingerprints present and equal under no writes. Run the eight F0 mutations and N0 with a real worker restart |
| D11-W08 | G-06 and remaining 12D9 Local tests | All required checks recorded against the same commit. Track E2-01/E2-02 as recognition evidence |
| D11-W09 | Signed RB-1 package, A/B/C preflight, both Compose modes, cold startup, rollback and Ubuntu VM reboot | Persistent payload and selector outside the checkout. Confirm original entrypoint, restore before worker, offline OCR 10/10 with RapidOCR, same DB identity and equal full snapshots. Record effective restart policy. RB-G1–G10 verified on the Local lab hook. RB-G11 pending |

For each Standard export from the 12D9 procedure pass `--commit` and `--image-id` obtained from the checkout and inspected image. On the baseline use `f2fdf2714a7c0b5b196132f71cfc091928befc06`. Compare the two directories with `--release --candidate-commit <feature SHA> --candidate-image <sha256:image ID>`. Use the JSON `hyphen_occurrence_status` on OCR documents; total TSV counts alone do not satisfy G-H1.

`READY FOR RELEASE = NO` and `READY FOR PRODUCTION = NO` until the Local gates reach the required result.
