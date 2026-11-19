"""Phase 12F0 - synthetic dataset for the offline-update rehearsal (TEST ONLY).

Runs INSIDE the ChatBot5400 app container (v1.2.0 or later), through the app's
own repository layer, against a THROWAWAY SurrealDB. Every record is synthetic
and has a fixed id prefixed ``f0`` so it can be found, mutated and compared.

    python f0_synthetic.py seed [--reset]     # migrations up + dataset
    python f0_synthetic.py digest             # full-content digest per table
    python f0_synthetic.py mutate <case>      # one D10-09 style change
    python f0_synthetic.py cases              # list the cases

Prints only record ids, counts and SHA-256 values (all data is synthetic).
Never point it at a production database: it refuses unless SURREAL_URL names
a host listed in F0_ALLOWED_DB_HOSTS (default: f0db, surrealdb, localhost).
"""

import asyncio
import hashlib
import json
import math
import os
import sys
from urllib.parse import urlparse

TABLES = ("notebook", "source", "note", "source_insight", "source_embedding")
DIM = 16
N_SOURCES = 3
CHUNKS_PER_SOURCE = 4


def _guard() -> None:
    host = urlparse(os.environ.get("SURREAL_URL", "")).hostname or ""
    allowed = os.environ.get("F0_ALLOWED_DB_HOSTS", "f0db,surrealdb,localhost").split(",")
    if host not in allowed:
        sys.exit(f"REFUSED: SURREAL_URL host {host!r} is not a rehearsal database {allowed}")


def vec(seed: str) -> list:
    """Deterministic unit vector of DIM floats derived from ``seed``."""
    h = hashlib.sha256(seed.encode()).digest()
    raw = [((h[i % len(h)] / 255.0) - 0.5) * (1 + i / DIM) for i in range(DIM)]
    n = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [round(x / n, 6) for x in raw]


def chunk_text(s: int, c: int) -> str:
    return f"Doan tong hop {c} cua nguon thu {s}. Noi dung gia lap, khong phai tai lieu nghiep vu."


async def _q(sql: str, vars: dict | None = None):
    from open_notebook.database.repository import repo_query

    return await repo_query(sql, vars or {})


async def migrate() -> int:
    from open_notebook.database.async_migrate import AsyncMigrationManager

    mgr = AsyncMigrationManager()
    if await mgr.needs_migration():
        await mgr.run_migration_up()
    return await mgr.get_current_version()


async def reset() -> None:
    for t in ("reference", "artifact") + TABLES[::-1]:
        await _q(f"DELETE {t} WHERE string::starts_with(record::id(id), 'f0')")


async def seed(do_reset: bool) -> None:
    version = await migrate()
    if do_reset:
        await reset()
    await _q(
        "CREATE notebook:f0nb1 SET name = 'So tong hop F0', description = 'Du lieu thu Phase 12F', archived = false"
    )
    for s in range(1, N_SOURCES + 1):
        sid = f"f0src{s}"
        full = " ".join(chunk_text(s, c) for c in range(CHUNKS_PER_SOURCE))
        await _q(
            f"CREATE source:{sid} SET title = $t, full_text = $f, topics = ['tong-hop', 'f0']",
            {"t": f"Nguon tong hop {s}", "f": full},
        )
        await _q(f"RELATE source:{sid}->reference->notebook:f0nb1")
        for c in range(CHUNKS_PER_SOURCE):
            await _q(
                f"CREATE source_embedding:f0e_{s}_{c} SET source = source:{sid}, order = $o, content = $x, embedding = $v",
                {"o": c, "x": chunk_text(s, c), "v": vec(f"emb-{s}-{c}")},
            )
        await _q(
            f"CREATE source_insight:f0i_{s} SET source = source:{sid}, insight_type = 'summary', content = $x, embedding = $v",
            {"x": f"Tom tat tong hop cua nguon {s}.", "v": vec(f"ins-{s}")},
        )
    await _q(
        "CREATE note:f0note1 SET title = 'Ghi chu tong hop', content = 'Ghi chu thu, khong co du lieu that.', note_type = 'human', embedding = $v",
        {"v": vec("note-1")},
    )
    await _q("RELATE note:f0note1->artifact->notebook:f0nb1")
    counts = {}
    for t in TABLES:
        r = await _q(f"SELECT count() AS n FROM {t} WHERE string::starts_with(record::id(id), 'f0') GROUP ALL")
        counts[t] = r[0]["n"] if r else 0
    print("SEED " + json.dumps({"schema_version": version, "f0_counts": counts}))


async def digest() -> None:
    """Content digest over EVERY field of every record (the oracle the snapshot must match)."""
    out = {}
    for t in TABLES + ("reference", "artifact"):
        rows = await _q(f"SELECT * FROM {t}")
        canon = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
        out[t] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(canon).encode()).hexdigest()}
    print("DIGEST " + json.dumps(out, sort_keys=True))


CASES = {
    "vector_same_id": ("source_embedding", "UPDATE source_embedding:f0e_1_0 SET embedding = $v", {"v": vec("emb-1-0-CHANGED")}),
    "chunk_content": ("source_embedding", "UPDATE source_embedding:f0e_1_1 SET content = string::concat(content, ' (da sua)')", {}),
    "chunk_order": ("source_embedding", "UPDATE source_embedding:f0e_2_0 SET order = 1; UPDATE source_embedding:f0e_2_1 SET order = 0", {}),
    "add_record": ("source_embedding", "CREATE source_embedding:f0e_3_9 SET source = source:f0src3, order = 9, content = 'Doan them', embedding = $v", {"v": vec("emb-3-9")}),
    "delete_record": ("source_embedding", "DELETE source_embedding:f0e_3_3", {}),
    "insight_vector_same_id": ("source_insight", "UPDATE source_insight:f0i_1 SET embedding = $v", {"v": vec("ins-1-CHANGED")}),
    "note_content": ("note", "UPDATE note:f0note1 SET content = 'Ghi chu da sua'", {}),
    "source_full_text": ("source", "UPDATE source:f0src2 SET full_text = string::concat(full_text, ' x')", {}),
}


async def mutate(case: str) -> None:
    table, sql, v = CASES[case]
    await _q(sql, v)
    print("MUTATED " + json.dumps({"case": case, "table": table}))


def main(argv: list) -> int:
    _guard()
    if not argv or argv[0] == "cases":
        print("\n".join(CASES))
        return 0
    cmd = argv[0]
    if cmd == "seed":
        asyncio.run(seed("--reset" in argv))
    elif cmd == "digest":
        asyncio.run(digest())
    elif cmd == "mutate" and len(argv) == 2 and argv[1] in CASES:
        asyncio.run(mutate(argv[1]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
