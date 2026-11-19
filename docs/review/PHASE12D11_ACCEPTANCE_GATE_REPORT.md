# Phase 12D11 · Standard expected-diff and occurrence evidence

**D10-05 RED:** LF/CRLF and a manifest success missing from both compared directories returned zero. The gate now compares bytes, validates both manifest inventories and refuses missing, extra, duplicate, failed and hash-mismatched artifacts.

**D10-06 RED:** differing model hashes and a free-standing orientation record returned zero. Release comparison requires `--release` with expected candidate commit and image ID. It checks the official baseline, run IDs, document/engine/model/config parity and an inventory of hashed evidence from the candidate export. Records must name the same document and run. TSV evidence must name its invocation, page, crop and actual model files. An image-labelled export requires release mode. Legacy diagnostics remain available for the older audit fixtures.

The release comparator reconstructs baseline bytes from candidate serializer offsets and exact source elements. It consumes each source span once and checks TSV row identities, crop containment and output position. The unchanged text between the proven spans must also match the baseline. A span can contain TSV and hyphen fixes together. Attached footnote evidence uses the exact floating item serialization and its appended notes. An unsupported difference, including an orientation difference without an attested producer, stays NOT VERIFIED.

**D10-07 RED:** two raw OCR appearances of a token reused one Markdown substring. The diagnostic count now consumes distinct output positions. It is informational. Release G-H1 requires a separate row identity and ordered Markdown span per OCR occurrence. A missing, swapped or unbound occurrence fails certification. A text layer with no OCR invocations has no Tesseract occurrence verdict. Table/cross-layout/merge differences for which exact provenance cannot be reconstructed do not receive an automatic pass.

Exit codes retain 0 for a proved strict comparison, 1 for unexpected differences, 2 for unverified evidence and 3 for an invalid run. Evidence hashes bind artifacts to a run to detect accidental mixing. They carry no signature or publisher trust.

D11-W05 runs the strict path on the actual Windows exports. It records per-document reason and status without printing document text.
