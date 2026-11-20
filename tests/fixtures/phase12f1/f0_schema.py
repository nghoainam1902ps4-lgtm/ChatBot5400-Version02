"""Phase 12F1 - schema + whole-database digest (TEST ONLY, synthetic rehearsal DB).

    python f0_schema.py            # prints one SCHEMA line (JSON)

For every table that INFO FOR DB lists: the SHA-256 of its INFO FOR TABLE
(fields, indexes, events) and of all its records; plus SHA-256 of the
database-level definitions (analyzers, functions, params, accesses, ...).
Used to compare a source database with its restored copy: equal digests on a
few tables are NOT enough - every table and every definition must match.
"""

import asyncio
import hashlib
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import f0_synthetic as f0  # noqa: E402


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


async def main() -> None:
    info = (await f0._q("INFO FOR DB"))
    info = info[0] if isinstance(info, list) else info
    tables = sorted((info.get("tables") or {}).keys())
    db_defs = {k: h(v) for k, v in sorted(info.items()) if k != "tables"}
    out: dict = {"tables": {}, "db_definitions": db_defs, "table_names_sha256": h(tables)}
    runtime = {}
    for t in tables:
        ti = await f0._q(f"INFO FOR TABLE {t}")
        ti = ti[0] if isinstance(ti, list) else ti
        # LIVE queries are per-connection runtime state (the worker re-registers
        # one on `command` at every start), not data or schema: excluded.
        runtime[t] = len(ti.pop("lives", None) or {})
        rows = await f0._q(f"SELECT * FROM {t}")
        canon = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
        out["tables"][t] = {
            "definition_sha256": h(info["tables"][t]),
            "info_sha256": h(ti),
            "fields": len(ti.get("fields") or {}),
            "indexes": len(ti.get("indexes") or {}),
            "events": len(ti.get("events") or {}),
            "records": len(rows),
            "records_sha256": hashlib.sha256("\n".join(canon).encode()).hexdigest(),
        }
    print("SCHEMA " + json.dumps(out, sort_keys=True))
    print("RUNTIME " + json.dumps({"live_queries": runtime}, sort_keys=True))


if __name__ == "__main__":
    f0._guard()
    asyncio.run(main())
