#!/bin/sh
# Phase 12D9 - E2-04 local acceptance: fault injection in front of the REAL
# tesseract. TEST STACK ONLY (deploy/phase12-test), never production.
#
# Enable: PHASE12_TESSERACT_CMD=/app/scripts/ocr/phase12d9_tesseract_fault.sh in
# deploy/phase12-test/.env (it becomes OCR_TESSERACT_CMD), then
# `phase12-test.ps1 restart-app`. Remove the line and restart-app to disable.
#
# Control files in $CB5400_FAULT_DIR (default /phase12-out/fault, on Windows
# deploy\phase12-test\diagnostics\fault):
#   fail-once    the next RECOGNITION call (command line ends with
#                "stdout tsv") exits 1 and the file is removed: the region is
#                retried on the same crop - the document must be complete
#   fail-always  every recognition call exits 1: the document must be refused
#                (no Source content, no embedding, an older Source kept)
#   fail-osd     every orientation call ("--psm 0") exits 1: recognition still
#                runs with the configured language - the document must be
#                complete (OSD failing alone loses nothing)
# --version, --list-langs and everything else go straight to the real binary.
# No control file: nothing changes. Writes no document data anywhere.
REAL="${CB5400_REAL_TESSERACT:-/usr/bin/tesseract}"
DIR="${CB5400_FAULT_DIR:-/phase12-out/fault}"
prev=""
cur=""
osd=0
for arg in "$@"; do
    prev="$cur"
    cur="$arg"
    if [ "$prev" = "--psm" ] && [ "$cur" = "0" ]; then
        osd=1
    fi
done
if [ "$osd" = 1 ] && [ -e "$DIR/fail-osd" ]; then
    echo "cb5400 injected orientation failure (fail-osd)" >&2
    exit 1
fi
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
