# ADR-015 · Source publication integrity

**Status:** accepted for Phase 12D11 remediation

The Source graph uses both Open Notebook's selected OCR converter and content-core's default converter. Because content-core 2.0.7 flattens its conversion result into text, Open Notebook installs a version- and source-guarded PDF callback at its local file handler. This preserves content-core's dispatch and configuration, and puts the same conversion acceptance check before serialization on both paths. Unsupported native PDF integrations fail closed.

A successful extraction may replace a Source's text before a new embedding job runs. To prevent old vectors from being used with new text, a changed-text write and retirement of the previous vectors share a SurrealDB transaction. Metadata-only saves omit unchanged text. The embedding job computes and validates vectors before its transaction and uses a Source revision write fence when replacing the existing set. This requires no schema migration or bulk embedding work.

Release evidence is verified separately from operational ingest. The strict diff gate accepts only evidence tied to its run, model, source coordinates and Markdown span. If the serializer or OCR evidence does not provide the needed provenance, the difference remains unverified.
