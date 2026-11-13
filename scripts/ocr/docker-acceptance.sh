#!/usr/bin/env bash
# Docker acceptance for the OCR Engine Manager — ONLINE PREPARATION / OFFLINE
# OPERATION model (docs/ocr/OCR_ONLINE_PREPARATION.md, OCR_LOCAL_ACCEPTANCE.md).
#
# SAFE BY DESIGN
#   * Own compose project + own temporary directory (bind mounts): never touches an
#     existing deployment, its volumes or its database. Never `down -v`.
#   * "Offline" = the RUNNING app container is disconnected from the egress network
#     (no recreate). App and SurrealDB share an `internal: true` network, so the DB
#     stays reachable while the Internet is not (both are verified).
#
# FLOW (each step prints PASS / FAIL / NOT VERIFIED; summary + exit code at the end)
#   0. [OLD_REF] previous version: start, store settings marker + marker notebook
#   1. ONLINE UPDATE to the image under test: DB/API/worker ready, Docling on,
#      locked dependency versions, no OCR model downloaded at startup, old data kept
#   2. ONLINE PREPARATION per engine in $SCENARIOS (rapidocr tesseract_fast
#      tesseract_best easyocr): install model -> prepare (Docling Heron/TableFormer +
#      RapidOCR weights) -> readiness offline_ready -> E2E through API + worker
#      (activate, test, upload PDF, source processed, expected text, engine in log);
#      a second prepare re-uses models (checksums unchanged)
#   3. OFFLINE OPERATION (same container): Internet blocked, DB reachable; for EVERY
#      prepared engine: readiness check with offline_verified, E2E processing;
#      model + HF cache unchanged, no download attempt in logs
#   4. RESTART while offline (same container, still offline): runtimes/models
#      present, every prepared engine processes documents again
#   5. ONLINE UPDATE: reconnect, rebuild the image for real (new image id), recreate,
#      data + settings kept, models reused (checksums), prepare again (downloads only
#      what is missing), readiness offline_ready; then OFFLINE again and process
#
# USAGE   bash scripts/ocr/docker-acceptance.sh
# ENV     SCENARIOS="tesseract_best easyocr"   (any of rapidocr tesseract_fast tesseract_best easyocr)
#         OLD_REF=<git ref of the deployed version>   (empty = skip step 0)
#         SKIP_BUILD=1  KEEP_WORK=1  UV_TORCH_BACKEND=cpu (default)
set -uo pipefail

REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SCENARIOS="${SCENARIOS:-tesseract_best easyocr}"
OLD_REF="${OLD_REF:-}"
IMAGE="${IMAGE:-chatbot5400:ocr-accept}"
OLD_IMAGE="${IMAGE}-old"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ocr-accept.XXXXXX")"
PROJECT="ocraccept$$"
FIXTURE="$REPO/tests/fixtures/ocr/vb_scan.pdf"
DB_PASS="accept-$(date +%s)-$$"
RESULTS="$WORK/results.txt"
: > "$RESULTS"
PREPARED=""

log() { printf '\n=== %s\n' "$*"; }
record() { printf '%-14s %s\n' "$1" "$2" | tee -a "$RESULTS"; }
pass() { record "PASS" "$*"; }
fail() { record "FAIL" "$*"; }
nv() { record "NOT VERIFIED" "$*"; }

expects_for() {  # expected text per engine (RapidOCR's default model has no Vietnamese diacritics)
  if [ "$1" = rapidocr ]; then
    printf '%s\n' "1234/2024" "1.250.000.000"
  else
    printf '%s\n' "1234/2024/QĐ-MẪU" "Hạn mức thử nghiệm là 1.250.000.000 đồng"
  fi
}
class_for() {
  case "$1" in easyocr) echo EasyOcrModel ;; rapidocr) echo RapidOcrModel ;; *) echo TesseractOcrCliModel ;; esac
}

cat > "$WORK/compose.yml" <<EOF
networks:
  backend:
    internal: true        # DB traffic only, no route to the Internet
  egress: {}              # Internet; disconnected from the running app for offline steps
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: ["start", "--user", "root", "--pass", "${DB_PASS}", "rocksdb:/mydata/db"]
    user: root
    volumes: ["./surreal_data:/mydata"]
    networks: [backend]
  app:
    image: \${APP_IMAGE}
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=ocr-acceptance-only-${DB_PASS}
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - SURREAL_USER=root
      - SURREAL_PASSWORD=${DB_PASS}
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
      - OPEN_NOTEBOOK_ENABLE_DOCLING=true
      - UV_TORCH_BACKEND=\${UV_TORCH_BACKEND:-cpu}
      - OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true
      - OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true
      - OCR_RAPIDOCR_PERSISTENT=\${OCR_RAPIDOCR_PERSISTENT:-false}
      - OPEN_NOTEBOOK_WORKER_MAX_TASKS=1
    volumes: ["./data:/app/data"]
    networks: [backend, egress]
    depends_on: [surrealdb]
