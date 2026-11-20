# Phase 12D11 · Embedding publication

**D10-02 RED:** `embed_source_command` deleted vectors before invoking the provider. In the independent control a previously started embedding job and a failed OCR reprocess left the Source contents present and the vectors missing.

**Implementation:** `commands/embedding_commands.py` loads the Source, captures its content and revision, chunks it, obtains all vectors, and validates count, dimension, numeric type and finiteness. `repo_transaction` sends a single SurrealQL transaction and checks the raw response for errors across statements. A Source revision check and update fence the delete/insert against concurrent publication, edits and deletion. Timestamp comparison uses the microsecond resolution the Python SDK returns. The provider call is outside the transaction.

A successful OCR reprocess can publish different text. `repo_update` publishes the changed text and retires previous vectors in the same transaction. The existing enqueue policy can then populate fresh vectors. RAG sees the previous text with its vectors, or the new text without stale vectors. A metadata-only save omits unchanged text from its MERGE so it cannot republish a stale text snapshot. The failed OCR route never reaches text publication.

The embedded SurrealDB tests run the application migrations and check provider failure, invalid output, cancellation, an insert constraint failure and rollback, revision changes, source deletion, a late job and two separate sources. D11-W03 repeats this on the isolated SurrealDB server and real worker used for Windows acceptance.

Source deletion and notebook unlinking now share a database transaction. The existing `source_delete` event clears the vectors and insights in that transaction. File cleanup follows the commit. This also fences publication from a sync request whose Source has been removed.
