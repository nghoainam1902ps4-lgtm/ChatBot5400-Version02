#!/usr/bin/env bash
# ChatBot5400 Phase 12 - isolated test stack helper for WSL2 / Linux
# (same actions as scripts/windows/phase12-test.ps1;
#  docs/ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md).
#
# Safety: never `down -v`, never deletes a folder, only the compose project
# "chatbot5400-phase12-test", loopback ports, secrets never printed.
#
#   scripts/ocr/phase12-test.sh check | init-env | build | up | status | logs
#   scripts/ocr/phase12-test.sh import-agri /path/vie_agri.traineddata v2
#   scripts/ocr/phase12-test.sh activate-agri v2
#   scripts/ocr/phase12-test.sh fixtures
#   scripts/ocr/phase12-test.sh compare <name-in-import> [engine] [--full-page]
#   scripts/ocr/phase12-test.sh diagnose <name-in-import> [engine] [--full-page]
#   scripts/ocr/phase12-test.sh legal-gate on|off
#   scripts/ocr/phase12-test.sh stop
set -euo pipefail

PROJECT=chatbot5400-phase12-test
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK="$ROOT/deploy/phase12-test"
ENV_FILE="$STACK/.env"
PY=/app/.venv/bin/python

say() { printf '[phase12] %s\n' "$*"; }
die() { printf '[phase12] ERROR: %s\n' "$*" >&2; exit 1; }
compose() { (cd "$STACK" && docker compose -p "$PROJECT" -f docker-compose.yml "$@"); }
app() { compose exec -T open_notebook "$@"; }
env_value() { [ -f "$ENV_FILE" ] && grep -E "^\s*$1\s*=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
secret() { python3 -c "import secrets; print(secrets.token_urlsafe(${1:-32}))"; }

check() {
  command -v docker >/dev/null || die "docker not found"
  [ "$(docker info --format '{{.OSType}}' 2>/dev/null)" = "linux" ] || die "Docker (Linux containers) is not running"
  docker compose version >/dev/null || die "docker compose v2 is required"
  say "Git: $(git -C "$ROOT" rev-parse --abbrev-ref HEAD) @ $(git -C "$ROOT" rev-parse --short HEAD)"
  local web api
  web="$(env_value PHASE12_WEB_PORT)"; web="${web:-8504}"
  api="$(env_value PHASE12_API_PORT)"; api="${api:-5057}"
  if [ -z "$(compose ps -q 2>/dev/null || true)" ]; then
    for p in "$web" "$api"; do
      if (command -v ss >/dev/null && ss -ltn | grep -q ":$p ") ; then die "port $p already in use"; fi
    done
  fi
  df -h "$ROOT" | tail -1 | awk '{print "[phase12] free disk: " $4 " (the image needs about 15 GB)"}'
  [ -f "$ENV_FILE" ] || say 'no .env yet: run "init-env"'
  say "project=$PROJECT web=127.0.0.1:$web api=127.0.0.1:$api data=$STACK"
}

init_env() {
  if [ -f "$ENV_FILE" ]; then say ".env exists: unchanged"; return; fi
  umask 077
  sed -e "s|^SURREAL_PASSWORD=$|SURREAL_PASSWORD=$(secret 24)|" \
      -e "s|^OPEN_NOTEBOOK_ENCRYPTION_KEY=$|OPEN_NOTEBOOK_ENCRYPTION_KEY=$(secret)|" \
      -e "s|^OPEN_NOTEBOOK_JWT_SECRET=$|OPEN_NOTEBOOK_JWT_SECRET=$(secret)|" \
      "$STACK/.env.example" > "$ENV_FILE"
  mkdir -p "$STACK/import" "$STACK/diagnostics" "$STACK/fonts"
  say ".env created with new random secrets (not displayed)"
}

safe_name() {
  case "$1" in /*|*..*) die "give a name inside deploy/phase12-test/import" ;; esac
}

action="${1:-}"; shift || true
case "$action" in
  check) check ;;
  init-env) init_env ;;
  build) check; compose build open_notebook ;;
  up) check; [ -f "$ENV_FILE" ] || die 'run "init-env" first'; compose up -d
      say "web http://127.0.0.1:$(env_value PHASE12_WEB_PORT)  api http://127.0.0.1:$(env_value PHASE12_API_PORT)/docs" ;;
  status) compose ps; app "$PY" -m open_notebook.ocr.cli status ;;
  logs) compose logs --tail 200 open_notebook ;;
  import-agri)
    model="${1:?model path}"; version="${2:-v1}"
    [ -f "$model" ] || die "no such file: $model"
    say "SHA-256 on this machine: $(sha256sum "$model" | cut -d' ' -f1)"
    mkdir -p "$STACK/import"; cp "$model" "$STACK/import/vie_agri.traineddata"
    app "$PY" -m open_notebook.ocr.cli custom import --file /import/vie_agri.traineddata --version "$version" --notes "Phase 12 local"
    say "compare the stored sha256 above, then: $0 activate-agri $version" ;;
  activate-agri) app "$PY" -m open_notebook.ocr.cli custom activate --version "${1:?version}"; app "$PY" -m open_notebook.ocr.cli custom status ;;
  agri-status) app "$PY" -m open_notebook.ocr.cli custom status ;;
  fixtures) app "$PY" scripts/ocr/generate_phase12_fixtures.py --out /phase12-out/fixtures --font-dir /fonts ;;
  compare|diagnose)
    name="${1:?name inside the import folder}"; safe_name "$name"
    engine="${2:-tesseract_agri}"; shift 2 || shift || true
    stamp="$(date +%Y%m%d-%H%M%S)"
    app "$PY" "scripts/ocr/phase12_${action}.py" "/import/$name" --engine "$engine" --out "/phase12-out/$action-$stamp" "$@"
    say "results (document text, keep local): $STACK/diagnostics/$action-$stamp" ;;
  legal-gate)
    state="${1:?on|off}"; value=false; [ "$state" = on ] && value=true
    [ -f "$ENV_FILE" ] || die 'run "init-env" first'
    tmp="$(mktemp)"; grep -vE '^\s*OCR_LEGAL_NORMALIZATION_ENABLED\s*=' "$ENV_FILE" > "$tmp" || true
    echo "OCR_LEGAL_NORMALIZATION_ENABLED=$value" >> "$tmp"; cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
    say "gate=$value; recreating ONLY the application container"
    compose up -d --no-deps --no-build --force-recreate open_notebook ;;
  restart-app) compose up -d --no-deps --no-build --force-recreate open_notebook ;;
  stop) compose stop; say "stopped; data kept" ;;
  *) sed -n '2,16p' "$0"; exit 2 ;;
esac
