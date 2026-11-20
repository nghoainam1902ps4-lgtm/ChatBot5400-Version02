"""Phase 12F0 - which synthetic change does each data comparison see? (TEST ONLY)

Inside the app container, against a throwaway SurrealDB:
    python f0_case_matrix.py /path/to/offline_package.py

For every case of f0_synthetic.CASES: reseed, take (a) the offline tool's data
fingerprint (offline_package.FINGERPRINT_PROBE + make_fingerprint - the code
used by `snapshot --compare` / F1 == F2) and (b) the full-content digest, apply
the change, take both again. Prints one JSON line per case: detected yes / no.
Synthetic data only; prints ids-free summaries.
"""

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f0_synthetic as f0  # noqa: E402


def load_tool(path: str):
    spec = importlib.util.spec_from_file_location("offline_package_f0", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tool_fp(tool) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(tool.FINGERPRINT_PROBE, "probe", "exec"), {"__name__": "probe"})
    line = [x for x in buf.getvalue().splitlines() if x.startswith("FINGERPRINT ")][-1]
    return tool.make_fingerprint(json.loads(line[len("FINGERPRINT "):]))["summary"]


def content_digest() -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asyncio.run(f0.digest())
    return json.loads(buf.getvalue().split("DIGEST ", 1)[1])


def main() -> int:
    f0._guard()
    tool = load_tool(sys.argv[1])
    rows = []
    for case, (table, _sql, _v) in f0.CASES.items():
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(f0.seed(do_reset=True))
        fp_a, dg_a = tool_fp(tool), content_digest()
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(f0.mutate(case))
        fp_b, dg_b = tool_fp(tool), content_digest()
        row = {
            "case": case,
            "table": table,
            "tool_fingerprint_detects": fp_a["sha256"] != fp_b["sha256"],
            "tool_table_entry_changed": fp_a["tables"][table] != fp_b["tables"][table],
            "tool_has_updated_for_table": fp_a["tables"][table]["updated_sha256"] is not None,
            "content_digest_detects": dg_a[table]["sha256"] != dg_b[table]["sha256"],
            "count_before_after": [dg_a[table]["count"], dg_b[table]["count"]],
        }
        rows.append(row)
        print("CASE " + json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
