# Phase 12D11 · PDF integrity

## D10-01 and D10-02

Both API ingestion modes use the source command and source graph. The async API queues it. The sync API submits it and waits up to 300 seconds. The command resolves uploaded paths and the graph retains the deployment URL switch, URL validation and content-core routing. Default OCR, OCR disabled, and native PDF text-layer extraction keep content-core's default PDF options. Selected OCR still uses Open Notebook's converter and PDF preparation.

```text
sync/async API -> process_source -> content_process
  selected OCR -> build_converter -> convert_document -> reject_incomplete -> serialize
  native -> content-core MIME/routing (download for URL)
         -> guarded PDF callback -> native converter -> reject_incomplete -> serialize
  accepted output -> save_source -> existing optional embedding enqueue
```

RED was the native callback’s immediate call to `result.document.export_to_markdown()`. It discarded status and errors. URL ingestion had only requested optional patching, before content-core downloaded the file. Three controls reproduce the bypass, including a normal-looking result with a nonempty body.

The native callback is installed under a lock and checks content-core 2.0.7 and SHA-256 of the dispatch and extraction functions. The PDF branch inspects the downloaded file header, applies required text patches and keeps `ConversionResult` until acceptance. The selected OCR branch uses the same `reject_incomplete` policy. Both refuse missing status, PARTIAL_SUCCESS, SUCCESS with errors, exhausted Tesseract errors and empty exported text. An image placeholder or an HTML/JSON wrapper alone is insufficient. A successful empty OCR crop is allowed when the rest of the document is valid. Configured-language OSD failure still proceeds to recognition. Production URL ingestion configuration is unchanged.

Initialization is per process. Text patches and the Tesseract-specific patches have separate guards. Selected Tesseract initializes both before conversion. Native Auto does not instantiate the Tesseract CLI model. Cached Docling instances use the guarded class methods when called. No claim of one atomic swap of all seven functions is made.

An OCR thread can finish after cancellation. Its work is conversion only. If the sync wait times out or the API task is cancelled, the API deletes the new Source before leaving the request. Transactional Source publication checks that the record still exists. A DB or process outage during cancellation still requires the Local worker/deadline rehearsal. The recognition stderr limit remains 4096 bytes **for classification**. PIPE capture can still buffer more.

## D10-03 and D10-04

Page assembly closes an ending hyphen only when the adjacent cells are compatible with the same source line or the next line begins near the previous line's margin within a plausible line pitch. The margin comes from contiguous cells in the preceding line. Ambiguous boxes leave a space. The D8-01 reading-order controls pass.

The Markdown wrapper writes a resolved, nonempty note through the active text serializer. In Legal, heading and quote syntax and literal footnote markup are escaped for display. Markdown encoding can add escapes to stored text. The underlying printed characters and existing coverage for caption, holder and reference deduplication are retained. Known non-PDF/non-image origin types use upstream floating serializers. HTML remains outside the change.

Verification: the 12D10 controls cover native upload outcomes, the remote callback and both text fixes. The 12D11 tests add native Source persistence/queue checks, sync wait cleanup and non-PDF serialization. D11-W01, W02 and W04 cover Windows deployment and actual PDF geometry.
