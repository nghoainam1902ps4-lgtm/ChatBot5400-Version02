#!/bin/sh
set -eu

root=/opt/cb5400-rb1
case "${OCR_OFFLINE:-}:${OCR_RAPIDOCR_PERSISTENT:-}:${OPEN_NOTEBOOK_ENABLE_DOCLING:-}:${OPEN_NOTEBOOK_ENABLE_CRAWL4AI:-false}" in
    true:true:true:false) ;;
    *) echo '[rb1] REFUSED: incompatible offline runtime configuration' >&2; exit 3 ;;
esac
export UV_OFFLINE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

if [ "$#" -eq 0 ]; then
    printf '%s\n' '62371dd1bc8e2138a2b03c29cd3efe91aec0ffade45e66c3e3f7c35df8a8349f  /app/scripts/docker-entrypoint.sh' | sha256sum -c -
    exec /app/scripts/docker-entrypoint.sh /bin/sh "$root/startup.sh" after-entrypoint
fi
[ "$#" -eq 1 ] && [ "$1" = after-entrypoint ] || exit 2
/app/.venv/bin/python -I -B "$root/runtime_gate.py" --apply
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
