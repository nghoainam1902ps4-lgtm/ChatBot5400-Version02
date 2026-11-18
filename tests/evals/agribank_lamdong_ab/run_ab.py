"""Deterministic A/B harness for the Agribank Lâm Đồng system prompts.

LEVEL 1 / LEVEL 2 ONLY. Makes NO external AI calls. It:

1. Loads prompt A (old) from the base commit and prompt B (new) from the working
   tree, renders both for every synthetic case with identical inputs, and
   confirms Jinja validity + variable parity.
2. Runs an instruction-coverage check: for each case, whether the rendered
   system prompt contains the Vietnamese instruction signals needed to steer the
   required behaviour. This is a PROXY for prompt strength, NOT a measurement of
   model output — behavioural scoring (HARD FAILs, 0-2 rubric) requires Level 3.
3. Prints char/token-cost deltas and a machine-readable JSON summary.

Run:  uv run python tests/evals/agribank_lamdong_ab/run_ab.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import CASES, HARD_FAIL_LABELS  # noqa: E402

BASE_SHA = "887e55e23bd306686b8cd55ae960af3e77a5a3bf"

PROMPT_FILES = {
    "notebook": "prompts/chat/system.jinja",
    "source": "prompts/source_chat/system.jinja",
}


def _git_show(sha: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout


def _worktree(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def _norm(s: str) -> str:
    """Whitespace-normalise so newline-wrapped template phrases still match."""
    return re.sub(r"\s+", " ", s).strip()


def render(template_src: str, case: dict) -> str:
    from jinja2 import Environment
    env = Environment()
    t = env.from_string(template_src)
    if case["mode"] == "notebook":
        data = dict(
            notebook={
                "name": case.get("notebook_name", "Notebook thử nghiệm"),
                "description": case.get("notebook_description", "Mô tả thử nghiệm"),
            },
            context=case["context"],
        )
    else:
        # Minimal source object; title/topics are not the subject of these cases
        data = dict(
            source={"id": "source:_render", "title": "Tài liệu", "topics": []},
            context=case["context"],
        )
    return t.render(**data)


def main() -> int:
    old_tpl = {m: _git_show(BASE_SHA, p) for m, p in PROMPT_FILES.items()}
    new_tpl = {m: _worktree(p) for m, p in PROMPT_FILES.items()}

    # --- Structural checks: render validity + variable parity ---
    from jinja2 import Environment, meta
    env = Environment()
    structural = {}
    for label, tpls in (("A_old", old_tpl), ("B_new", new_tpl)):
        for mode, src in tpls.items():
            ast = env.parse(src)
            structural[f"{label}:{mode}"] = sorted(meta.find_undeclared_variables(ast))

    # New prompt must not introduce a runtime variable the old one lacked.
    new_vars_only = {}
    for mode in PROMPT_FILES:
        old_v = set(structural[f"A_old:{mode}"])
        new_v = set(structural[f"B_new:{mode}"])
        new_vars_only[mode] = sorted(new_v - old_v)

    # --- Forbidden vestigial tool wording (English) in NEW prompts ---
    forbidden = ["search tool", "query you made", "specialized tools"]
    forbidden_hits = {}
    for mode, src in new_tpl.items():
        low = src.lower()
        forbidden_hits[mode] = [p for p in forbidden if p in low]

    # --- Per-case instruction-coverage (A vs B) ---
    results = []
    for case in CASES:
        mode = case["mode"]
        a_src = _norm(old_tpl[mode])
        b_src = _norm(new_tpl[mode])
        sigs = case.get("signals", [])
        a_cov = [s for s in sigs if _norm(s) in a_src]
        b_cov = [s for s in sigs if _norm(s) in b_src]
        # also render both to confirm no template error for this case
        render(old_tpl[mode], case)
        render(new_tpl[mode], case)
        results.append(dict(
            id=case["id"], mode=mode, title=case["title"],
            n_signals=len(sigs),
            A_covered=len(a_cov), B_covered=len(b_cov),
            A_missing=[s for s in sigs if s not in a_cov],
            hard_fail_risks=[HARD_FAIL_LABELS[h] for h in case["hard_fail_risks"]],
        ))

    # --- Cost ---
    def chars(s): return len(s)
    def wtok(s): return int(len(s.split()) * 1.3)  # repo offline token fallback
    cost = {}
    for mode in PROMPT_FILES:
        cost[mode] = dict(
            old_chars=chars(old_tpl[mode]), new_chars=chars(new_tpl[mode]),
            old_tok_est=wtok(old_tpl[mode]), new_tok_est=wtok(new_tpl[mode]),
        )

    total_A = sum(r["A_covered"] for r in results)
    total_B = sum(r["B_covered"] for r in results)
    total_sig = sum(r["n_signals"] for r in results)

    summary = dict(
        base_sha=BASE_SHA,
        n_cases=len(CASES),
        modes={"notebook": sum(1 for c in CASES if c["mode"] == "notebook"),
               "source": sum(1 for c in CASES if c["mode"] == "source")},
        structural_vars=structural,
        new_runtime_vars_introduced=new_vars_only,
        forbidden_tool_wording_in_new=forbidden_hits,
        instruction_coverage=dict(total_signals=total_sig, A_old=total_A, B_new=total_B),
        cost=cost,
        per_case=results,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Assertions that make this usable as a pytest-style gate too
    assert all(not v for v in new_vars_only.values()), f"NEW introduced vars: {new_vars_only}"
    assert all(not v for v in forbidden_hits.values()), f"Forbidden wording: {forbidden_hits}"
    assert total_B >= total_A, "NEW prompt covers fewer instruction signals than OLD"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
