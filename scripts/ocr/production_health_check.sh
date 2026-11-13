#!/usr/bin/env bash
# Read-only health snapshot of a ChatBot5400 deployment for the operator.
#
#   bash scripts/ocr/production_health_check.sh            # in the deployment directory
#   PROJECT_DIR=/path/to/deployment SINCE=1h bash scripts/ocr/production_health_check.sh
#
# Prints container state, restart counts, /health, memory, disk and a COUNT of
# warning / error lines in the application log. By design it never prints
# environment variables, secrets, log line contents or document names, and it
# changes nothing (no restart, no exec that writes, no network call other than
# the local /health endpoint).
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-$PWD}"
SINCE="${SINCE:-24h}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5055/health}"
cd "$PROJECT_DIR" || { echo "cannot enter $PROJECT_DIR"; exit 2; }

status=0
note() { printf '%-34s %s\n' "$1" "$2"; }
bad() { status=1; note "$1" "$2  <-- CHECK"; }

echo "== ChatBot5400 health snapshot $(date '+%F %T %Z')  (log window: $SINCE)"

ids=$(docker compose ps -q 2>/dev/null)
[ -n "$ids" ] || { echo "no containers for the compose project in $PROJECT_DIR"; exit 2; }
for id in $ids; do
  line=$(docker inspect "$id" --format \
    '{{index .Config.Labels "com.docker.compose.service"}}|{{.State.Status}}|{{.RestartCount}}|{{.State.StartedAt}}|{{.Config.Image}}')
  IFS='|' read -r service state restarts started image <<<"$line"
  msg="state=$state restarts=$restarts started=${started%%.*} image=$image"
  if [ "$state" = running ] && [ "$restarts" = 0 ]; then note "container $service" "$msg"; else bad "container $service" "$msg"; fi
done

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HEALTH_URL" 2>/dev/null)
if [ "$code" = 200 ]; then note "api /health" "200"; else bad "api /health" "${code:-no answer}"; fi

app=$(docker compose ps -q open_notebook 2>/dev/null)
if [ -n "$app" ]; then
  note "app memory / cpu" "$(docker stats --no-stream --format '{{.MemUsage}} ({{.MemPerc}}), cpu {{.CPUPerc}}' "$app" 2>/dev/null)"
  log=$(docker logs --since "$SINCE" "$app" 2>&1)
  count() { printf '%s\n' "$log" | grep -c -E "$1"; }
  errors=$(count ' \| ERROR ')
  note "log: ERROR lines" "$errors"
  note "log: WARNING lines" "$(count ' \| WARNING ')"
  note "log: documents converted (OCR)" "$(count 'Docling OCR finished')"
  note "log: partial conversions" "$(count 'part of the document may be missing')"
  note "log: orientation limited" "$(count 'OCR page orientation limited')"
  note "log: OCR model not available" "$(count 'is not available locally')"
  note "log: tracebacks" "$(count '^Traceback ')"
  left=$(docker exec "$app" sh -c 'ls -d /tmp/ocr-prep-* 2>/dev/null | wc -l' 2>/dev/null)
  note "leftover ocr-prep temp dirs" "${left:-unknown}"
  ocr=$(docker exec "$app" sh -c 'du -sh /app/data/ocr 2>/dev/null | cut -f1' 2>/dev/null)
  hf=$(docker exec "$app" sh -c 'du -sh /app/data/.cache/huggingface 2>/dev/null | cut -f1' 2>/dev/null)
  note "model storage" "ocr=${ocr:-none} huggingface=${hf:-none}"
fi

note "host memory" "$(free -h | awk '/^Mem:/ {print "total " $2 ", available " $7}')"
note "host disk ($PROJECT_DIR)" "$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $4 " free of " $2 " (" $5 " used)"}')"
note "host load" "$(cut -d' ' -f1-3 /proc/loadavg)"

[ "$status" = 0 ] && echo "RESULT: OK" || echo "RESULT: CHECK the lines marked above"
exit "$status"
