#!/usr/bin/env bash
# Docker end-to-end acceptance for the OCR Engine Manager (docs/ocr/OCR_LOCAL_ACCEPTANCE.md).
#
# SAFE BY DESIGN
#   * Own compose project + own temporary directory (bind mounts) — never touches
#     an existing deployment, its volumes or its database.
#   * Never runs `docker compose down -v`; only removes the containers it created.
#
# WHAT IT VERIFIES (each step prints PASS / FAIL / NOT VERIFIED, summary at the end)
#   0. [OLD_REF set] the currently deployed version runs and stores a settings marker
#   1. fresh/upgraded start: DB, API, worker ready; Docling runtime on; no OCR model
#      downloaded at startup; settings from the old version preserved
#   2. per engine in $SCENARIOS, through the REAL API + worker: install model ->
#      job status -> activate -> test -> upload PDF -> source processed -> expected
#      Vietnamese text present -> worker log shows the selected Docling OCR model;
#      installing one engine does not download the others
#   3. restart: models untouched (checksums), settings + active engine preserved
#   4. offline: app on an `internal: true` network (DB reachable, Internet blocked,
#      verified), recreated with OCR_OFFLINE/HF_HUB_OFFLINE: runtimes restored from
#      cache, documents processed, no model / HF cache change, no download in logs
#   5. real image rebuild (new image ID): recreate -> runtimes restored, model
#      checksums unchanged, settings preserved, engine still processes documents
#
# USAGE
#   scripts/ocr/docker-acceptance.sh
# ENV
#   SCENARIOS="tesseract_best easyocr"   engines to test end-to-end
#   OLD_REF=<git ref>                    version currently deployed (upgrade test); empty = skip
#   SKIP_BUILD=1                         reuse already-built $IMAGE (step 5 still rebuilds)
#   KEEP_WORK=1                          keep the temp directory for inspection
#   UV_TORCH_BACKEND=cpu                 (default) CPU-only torch for the Docling install
set -uo pipefail

REPO="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SCENARIOS="${SCENARIOS:-tesseract_best easyocr}"
OLD_REF="${OLD_REF:-}"
IMAGE="${IMAGE:-chatbot5400:ocr-accept}"
OLD_IMAGE="${IMAGE}-old"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ocr-accept.XXXXXX")"
PROJECT="ocraccept$$"
FIXTURE="$REPO/tests/fixtures/ocr/vb_scan.pdf"
EXPECT1="1234/2024/QĐ-MẪU"
EXPECT2="Hạn mức thử nghiệm là 1.250.000.000 đồng"
DB_PASS="accept-$(date +%s)-$$"
RESULTS="$WORK/results.txt"
: > "$RESULTS"

log() { printf '\n=== %s\n' "$*"; }
record() { printf '%-14s %s\n' "$1" "$2" | tee -a "$RESULTS"; }
pass() { record "PASS" "$*"; }
fail() { record "FAIL" "$*"; }
nv() { record "NOT VERIFIED" "$*"; }

# --- compose files -------------------------------------------------------------
cat > "$WORK/compose.yml" <<EOF
networks:
  backend:
    internal: true        # DB traffic only, no route to the Internet
  egress: {}
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
      - OPEN_NOTEBOOK_WORKER_MAX_TASKS=1
      - OCR_OFFLINE=\${OCR_OFFLINE:-false}
      - HF_HUB_OFFLINE=\${HF_HUB_OFFLINE:-0}
    volumes: ["./data:/app/data"]
    networks: [backend]
    depends_on: [surrealdb]
EOF
cat > "$WORK/online.yml" <<'EOF'
services:
  app:
    networks: [backend, egress]
EOF
mkdir -p "$WORK/data" "$WORK/surreal_data"

dc_online() { docker compose -p "$PROJECT" -f "$WORK/compose.yml" -f "$WORK/online.yml" "$@"; }
dc_offline() { docker compose -p "$PROJECT" -f "$WORK/compose.yml" "$@"; }
app_id() { docker compose -p "$PROJECT" -f "$WORK/compose.yml" ps -q app; }
api() {
  local id; id="$(app_id)"
  docker cp "$REPO/scripts/ocr/acceptance_api.py" "$id:/tmp/acceptance_api.py" >/dev/null
  docker cp "$FIXTURE" "$id:/tmp/vb_scan.pdf" >/dev/null
  docker exec "$id" /app/.venv/bin/python /tmp/acceptance_api.py "$@"
}
model_sums() { (cd "$WORK/data/ocr/models" 2>/dev/null && find . -type f \( -name '*.traineddata' -o -name '*.pth' \) -exec sha256sum {} + | sort) || true; }
hf_state() { find "$WORK/data/.cache/huggingface" -type f -printf '%s %P\n' 2>/dev/null | sort | sha256sum | cut -c1-16; }
cleanup() {
  docker compose -p "$PROJECT" -f "$WORK/compose.yml" down --remove-orphans >/dev/null 2>&1 || true
  echo
  echo "================ SUMMARY ================"
  cat "$RESULTS"
  if [ "${KEEP_WORK:-0}" = "1" ]; then
    echo "work dir kept: $WORK"
  else
    # Files written by the (root) containers: remove them with the image itself.
    docker run --rm -v "$WORK:/w" --entrypoint sh "$IMAGE" -c 'rm -rf /w/data /w/surreal_data' >/dev/null 2>&1 || true
    rm -rf "$WORK" 2>/dev/null || echo "work dir left at: $WORK"
  fi
}
trap cleanup EXIT