EOF
mkdir -p "$WORK/data" "$WORK/surreal_data"

dc() { docker compose -p "$PROJECT" -f "$WORK/compose.yml" "$@"; }
app_id() { dc ps -q app; }
EGRESS="${PROJECT}_egress"
go_offline() { docker network disconnect "$EGRESS" "$(app_id)" >/dev/null 2>&1; }
go_online() { docker network connect "$EGRESS" "$(app_id)" >/dev/null 2>&1; }
api() {
  local id; id="$(app_id)"
  docker cp "$REPO/scripts/ocr/acceptance_api.py" "$id:/tmp/acceptance_api.py" >/dev/null
  docker cp "$FIXTURE" "$id:/tmp/vb_scan.pdf" >/dev/null
  docker exec "$id" /app/.venv/bin/python /tmp/acceptance_api.py "$@"
}
e2e() {  # $1 engine
  local args=() line
  while IFS= read -r line; do args+=(--expect "$line"); done < <(expects_for "$1")
  api ocr-e2e --engine "$1" --pdf /tmp/vb_scan.pdf "${args[@]}"
}
internet_blocked() {
  ! docker exec "$(app_id)" /app/.venv/bin/python -c "import urllib.request;urllib.request.urlopen('https://pypi.org/simple/',timeout=10)" >/dev/null 2>&1
}
model_sums() { (cd "$WORK/data/ocr/models" 2>/dev/null && find . -type f \( -name '*.traineddata' -o -name '*.pth' -o -name '*.onnx' \) -exec sha256sum {} + | sort) || true; }
hf_state() { find "$WORK/data/.cache/huggingface" -type f -printf '%s %P\n' 2>/dev/null | sort | sha256sum | cut -c1-16; }
wait_ready() {  # $1 timeout, $2 optional --no-ocr
  if api --timeout "$1" wait-ready ${2:-} >"$WORK/ready.json"; then return 0; fi
  cat "$WORK/ready.json"; return 1
}
cleanup() {
  dc down --remove-orphans >/dev/null 2>&1 || true
  echo; echo "================ SUMMARY ================"; cat "$RESULTS"
  if [ "${KEEP_WORK:-0}" = "1" ]; then
    echo "work dir kept: $WORK"
  else
    docker run --rm -v "$WORK:/w" --entrypoint sh "$IMAGE" -c 'rm -rf /w/data /w/surreal_data' >/dev/null 2>&1 || true
    rm -rf "$WORK" 2>/dev/null || echo "work dir left at: $WORK"
  fi
}
trap cleanup EXIT

# --- build ---------------------------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  log "Build image under test ($IMAGE), Tesseract build profile"
  docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t "$IMAGE" "$REPO" || { fail "docker build"; exit 1; }
fi
if [ -n "$OLD_REF" ]; then
  log "Build the deployed version ($OLD_REF)"
  OLD_OK=0
  git -C "$REPO" worktree add --detach "$WORK/old-src" "$OLD_REF" >/dev/null &&
    docker build --target runtime -t "$OLD_IMAGE" "$WORK/old-src" && OLD_OK=1
  git -C "$REPO" worktree remove --force "$WORK/old-src" >/dev/null 2>&1 || true
  [ "$OLD_OK" = 1 ] || { fail "build of OLD_REF=$OLD_REF"; OLD_REF=""; }
fi

# --- 0. previous version ----------------------------------------------------------------
if [ -n "$OLD_REF" ]; then
  log "0. Previous version $OLD_REF"
  APP_IMAGE="$OLD_IMAGE" dc up -d >/dev/null
  if wait_ready 3600 --no-ocr && api settings-set >/dev/null && api seed-data >/dev/null; then
    pass "old version running; settings marker + marker notebook stored"
  else
    fail "old version start/seed"
  fi
fi

# --- 1. online update -----------------------------------------------------------------------
log "1. ONLINE: start the image under test (first boot installs Docling with lock constraints)"
APP_IMAGE="$IMAGE" dc up -d --force-recreate >/dev/null
if wait_ready 3600; then pass "DB + API + worker ready, admin login, OCR API"; else fail "stack not ready"; exit 1; fi
grep -q '"docling_available": true' "$WORK/ready.json" && pass "Docling runtime enabled" || fail "Docling runtime missing"
grep -q '"dependency_problems": \[\]' "$WORK/ready.json" && pass "content-core/Docling = verified versions" || fail "dependency problems: $(cat "$WORK/ready.json")"
[ -z "$(model_sums)" ] && pass "no OCR model downloaded at startup" || fail "OCR models present after startup"
if [ -n "$OLD_REF" ]; then
  api settings-check >/dev/null && pass "settings from $OLD_REF kept" || fail "settings lost"
  api check-data >/dev/null && pass "data (marker notebook) from $OLD_REF kept" || fail "data lost"
fi

