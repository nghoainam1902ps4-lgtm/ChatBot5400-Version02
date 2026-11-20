"""Phase 12F1 - record-level preservation check (TEST ONLY, synthetic rehearsal DB).

    python f0_preserve.py snapshot <file.json>   # per table: record id -> SHA-256 of the record
    python f0_preserve.py compare  <file.json>   # PRESERVE line: changed / missing / new per table

"Preserved" = every record that existed at the snapshot is still there with
identical content (all fields, embeddings included). New records are listed
separately (e.g. the synthetic test Source an acceptance step uploads on purpose).
Prints ids-free counts only.
"""

import asyncio
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f0_synthetic as f0  # noqa: E402


async def records() -> dict:
    info = await f0._q("INFO FOR DB")
    info = info[0] if isinstance(info, list) else info
    out = {}
    for t in sorted((info.get("tables") or {}).keys()):
        rows = await f0._q(f"SELECT * FROM {t}")
        out[t] = {
            str(r.get("id")): hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()
            for r in rows
        }
    return out


def main(argv: list) -> int:
    f0._guard()
    if len(argv) != 2 or argv[0] not in ("snapshot", "compare"):
        print(__doc__)
        return 2
    now = asyncio.run(records())
    if argv[0] == "snapshot":
        with open(argv[1], "w", encoding="utf-8") as fh:
            json.dump(now, fh, sort_keys=True)
        print("SNAPSHOT " + json.dumps({t: len(v) for t, v in now.items()}, sort_keys=True))
        return 0
    with open(argv[1], encoding="utf-8") as fh:
        before = json.load(fh)
    res, bad = {}, False
    for t in sorted(set(before) | set(now)):
        b, a = before.get(t, {}), now.get(t, {})
        changed = sum(1 for i in b if i in a and a[i] != b[i])
        missing = sum(1 for i in b if i not in a)
        new = sum(1 for i in a if i not in b)
        if changed or missing or new:
            res[t] = {"changed": changed, "missing": missing, "new": new}
        bad = bad or bool(changed or missing)
    print("PRESERVE " + json.dumps({"preserved": not bad, "differences": res}, sort_keys=True))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
