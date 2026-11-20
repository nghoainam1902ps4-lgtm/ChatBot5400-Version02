#!/bin/sh
# Return the persistent Compose override only while the deployment tag is pinned to v1.2.0.
#
# Output contract (Phase 12D13): exit 0 with the override path while the tag
# points to the approved baseline image; exit 0 with NO output while it points
# to another image; any unreadable or malformed metadata (a pin that is not
# exactly one strict LF-terminated line, CRLF, wrong case, truncated ID), a
# Docker error or a missing override exits non-zero. A caller that selected
# the baseline tag must also require the output to be "$RB1_STATE/compose.json"
# (an empty or replaced selector would otherwise read as "no override"), and
# must run verify_stage.py first (staged bytes = signed bytes).
set -eu
export LC_ALL=C
root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

# pin <file> <extended regex>: the file holds exactly one line "<value>\n"
pin() {
    file="$root/$1"
    [ -f "$file" ] && [ ! -L "$file" ] || exit 3
    value=$(cat "$file")
    [ "$(wc -c < "$file")" -eq $((${#value} + 1)) ] || exit 3
    [ "$(printf '%s\n' "$value" | wc -l)" -eq 1 ] || exit 3
    printf '%s\n' "$value" | grep -Eqx "$2" || exit 3
    printf '%s' "$value"
}

baseline=$(pin baseline-image 'sha256:[0-9a-f]{64}')
tag=$(pin deploy-tag '[a-z0-9]+([._-]+[a-z0-9]+)*(:[0-9]{1,5})?(/[a-z0-9]+([._-]+[a-z0-9]+)*)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}')
actual=$(docker image inspect --format '{{.Id}}' -- "$tag")
printf '%s\n' "$actual" | grep -Eqx 'sha256:[0-9a-f]{64}' || exit 3
if [ "$actual" = "$baseline" ]; then
    [ -f "$root/compose.json" ] && [ ! -L "$root/compose.json" ] || exit 3
    printf '%s\n' "$root/compose.json"
fi