# --- 2. online preparation ------------------------------------------------------------------
for E in $SCENARIOS; do
  log "2. ONLINE PREPARATION: $E"
  out="$(api prepare --engine "$E")"; rc=$?; echo "$out"
  case $rc in
    0) pass "$E: prepared, readiness offline_ready (network-blocked pipeline check)";;
    2) nv "$E: $out"; continue;;
    *) fail "$E: prepare: $out"; continue;;
  esac
  out="$(e2e "$E")"; rc=$?; echo "$out"
  if [ $rc -eq 0 ]; then pass "$E: online E2E (activate/test/upload/process)"; else fail "$E: online E2E: $out"; continue; fi
  docker logs "$(app_id)" 2>&1 | grep -q "Docling OCR finished: engine=$E actual_models=\['$(class_for "$E")'\]" &&
    pass "$E: worker log shows $(class_for "$E")" || fail "$E: engine not confirmed in worker log"
  before="$(model_sums)"
  api prepare --engine "$E" >/dev/null && [ "$(model_sums)" = "$before" ] &&
    pass "$E: second prepare re-used models (checksums unchanged)" || fail "$E: models changed on re-prepare"
  PREPARED="$PREPARED $E"
done
[ -n "$PREPARED" ] || { fail "no engine prepared; offline steps skipped"; exit 1; }
api settings-set --with-ocr >/dev/null && pass "settings marker incl. OCR config stored" || fail "settings-set"
LAST="${PREPARED##* }"
SUMS="$(model_sums)"; HF="$(hf_state)"

# --- 3. offline operation ---------------------------------------------------------------------
offline_round() {  # $1 label
  local E out rc since
  since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  internet_blocked && pass "$1: Internet unreachable from the app" || fail "$1: Internet still reachable (test invalid)"
  wait_ready 900 && pass "$1: DB + API + worker reachable" || { fail "$1: stack not reachable"; return; }
  for E in $PREPARED; do
    out="$(api readiness-check --engine "$E" --require-offline)"; rc=$?
    [ $rc -eq 0 ] && pass "$1: $E readiness offline_verified" || fail "$1: $E readiness: $out"
    out="$(e2e "$E")"; rc=$?
    [ $rc -eq 0 ] && pass "$1: $E processed a PDF (Heron/TableFormer + OCR)" || fail "$1: $E processing: $out"
  done
  [ "$(model_sums)" = "$SUMS" ] && pass "$1: OCR model checksums unchanged" || fail "$1: OCR models changed"
  [ "$(hf_state)" = "$HF" ] && pass "$1: Hugging Face cache unchanged" || fail "$1: HF cache changed"
  if docker logs --since "$since" "$(app_id)" 2>&1 | grep -E -i "Initiating download|Downloading https|huggingface.co/api|modelscope.cn" >/dev/null; then
    fail "$1: download attempt found in logs"
  else
    pass "$1: no download attempt in logs"
  fi
}
log "3. OFFLINE OPERATION (same container)"
go_offline
offline_round "offline"

# --- 4. restart while offline -------------------------------------------------------------------
log "4. RESTART while offline (same container, no recreate)"
dc restart app >/dev/null
offline_round "offline-restart"
api settings-check --with-ocr --engine "$LAST" >/dev/null && pass "offline-restart: settings + active engine kept" || fail "offline-restart: settings lost"

# --- 5. online update, then offline again ---------------------------------------------------------
log "5. ONLINE UPDATE: reconnect, rebuild for real, recreate, re-prepare"
go_online
OLD_ID="$(docker image inspect -f '{{.Id}}' "$IMAGE")"
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true --no-cache-filter runtime-base,runtime -t "$IMAGE" "$REPO" >/dev/null || fail "rebuild"
NEW_ID="$(docker image inspect -f '{{.Id}}' "$IMAGE")"
[ "$OLD_ID" != "$NEW_ID" ] && pass "rebuild produced a new image" || fail "rebuild reused the same image id"
APP_IMAGE="$IMAGE" dc up -d --force-recreate app >/dev/null
[ "$(docker inspect -f '{{.Image}}' "$(app_id)")" = "$NEW_ID" ] && pass "container recreated from the rebuilt image" || fail "container not on rebuilt image"
if wait_ready 3600; then
  api settings-check --with-ocr --engine "$LAST" >/dev/null && pass "update: settings + active engine kept" || fail "update: settings lost"
  [ -z "$OLD_REF" ] || { api check-data >/dev/null && pass "update: data kept" || fail "update: data lost"; }
  [ "$(model_sums)" = "$SUMS" ] && pass "update: OCR models reused (checksums unchanged)" || fail "update: OCR models changed"
  for E in $PREPARED; do
    out="$(api prepare --engine "$E")" && pass "update: $E re-prepared (offline_ready)" || fail "update: $E prepare: $out"
  done
  SUMS="$(model_sums)"; HF="$(hf_state)"
  log "5b. OFFLINE again after the update"
  go_offline
  offline_round "after-update-offline"
else
  fail "update: stack not ready"
fi

grep -q '^FAIL' "$RESULTS" && exit 1
exit 0
