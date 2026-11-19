#!/bin/sh
# Return the persistent Compose override only while the deployment tag is pinned to v1.2.0.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
read -r baseline < "$root/baseline-image"
read -r tag < "$root/deploy-tag"
actual=$(docker image inspect --format '{{.Id}}' "$tag")
[ -n "$actual" ] && [ -n "$baseline" ] || exit 3
if [ "$actual" = "$baseline" ]; then
    [ -f "$root/compose.json" ] || exit 3
    printf '%s\n' "$root/compose.json"
fi
