#!/usr/bin/env bash
# ChatBot5400 offline update — snapshot (docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md).
# READ-ONLY record of the database container, the records (counts + digests), the
# deployment image tag and the model files: snapshot.sh [--out before.json]
# [--compare before.json] (exit 0 nothing lost, 5 lost / changed, 3 unreadable).
# Thin wrapper: all logic (fail closed, no network) is in offline_package.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
exec python3 "$HERE/offline_package.py" snapshot "$@"