wait_ready() {  # $1 = timeout seconds, $2 = extra flag (e.g. --no-ocr)
  if api --timeout "$1" wait-ready ${2:-} >"$WORK/ready.json"; then return 0; fi
  cat "$WORK/ready.json"; return 1
}

# --- build ---------------------------------------------------------------------------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  log "Build image under test ($IMAGE) with the Tesseract build profile"
  docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t "$IMAGE" "$REPO" || { fail "docker build"; exit 1; }
fi
if [ -n "$OLD_REF" ]; then
  log "Build the currently deployed version ($OLD_REF) for the upgrade test"
  git -C "$REPO" worktree add --detach "$WORK/old-src" "$OLD_REF" >/dev/null &&
    docker build --target runtime -t "$OLD_IMAGE" "$WORK/old-src" && OLD_OK=1 || OLD_OK=0
  git -C "$REPO" worktree remove --force "$WORK/old-src" >/dev/null 2>&1 || true
  [ "$OLD_OK" = 1 ] || { fail "build of OLD_REF=$OLD_REF"; OLD_REF=""; }
fi

# --- 0. previous version -----------------------------------------------------------------
if [ -n "$OLD_REF" ]; then
  log "0. Previous version $OLD_REF: start and store a settings marker"
  APP_IMAGE="$OLD_IMAGE" dc_online up -d >/dev/null
  if wait_ready 3600 --no-ocr && api settings-set >/dev/null; then pass "old version running, settings marker stored"; else fail "old version start/settings"; fi
fi

# --- 1. fresh / upgraded start -------------------------------------------------------------
log "1. Start the image under test (first boot installs Docling with lock constraints)"
APP_IMAGE="$IMAGE" dc_online up -d --force-recreate >/dev/null
if wait_ready 3600; then pass "DB + API + worker ready, admin login, OCR API reachable"; else fail "stack not ready"; exit 1; fi
grep -q '"docling_available": true' "$WORK/ready.json" && pass "Docling runtime enabled" || fail "Docling runtime missing: $(cat "$WORK/ready.json")"
grep -q '"dependency_problems": \[\]' "$WORK/ready.json" && pass "content-core/Docling = verified versions" || fail "dependency problems: $(cat "$WORK/ready.json")"
[ -z "$(model_sums)" ] && pass "no OCR model downloaded at startup" || fail "OCR models present after startup"
if [ -n "$OLD_REF" ]; then api settings-check >/dev/null && pass "settings from $OLD_REF preserved after upgrade" || fail "settings lost after upgrade"; fi

# --- 2. engines end-to-end through API + worker ---------------------------------------------
LAST=""
FIRST=1
for E in $SCENARIOS; do
  log "2. $E end-to-end (install -> activate -> test -> upload -> processed)"
  out="$(api ocr-e2e --engine "$E" --pdf /tmp/vb_scan.pdf --expect "$EXPECT1" --expect "$EXPECT2")"; rc=$?
  echo "$out"
  case $rc in
    0) pass "$E: install/activate/test/upload/process via API+worker";;
    2) nv "$E: $out";;
    *) fail "$E: $out";;
  esac
  CLASS=TesseractOcrCliModel; [ "$E" = easyocr ] && CLASS=EasyOcrModel; [ "$E" = rapidocr ] && CLASS=RapidOcrModel
  if docker logs "$(app_id)" 2>&1 | grep -q "Docling OCR finished: engine=$E actual_models=\['$CLASS'\]"; then
    pass "$E: worker log shows Docling used $CLASS"
  else
    [ $rc -eq 0 ] && fail "$E: worker log lacks 'actual_models=['$CLASS']'"
  fi
  if [ $FIRST = 1 ] && [ $rc -eq 0 ]; then
    others="$(model_sums | grep -v -e "/${E#tesseract_}/" -e 'osd.traineddata' | grep -c . || true)"
    case "$E" in tesseract_*) [ "$others" = 0 ] && pass "installing $E downloaded no other engine" || fail "other engines downloaded";; esac
  fi
  [ $rc -eq 0 ] && LAST="$E"
  FIRST=0
