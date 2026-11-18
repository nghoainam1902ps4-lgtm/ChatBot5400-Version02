#!/usr/bin/env bash
# ChatBot5400 offline update — pin (docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md).
# Phase 12D5: DEPLOY_IMAGE_TAG is the pin. `pin.sh` reports it against approved.json
# and the running container (read-only); `pin.sh --apply` re-points the tag to the
# approved image (idempotent repair); `--undo` is refused (use rollback.sh app).
# Thin wrapper: all logic (fail closed, locking, no network) is in offline_package.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
exec python3 "$HERE/offline_package.py" pin "$@"
