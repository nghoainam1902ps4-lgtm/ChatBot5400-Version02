# Phase 12D11 · Offline safety

## D10-08 · Publish and recovery

RED: when both final checksum publication operations failed, the prepared hash was cleaned up while the new archive was already visible. Recovery could not pair the archive. The persistent PermissionError control captures this window, and the interrupted archive rename control exercises recovery of the prior pair.

`cmd_build` cleans staged and previous checksums only after checking the current pair. Recovery under the existing file lock only restores an already prepared checksum whose digest and filename match the archive. Unmatched or unavailable recovery material yields NOT READY. The archive hash remains a consistency check. Signature and trusted-channel requirements stay in the manual procedure.

The locked build claims the stage before examining recovery files, preserving the existing refusal when a stage directory already exists. That refusal leaves the existing stage and package intact. The 12D4 race control checks both the stage and lock cases.

## D10-09 · Data fingerprint

RED: updating a vector while retaining its ID passed `snapshot --no-writes`; the old query only selected ID and update time. The probe now hashes the actual returned rows of `source`, `notebook`, `note`, `source_insight` and `source_embedding`. The source link, chunk order, chunk body and vector all contribute. It checks the required table inventory in the live probe, processes large tables in ordered pages, and outputs only digests, record IDs, counts and update metadata. The local snapshot retains record IDs for loss detection. The process must run with writers stopped for F1/F2 and the image comparison.

Strict no-writes rejects missing content digests or malformed summaries. The manual F1/F2 gate checks each table's content digest and requires equality before proceeding. The RB-1 supplement adds relationship tables `reference` and `artifact` and includes `user`, for eight tables. LIVE subscription metadata and `command`/`recently_viewed` are runtime activity and outside the fingerprint. Credentials and provider settings are verified separately by the Local preservation procedure. Restore verification still uses a disposable backup copy.

G-07 and G-09 remain Local. They cover Windows locking and image publication, trusted archive validation, actual backup/restore, stable DB/container/volume identity, image pin and rollback. The automatic updater remains EXPERIMENTAL.

The [RB-1 integration report](PHASE12D11_RB1_INTEGRATION_REPORT.md) records the startup gate and verified Local RB-G10 rerun. RB-G11 remains pending.
