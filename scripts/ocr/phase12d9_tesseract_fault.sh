#!/bin/sh
# Phase 12D9 - E2-04 local acceptance: fault injection in front of the REAL
# tesseract. TEST STACK ONLY (deploy/phase12-test), never production.
#
# Enable: PHASE12_TESSERACT_CMD=/app/scripts/ocr/phase12d9_tesseract_fault.sh in
# deploy/phase12-test/.env (it becomes OCR_TESSERACT_CMD), then
# `phase12-test.ps1 restart-app`. Remove the line and restart-app to disable.
#
# Only RECOGNITION calls (the command line ends with "stdout tsv") can fail;
# orientation (OSD), --version, --list-langs and every other call go straight to
# the real binary. Control files in $CB5400_FAULT_DIR (default /phase12-out/fault,
# on Windows deploy\phase12-test\diagnostics\fault):
#   fail-once    the next recognition call exits 1 and the file is removed:
#                the region is retried on the same crop - the document must be
#                complete
#   fail-always  every recognition call exits 1: the document must be refused
#                (no Source content, no embedding, an older Source kept)
# No control file: nothing changes. Writes no document data anywhere.
REAL="${CB5400_REAL_TESSERACT:-/usr/bin/tesseract}"
DIR="${CB5400_FAULT_DIR:-/phase12-out/fault}"
prev=""
cur=""
for arg in "$@"; do
    prev="$cur"
    cur="$arg"
done
if [ "$prev $cur" = "stdout tsv" ]; then
    if [ -e "$DIR/fail-always" ]; then
        echo "cb5400 injected recognition failure (fail-always)" >&2
        exit 1
    fi
    if rm "$DIR/fail-once" 2>/dev/null; then
        echo "cb5400 injected recognition failure (fail-once)" >&2
        exit 1
    fi
fi
exec "$REAL" "$@"
