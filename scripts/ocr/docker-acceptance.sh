#!/usr/bin/env bash
# Docker acceptance test for the OCR Engine Manager (docs/ocr/OCR_TEST_REPORT.md).
#
# SAFE BY DESIGN: runs in its OWN compose project and its OWN temporary data
# directory. It never touches an existing deployment's volumes, never runs
# `docker compose down -v`, and removes only the containers it created.
#
# Usage:
#   docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t chatbot5400:ocr-test .
#   IMAGE=chatbot5400:ocr-test scripts/ocr/docker-acceptance.sh
#
# Scenarios: fresh install downloads no OCR engine · install one engine only ·
# restart and recreate keep models (no re-download) · shared osd survives
# removing one Tesseract variant · failed install leaves the ready engine
# intact · offline (no network) startup keeps engines ready · new image tag
# reuses the models.
set -euo pipefail

IMAGE="${IMAGE:-chatbot5400:ocr-test}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ocr-accept.XXXXXX")"
PROJECT="ocraccept$$"
PASS=0
FAIL=0

log() { printf '\n=== %s\n' "$*"; }
ok() { echo "PASS: $*"; PASS=$((PASS + 1)); }
ko() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

cat > "$WORK/compose.yml" <<EOF
services:
  surrealdb:
    image: surrealdb/surrealdb:v2
    command: ["start", "--user", "root", "--pass", "root", "memory"]
  app:
    image: ${IMAGE}
    environment:
      - OPEN_NOTEBOOK_ENCRYPTION_KEY=ocr-acceptance-only
      - SURREAL_URL=ws://surrealdb:8000/rpc
      - SURREAL_USER=root
      - SURREAL_PASSWORD=root
      - SURREAL_NAMESPACE=open_notebook
      - SURREAL_DATABASE=open_notebook
      - OCR_OFFLINE=\${OCR_OFFLINE:-false}
    volumes:
      - ./data:/app/data
    depends_on: [surrealdb]
EOF
mkdir -p "$WORK/data"
dc() { docker compose -p "$PROJECT" -f "$WORK/compose.yml" "$@"; }
cli() { dc exec -T app uv run --no-sync python -m open_notebook.ocr.cli "$@"; }
state_of() { cli status --no-db 2>/dev/null | awk -v e="$1" '$1==e {sub("state=","",$2); print $2}'; }
cleanup() { dc down --remove-orphans >/dev/null 2>&1 || true; echo "work dir kept for inspection: $WORK"; }
trap cleanup EXIT

wait_app() {
  for _ in $(seq 1 60); do
    if dc exec -T app sh -c 'test -d /app/data' 2>/dev/null; then return 0; fi
    sleep 2
  done
  return 1
}

log "1. Fresh installation: no OCR engine downloaded at startup"
dc up -d >/dev/null
wait_app
sleep 5
if [ -z "$(find "$WORK/data/ocr/models" -type f -name '*.traineddata' -o -type f -name '*.pth' 2>/dev/null)" ]; then
  ok "no OCR model files after first boot"
else
  ko "OCR model files present after first boot"
fi
[ "$(state_of tesseract_best)" = "not_installed" ] && ok "tesseract_best not_installed" || ko "tesseract_best state $(state_of tesseract_best)"
[ "$(state_of easyocr)" = "not_installed" ] && ok "easyocr not_installed" || ko "easyocr state $(state_of easyocr)"
[ "$(state_of rapidocr)" = "ready" ] || echo "note: rapidocr not ready (Docling not installed in this image: $(state_of rapidocr))"

log "2. Install one engine only (tesseract_best)"
cli install-model tesseract_best
[ "$(state_of tesseract_best)" = "ready" ] && ok "tesseract_best ready" || ko "tesseract_best $(state_of tesseract_best)"
[ ! -e "$WORK/data/ocr/models/tesseract/fast/vie.traineddata" ] && ok "fast not downloaded" || ko "fast downloaded"
[ ! -e "$WORK/data/ocr/models/easyocr" ] && ok "easyocr not downloaded" || ko "easyocr downloaded"
STAMP="$(stat -c %Y "$WORK/data/ocr/models/tesseract/best/vie.traineddata")"

log "3. Restart container keeps models (no re-download)"
dc restart app >/dev/null
wait_app
[ "$(state_of tesseract_best)" = "ready" ] && ok "ready after restart" || ko "after restart: $(state_of tesseract_best)"
[ "$(stat -c %Y "$WORK/data/ocr/models/tesseract/best/vie.traineddata")" = "$STAMP" ] && ok "model file untouched" || ko "model file rewritten"

log "4. Recreate container keeps models"
dc up -d --force-recreate app >/dev/null
wait_app
[ "$(state_of tesseract_best)" = "ready" ] && ok "ready after recreate" || ko "after recreate: $(state_of tesseract_best)"
cli install-model tesseract_best | grep -q "'existing'" && ok "reinstall reuses verified files" || ko "reinstall re-downloaded"

log "5. Shared osd survives removing the other Tesseract variant"
cli install-model tesseract_fast >/dev/null
cli remove-model tesseract_fast
[ -e "$WORK/data/ocr/models/tesseract/osd.traineddata" ] && ok "osd kept" || ko "osd removed"
[ "$(state_of tesseract_best)" = "ready" ] && ok "best still ready" || ko "best $(state_of tesseract_best)"

log "6. Failed install does not affect the ready engine"
if dc exec -T -e OCR_OFFLINE=true app uv run --no-sync python -m open_notebook.ocr.cli install-model easyocr; then
  ko "offline install without bundle unexpectedly succeeded"
else
  ok "offline install without bundle failed cleanly"
fi
[ "$(state_of tesseract_best)" = "ready" ] && ok "best still ready" || ko "best $(state_of tesseract_best)"

log "7. Offline startup (no network) keeps engines ready"
OCR_OFFLINE=true dc up -d --force-recreate app >/dev/null
NET="${PROJECT}_default"
docker network disconnect "$NET" "$(dc ps -q app)" >/dev/null 2>&1 || true
dc restart app >/dev/null
wait_app
[ "$(state_of tesseract_best)" = "ready" ] && ok "ready offline" || ko "offline: $(state_of tesseract_best)"
docker network connect "$NET" "$(dc ps -q app)" >/dev/null 2>&1 || true

log "8. New image tag reuses the models"
docker tag "$IMAGE" "${IMAGE}-next"
IMAGE_NEXT="${IMAGE}-next"
sed -i "s|image: ${IMAGE}$|image: ${IMAGE_NEXT}|" "$WORK/compose.yml"
dc up -d app >/dev/null
wait_app
[ "$(state_of tesseract_best)" = "ready" ] && ok "ready on new image" || ko "new image: $(state_of tesseract_best)"
[ "$(stat -c %Y "$WORK/data/ocr/models/tesseract/best/vie.traineddata")" = "$STAMP" ] && ok "model not re-downloaded" || ko "model re-downloaded"
docker rmi "${IMAGE_NEXT}" >/dev/null 2>&1 || true

echo
echo "RESULT: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
