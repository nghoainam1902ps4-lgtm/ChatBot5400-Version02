#!/usr/bin/env bash
# ChatBot5400 offline update — pin (docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md).
# Makes the new image survive a plain `docker compose up -d` in the deployment
# folder. Dry run by default; --apply needs the operator's decision; --undo reverts.
# Thin wrapper: all logic (fail closed, locking, no network) is in offline_package.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
exec python3 "$HERE/offline_package.py" pin "$@"
