"""Phase 12F1 - D10-09 negative control N0 (TEST ONLY, synthetic rehearsal DB).

    python f0_live_control.py <path/to/offline_package.py>

Prints one LIVE line: the offline tool's data fingerprint, a hash of the raw
INFO FOR TABLE command (which includes the worker's LIVE query subscriptions)
and the number of LIVE queries. Run it, restart ONLY the worker (no business
write), run it again: the raw hash / live count change, the tool fingerprint
must NOT change (a LIVE query is runtime state, not business data). The 8
mutation cases of f0_case_matrix.py must still be detected.
"""

import asyncio
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f0_synthetic as f0  # noqa: E402


def main() -> int:
    f0._guard()
    spec = importlib.util.spec_from_file_location("offline_package_f0", sys.argv[1])
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(tool.FINGERPRINT_PROBE, "probe", "exec"), {"__name__": "probe"})
    line = [x for x in buf.getvalue().splitlines() if x.startswith("FINGERPRINT ")][-1]
    fp = tool.make_fingerprint(json.loads(line[len("FINGERPRINT "):]))["summary"]["sha256"]
    info = asyncio.run(f0._q("INFO FOR TABLE command"))
    info = info[0] if isinstance(info, list) else info
    raw = hashlib.sha256(json.dumps(info, sort_keys=True, default=str).encode()).hexdigest()
    print("LIVE " + json.dumps({"tool_fingerprint": fp, "raw_info_command_sha256": raw, "live_queries": len(info.get("lives") or {})}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