done
[ -n "$LAST" ] || { fail "no engine passed end-to-end; remaining steps skipped"; exit 1; }

api settings-set --with-ocr >/dev/null && pass "settings marker incl. OCR config stored" || fail "settings-set"
SUMS_BEFORE="$(model_sums)"

# --- 3. restart --------------------------------------------------------------------------------
log "3. Restart"
dc_online restart app >/dev/null
wait_ready 1800 || fail "not ready after restart"
[ "$(model_sums)" = "$SUMS_BEFORE" ] && pass "restart: model checksums unchanged" || fail "restart: models changed"
api settings-check --with-ocr --engine "$LAST" >/dev/null && pass "restart: settings + active engine ($LAST) preserved" || fail "restart: settings lost"

# --- 4. offline ---------------------------------------------------------------------------------
log "4. Offline: internal network only, recreated with OCR_OFFLINE=true HF_HUB_OFFLINE=1"
HF_BEFORE="$(hf_state)"
SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
APP_IMAGE="$IMAGE" OCR_OFFLINE=true HF_HUB_OFFLINE=1 dc_offline up -d --force-recreate app >/dev/null
if docker exec "$(app_id)" /app/.venv/bin/python -c "import urllib.request;urllib.request.urlopen('https://pypi.org/simple/',timeout=10)" >/dev/null 2>&1; then
  fail "offline: container can still reach the Internet (test invalid)"
else
  pass "offline: Internet unreachable from the app container"
fi
if wait_ready 1800; then
  pass "offline: DB + API + worker up (runtimes restored from cache)"
  out="$(api ocr-e2e --engine "$LAST" --pdf /tmp/vb_scan.pdf --expect "$EXPECT1")"; rc=$?
  [ $rc -eq 0 ] && pass "offline: document processed with $LAST" || fail "offline processing: $out"
  [ "$(model_sums)" = "$SUMS_BEFORE" ] && pass "offline: model checksums unchanged" || fail "offline: models changed"
  [ "$(hf_state)" = "$HF_BEFORE" ] && pass "offline: Hugging Face cache unchanged (no download)" || fail "offline: HF cache changed"
  if docker logs --since "$SINCE" "$(app_id)" 2>&1 | grep -E -i "Initiating download|Downloading https|huggingface.co/api" >/dev/null; then
    fail "offline: download attempt found in logs"
  else
    pass "offline: no download attempt in logs"
  fi
else
  fail "offline: stack did not come up (see: docker logs $(app_id))"
fi

# --- 5. real image rebuild ------------------------------------------------------------------------
log "5. Rebuild the image for real and recreate"
OLD_ID="$(docker image inspect -f '{{.Id}}' "$IMAGE")"
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true \
  --no-cache-filter runtime-base,runtime -t "$IMAGE" "$REPO" >/dev/null || fail "rebuild"
NEW_ID="$(docker image inspect -f '{{.Id}}' "$IMAGE")"
[ "$OLD_ID" != "$NEW_ID" ] && pass "rebuild produced a new image ($NEW_ID)" || fail "rebuild reused the same image id"
APP_IMAGE="$IMAGE" dc_online up -d --force-recreate app >/dev/null
CID_NEW_IMAGE="$(docker inspect -f '{{.Image}}' "$(app_id)")"
[ "$CID_NEW_IMAGE" = "$NEW_ID" ] && pass "container recreated from the rebuilt image" || fail "container not on the rebuilt image"
if wait_ready 3600; then
  docker exec "$(app_id)" /app/.venv/bin/python -m open_notebook.ocr.cli status --no-db | tee "$WORK/status.txt"
  grep -E "^$LAST +state=ready" "$WORK/status.txt" >/dev/null && pass "rebuild: runtime restored, $LAST ready" || fail "rebuild: $LAST not ready"
  [ "$(model_sums)" = "$SUMS_BEFORE" ] && pass "rebuild: model checksums unchanged (no re-download)" || fail "rebuild: models changed"
  api settings-check --with-ocr --engine "$LAST" >/dev/null && pass "rebuild: settings + active engine preserved" || fail "rebuild: settings lost"
  out="$(api ocr-e2e --engine "$LAST" --pdf /tmp/vb_scan.pdf --expect "$EXPECT1")" && pass "rebuild: $LAST still processes documents" || fail "rebuild processing: $out"
else
  fail "rebuild: stack not ready"
fi

grep -q '^FAIL' "$RESULTS" && exit 1
exit 0
