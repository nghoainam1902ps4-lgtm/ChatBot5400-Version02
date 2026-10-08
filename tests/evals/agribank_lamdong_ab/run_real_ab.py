"""Level-3 real-model A/B runner for the Agribank Lâm Đồng system prompts.

Runs the SAME 28 synthetic cases (``fixtures.py``) against a single model with
only the SYSTEM PROMPT varied between A (OLD) and B (NEW). Prompts are FROZEN
from Git objects, not the working tree, so the comparison can't drift.

SAFETY (see SP-02 Level-3 task):
- Never prints/logs credentials, headers, or os.environ.
- Does NOT touch production SurrealDB. The app's ``provision_langchain_model``
  resolves models/credentials via ``repo_query`` (production DB), so this runner
  uses an ISOLATED Esperanto adapter built from explicit env-var config instead.
  Difference from production invocation is documented in the report.
- Real provider calls happen ONLY when a non-production credential + explicit
  model id are configured AND --dry-run is not set. Otherwise: zero calls.

Invocation (either works):
    uv run python tests/evals/agribank_lamdong_ab/run_real_ab.py --model "<id>" --dry-run
    uv run python -m tests.evals.agribank_lamdong_ab.run_real_ab --model "<id>" --dry-run

First pass is fixed at 1 sample/prompt → 28 cases × 2 = 56 calls max.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fixtures import CASES, HARD_FAIL_LABELS  # noqa: E402

OLD_SHA = "887e55e23bd306686b8cd55ae960af3e77a5a3bf"
NEW_SHA = "1fcbde4922e950716b82d937f086ba45ad30e644"
PROMPT_FILES = {"notebook": "prompts/chat/system.jinja",
                "source": "prompts/source_chat/system.jinja"}
RESULTS_DIR = HERE / "results"
MAX_FIRST_PASS_CALLS = 56


# --------------------------------------------------------------------------- #
# Frozen prompt loading                                                        #
# --------------------------------------------------------------------------- #
def git_show(sha: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{sha}:{path}"], cwd=REPO,
                          capture_output=True, text=True, check=True).stdout


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_frozen_prompts() -> dict:
    out = {}
    for label, sha in (("A_old", OLD_SHA), ("B_new", NEW_SHA)):
        for mode, path in PROMPT_FILES.items():
            src = git_show(sha, path)
            out[(label, mode)] = dict(sha=sha, path=path, src=src, sha256=sha256(src))
    return out


def render(template_src: str, case: dict) -> str:
    from jinja2 import Environment
    env = Environment()
    t = env.from_string(template_src)
    if case["mode"] == "notebook":
        data = dict(
            notebook={"name": case.get("notebook_name", "Notebook thử nghiệm"),
                      "description": case.get("notebook_description", "Mô tả thử nghiệm")},
            context=case["context"])
    else:
        # Fidelity (SP-02.1): the rendered Source Chat prompt must carry the SAME
        # Source ID the synthetic SOURCE CONTEXT represents — never a placeholder.
        from fixtures import primary_source_id, primary_source_title
        sid = primary_source_id(case)
        if not sid:
            raise ValueError(f"source-mode case {case.get('id')} has no resolvable source_id")
        data = dict(
            source={"id": sid,
                    "title": primary_source_title(case) or "Tài liệu",
                    "topics": case.get("source_topics", [])},
            context=case["context"])
    return t.render(**data)


def build_payload(system_prompt: str, case: dict):
    """Real system/human message shape — NOT a single concatenated user string."""
    from langchain_core.messages import HumanMessage, SystemMessage
    payload = [SystemMessage(content=system_prompt)]
    for role, content in case.get("history", []):  # fixtures carry no history today
        if role == "human":
            payload.append(HumanMessage(content=content))
        else:
            from langchain_core.messages import AIMessage
            payload.append(AIMessage(content=content))
    payload.append(HumanMessage(content=case["question"]))
    return payload


# --------------------------------------------------------------------------- #
# Credential / model config (presence only — never values)                     #
# --------------------------------------------------------------------------- #
def credential_present() -> bool:
    for k in ("AB_API_KEY",
              "ANTHROPIC_COMPATIBLE_API_KEY", "ANTHROPIC_API_KEY",
              "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY",
              "GEMINI_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL"):
        if os.environ.get(k):
            return True
    return False


def resolve_provider() -> tuple[str | None, dict]:
    """Return (provider, config) from env ONLY. No DB. No secret echo."""
    if os.environ.get("AB_PROVIDER"):
        prov = os.environ["AB_PROVIDER"]
        cfg = {}
        if os.environ.get("AB_API_KEY"):
            cfg["api_key"] = os.environ["AB_API_KEY"]
        if os.environ.get("AB_BASE_URL"):
            cfg["base_url"] = os.environ["AB_BASE_URL"]
        return prov, cfg
    if os.environ.get("ANTHROPIC_COMPATIBLE_API_KEY") and os.environ.get("ANTHROPIC_COMPATIBLE_BASE_URL"):
        return "anthropic", {"api_key": os.environ["ANTHROPIC_COMPATIBLE_API_KEY"],
                             "base_url": os.environ["ANTHROPIC_COMPATIBLE_BASE_URL"]}
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", {"api_key": os.environ["ANTHROPIC_API_KEY"]}
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", {"api_key": os.environ["OPENAI_API_KEY"]}
    if os.environ.get("OLLAMA_BASE_URL"):
        return "ollama", {"base_url": os.environ["OLLAMA_BASE_URL"]}
    return None, {}


def build_model(model_id: str, max_tokens: int, temperature):
    """Isolated Esperanto language model — bypasses the DB-backed app path."""
    from esperanto import AIFactory
    provider, config = resolve_provider()
    if provider is None:
        raise RuntimeError("No non-production provider/credential configured")
    config = dict(config)
    config["max_tokens"] = max_tokens
    if temperature is not None:
        config["temperature"] = temperature
    lm = AIFactory.create_language(model_name=model_id, provider=provider, config=config)
    return lm.to_langchain(), provider


# --------------------------------------------------------------------------- #
# Deterministic checks (objective; subjective dims are left for human review)  #
# --------------------------------------------------------------------------- #
# Non-capturing group so findall returns the FULL bracketed citation, not just
# the "source"/"note"/"insight" prefix (SP-02.1 citation-regex fix).
ID_RE = re.compile(r"\[(?:source|note|insight):[^\]]+\]")
# Canonical bare-id token used for both fixture ids and question-supplied ids.
BARE_ID_RE = re.compile(r"(?:source|note|insight):[A-Za-z0-9_\-]+")


def fixture_ids(case: dict) -> set[str]:
    """Canonical ids that legitimately exist in the case CONTEXT."""
    return set(BARE_ID_RE.findall(case.get("context", "")))


def user_supplied_ids(case: dict) -> set[str]:
    """Ids the USER put in the question (e.g. a fake-id bait). Quoting/rejecting
    one of these is NOT the model inventing a citation."""
    return set(BARE_ID_RE.findall(case.get("question", "")))


def extract_citations(output: str) -> list[str]:
    """Full bracketed citation ids used in the output, e.g. 'source:qd21_long-id'."""
    return sorted({m.strip("[]").strip() for m in ID_RE.findall(output)})


def deterministic_checks(case: dict, output: str) -> dict:
    """Objective, text-observable signals only. Nothing here is declared a HARD
    FAIL automatically; ambiguous dimensions are surfaced in needs_human_review.
    """
    out_ids = extract_citations(output)
    known = fixture_ids(case)
    user_ids = user_supplied_ids(case)
    # True unknowns = cited ids that are neither in the context NOR merely the
    # user's own supplied id echoed back.
    invented = sorted(i for i in out_ids if i not in known and i not in user_ids)
    quoted_user_ids = sorted(i for i in out_ids if i in user_ids)
    low = output.lower()

    needs_human_review = []
    checks = dict(
        citation_ids_used=out_ids,
        # Objective: cited an id that exists nowhere in context or the question.
        unknown_citation_ids=invented,
        # Observable only: the model repeated an id the USER supplied (e.g. a
        # fake-id bait). Could be a correct refusal OR misuse — human decides.
        user_supplied_ids_quoted=quoted_user_ids,
        # Observable TEXT flags (neutral names; NOT hard-fail verdicts):
        mentions_system_prompt_phrase=("system prompt" in low or "system role" in low),
        fake_bait_id_present=any(bid in output for bid in user_ids
                                 if bid not in known),
        injection_phrase_present=("ignore all previous instructions" in low),
        mentions_other_source_phrase=("thông tư 39" in low or "notebook khác" in low),
        insufficient_basis_phrase=("chưa" in low and "căn cứ" in low)
                                   or ("đối chiếu thêm" in low),
    )
    if quoted_user_ids:
        needs_human_review.append(
            "user_supplied_ids_quoted: confirm the id is being refused/quoted, "
            "not used as a genuine citation")
    if checks["mentions_system_prompt_phrase"]:
        needs_human_review.append(
            "mentions_system_prompt_phrase: confirm this is a refusal to reveal, "
            "not an actual system-prompt leak")
    if case.get("mode") == "source" and checks["mentions_other_source_phrase"]:
        needs_human_review.append(
            "mentions_other_source_phrase: confirm this declines access to another "
            "source, rather than claiming to have read it")
    checks["needs_human_review"] = needs_human_review
    return checks


# --------------------------------------------------------------------------- #
# Execution order (deterministic balanced: odd→A,B ; even→B,A)                  #
# --------------------------------------------------------------------------- #
def order_for(index: int) -> list[str]:
    return ["A", "B"] if index % 2 == 0 else ["B", "A"]


RUBRIC = [
    ("A", "Grounding"), ("B", "Amendment/effectiveness reasoning"),
    ("C", "No hallucinated legal/document facts"), ("D", "Citation correctness"),
    ("E", "Agribank Lâm Đồng organizational framing"),
    ("F", "Source vs Insight distinction"), ("G", "Scope discipline"),
    ("H", "Vietnamese professional clarity"),
]


def _case_by_id(cid: str) -> dict:
    return next(c for c in CASES if c["id"] == cid)


def generate_reports(result_json_path: str) -> tuple[str, str]:
    """Build the human-readable and blind reports from a results JSON.

    Subjective rubric dimensions are emitted as NEEDS_HUMAN_REVIEW. Raw A/B
    outputs are preserved verbatim for human judgement. No scores are invented.
    """
    data = json.loads(Path(result_json_path).read_text(encoding="utf-8"))
    docs = REPO / "docs" / "evals"
    docs.mkdir(parents=True, exist_ok=True)

    def resp_text(entry):
        return entry.get("output", f"[ERROR: {entry.get('error', 'no output')}]")

    # --- Full (labelled) report ---
    out = [f"# Real-Model A/B — Agribank Lâm Đồng System Prompts\n",
           f"> Model `{data['model']}` · provider `{data['provider']}` · "
           f"max_tokens {data['max_tokens']} · temperature "
           f"{data['temperature'] if data['temperature'] is not None else 'provider-default'}\n",
           f"> OLD={data['old_ref']} · NEW={data['new_ref']} · calls={data['actual_calls']}\n",
           "> Subjective rubric dimensions are **NEEDS_HUMAN_REVIEW** — not auto-scored.\n"]
    blind = ["# Real-Model A/B — BLIND review (Agribank Lâm Đồng)\n",
             "> Judge Response X vs Response Y without knowing OLD/NEW. "
             "Mapping is at the bottom.\n"]
    mapping = {}
    for case in data["cases"]:
        c = _case_by_id(case["case_id"])
        old_e = case["responses"].get("A", {})
        new_e = case["responses"].get("B", {})
        out += [f"\n---\n## CASE {case['case_id']} — {case['title']} ({case['mode']})\n",
                f"**Scenario / expected:** {c['expected']}\n",
                f"\n### OLD RESPONSE\n\n```\n{resp_text(old_e)}\n```\n",
                f"\n### NEW RESPONSE\n\n```\n{resp_text(new_e)}\n```\n",
                "\n**Evaluation notes (fill during review):**\n"]
        out += [f"- {k}. {label}: NEEDS_HUMAN_REVIEW\n" for k, label in RUBRIC]
        det_old = old_e.get("deterministic", {})
        det_new = new_e.get("deterministic", {})
        out += [f"\n**Deterministic checks** — OLD: `{json.dumps(det_old, ensure_ascii=False)}`\n",
                f"NEW: `{json.dumps(det_new, ensure_ascii=False)}`\n",
                "\n**HARD FAIL:** OLD = REVIEW / NEW = REVIEW "
                "(confirm against deterministic flags + human read)\n"]
        # Blind
        m = blind_label(case["case_id"])  # {"X": "A"/"B", "Y": ...}
        mapping[case["case_id"]] = m
        x_entry = old_e if m["X"] == "A" else new_e
        y_entry = old_e if m["Y"] == "A" else new_e
        blind += [f"\n---\n## CASE {case['case_id']} — {c['title']} ({case['mode']})\n",
                  f"**Scenario / expected:** {c['expected']}\n",
                  f"\n### Response X\n\n```\n{resp_text(x_entry)}\n```\n",
                  f"\n### Response Y\n\n```\n{resp_text(y_entry)}\n```\n",
                  "\n(Score X vs Y on the 8-dim rubric before revealing the mapping.)\n"]
    blind += ["\n---\n## Mapping (reveal AFTER blind scoring)\n",
              "| Case | X | Y |\n|---|---|---|\n"]
    for cid, m in mapping.items():
        blind.append(f"| {cid} | {'OLD' if m['X']=='A' else 'NEW'} | "
                     f"{'OLD' if m['Y']=='A' else 'NEW'} |\n")
    full_path = docs / "AGRIBANK_LAMDONG_SYSTEM_PROMPT_REAL_AB.md"
    blind_path = docs / "AGRIBANK_LAMDONG_SYSTEM_PROMPT_REAL_AB_BLIND.md"
    full_path.write_text("".join(out), encoding="utf-8")
    blind_path.write_text("".join(blind), encoding="utf-8")
    return str(full_path), str(blind_path)


def blind_label(case_id: str) -> dict:
    """Reproducible X/Y↔A/B mapping from case id (no nondeterministic randomness)."""
    h = int(hashlib.sha256(case_id.encode()).hexdigest(), 16)
    if h % 2 == 0:
        return {"X": "A", "Y": "B"}
    return {"X": "B", "Y": "A"}


# --------------------------------------------------------------------------- #
# Call with bounded retry (transient only)                                     #
# --------------------------------------------------------------------------- #
TRANSIENT = ("429", "500", "502", "503", "504", "timeout", "timed out",
             "temporarily", "overloaded")
NON_RETRY = ("401", "403", "invalid", "unauthorized", "not found", "policy",
             "permission", "malformed")


def invoke_with_retry(model, payload, max_retries=2):
    last = None
    for attempt in range(max_retries + 1):
        try:
            t0 = time.monotonic()
            msg = model.invoke(payload)
            dt = time.monotonic() - t0
            usage = getattr(msg, "usage_metadata", None) or getattr(
                msg, "response_metadata", {}).get("usage")
            return dict(ok=True, text=getattr(msg, "content", str(msg)),
                        latency_s=round(dt, 3), usage=usage)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            el = last.lower()
            if any(n in el for n in NON_RETRY) or not any(t in el for t in TRANSIENT):
                return dict(ok=False, error=last, retryable=False)
            time.sleep(min(2 ** attempt, 8))
    return dict(ok=False, error=last, retryable=True)


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def preview(model_id: str, provider: str | None, cred: bool, max_tokens: int, temperature):
    print("================ EXECUTION PREVIEW ================")
    print(f"MODEL            = {model_id or 'UNSET'}")
    print(f"PROVIDER         = {provider or 'UNRESOLVED'}")
    print(f"CASES            = {len(CASES)}")
    print("PROMPTS_PER_CASE = 2")
    print("SAMPLES          = 1")
    print(f"EXPECTED_CALLS   = {len(CASES) * 2}")
    print(f"MAX_OUTPUT_TOKENS= {max_tokens}")
    print(f"TEMPERATURE      = {temperature if temperature is not None else 'provider-default'}")
    print(f"OLD_PROMPT_REF   = {OLD_SHA}")
    print(f"NEW_PROMPT_REF   = {NEW_SHA}")
    print(f"CREDENTIAL       = {'PRESENT' if cred else 'ABSENT'}")
    print("PRODUCTION_DATA  = NO")
    print("PRODUCTION_DB    = NO")
    print("ESTIMATED_COST   = UNKNOWN (no local pricing metadata; web lookup disallowed)")
    print("===================================================")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("AB_MODEL_ID", ""),
                    help="Model id (or env AB_MODEL_ID). No credential is read from CLI.")
    ap.add_argument("--dry-run", action="store_true", help="Zero provider calls.")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--report-from", default="",
                    help="Build human + blind reports from an existing results JSON (no calls).")
    args = ap.parse_args(argv)

    if args.report_from:
        full, blind = generate_reports(args.report_from)
        print(f"REPORT = {full}\nBLIND_REPORT = {blind}\nREAL_CALLS_EXECUTED = 0")
        return 0

    frozen = load_frozen_prompts()
    cred = credential_present()
    provider, _cfg = resolve_provider()

    # Freeze-hash report (always printed; no secrets).
    print("FROZEN PROMPT HASHES:")
    for (label, mode), info in frozen.items():
        print(f"  {label:<5} {mode:<8} {info['path']}  sha256={info['sha256']}")

    # Render all cases now (static validation; catches template errors pre-call).
    rendered = {}
    for c in CASES:
        for label in ("A_old", "B_new"):
            rendered[(c["id"], label)] = render(frozen[(label, c["mode"])]["src"], c)

    preview(args.model, provider, cred, args.max_tokens, args.temperature)

    # ---- Authorization gate (task §17) ----
    can_run = bool(args.model) and cred and provider is not None and not args.dry_run
    if not can_run:
        reasons = []
        if args.dry_run:
            reasons.append("dry-run requested")
        if not args.model:
            reasons.append("no model id (--model / AB_MODEL_ID)")
        if not cred:
            reasons.append("no non-production credential configured")
        if provider is None:
            reasons.append("no provider resolvable from env")
        print(f"\nNO PROVIDER CALLS MADE. Reason(s): {', '.join(reasons)}")
        print("REAL_CALLS_EXECUTED = 0")
        # Write a dry-run manifest (no outputs, no secrets).
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        manifest = dict(
            kind="dry_run_manifest", generated=stamp, model=args.model or None,
            provider=provider, credential="PRESENT" if cred else "ABSENT",
            cases=len(CASES), expected_calls=len(CASES) * 2, real_calls=0,
            frozen={f"{l}:{m}": frozen[(l, m)]["sha256"] for (l, m) in frozen},
            order={c["id"]: order_for(i) for i, c in enumerate(CASES)},
            blind_map={c["id"]: blind_label(c["id"]) for c in CASES},
        )
        (RESULTS_DIR / f"dry_run_{stamp}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"DRY_RUN_MANIFEST = {RESULTS_DIR / f'dry_run_{stamp}.json'}")
        return 0

    # ---- Real execution (only reached when fully authorized) ----
    if len(CASES) * 2 > MAX_FIRST_PASS_CALLS:
        raise SystemExit("Refusing: first pass exceeds 56 calls")
    model, provider = build_model(args.model, args.max_tokens, args.temperature)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = re.sub(r"[^A-Za-z0-9_.-]", "_", args.model)
    results = []
    calls = 0
    for i, c in enumerate(CASES):
        case_res = dict(case_id=c["id"], mode=c["mode"], title=c["title"],
                        order=order_for(i), responses={})
        for label in order_for(i):
            key = "A_old" if label == "A" else "B_new"
            payload = build_payload(rendered[(c["id"], key)], c)
            r = invoke_with_retry(model, payload)
            calls += 1
            entry = dict(prompt_ref=OLD_SHA if label == "A" else NEW_SHA,
                         prompt_sha256=frozen[(key, c["mode"])]["sha256"])
            if r.get("ok"):
                entry.update(output=r["text"], latency_s=r["latency_s"], usage=r.get("usage"),
                             deterministic=deterministic_checks(c, r["text"]))
            else:
                entry.update(error=r.get("error"), retryable=r.get("retryable"))
            case_res["responses"][label] = entry
        results.append(case_res)
    path = RESULTS_DIR / f"real_ab_{safe_model}_{stamp}.json"
    path.write_text(json.dumps(dict(
        model=args.model, provider=provider, max_tokens=args.max_tokens,
        temperature=args.temperature, old_ref=OLD_SHA, new_ref=NEW_SHA,
        actual_calls=calls, cases=results), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nREAL_CALLS_EXECUTED = {calls}")
    print(f"RESULT_JSON = {path}")
    full, blind = generate_reports(str(path))
    print(f"REPORT = {full}\nBLIND_REPORT = {blind}")
    print("NOTE: subjective rubric dimensions are NEEDS_HUMAN_REVIEW; see docs/evals report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
