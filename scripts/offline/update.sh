#!/usr/bin/env bash
# ChatBot5400 offline update — update (docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md).
# EXPERIMENTAL - not the production path: production is updated with
# docs/deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md (the tool prints this on every run).
# Thin wrapper: all logic (fail closed, locking, no network) is in offline_package.py.
# Needs only python3 (standard library), docker with the compose plugin, git, ssh-keygen.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
exec python3 "$HERE/offline_package.py" update "$@"
