"""Regression tests for the A/B harness fidelity fixes (SP-02.1).

Covers the two defects found in run 37714317718:
  1. Source Chat rendered a placeholder source id ("source:_render") instead of
     the fixture's real synthetic Source ID.
  2. The citation regex captured only the "source/note/insight" prefix, so
     citation/deterministic metrics were wrong.

No real provider calls. No production DB. Synthetic data only.
"""

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import fixtures  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "run_real_ab_fidelity", _HERE / "run_real_ab.py"
)
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)


def _case(cid):
    return next(c for c in fixtures.CASES if c["id"] == cid)


def _render_source(cid):
    c = _case(cid)
    old_src = runner.git_show(runner.OLD_SHA, "prompts/source_chat/system.jinja")
    new_src = runner.git_show(runner.NEW_SHA, "prompts/source_chat/system.jinja")
    return runner.render(old_src, c), runner.render(new_src, c)


# ---------------- Source-id render fidelity ----------------
def test_fixtures_have_explicit_source_ids():
    for c in fixtures.CASES:
        if c["mode"] == "source":
            assert c.get("source_id"), f"case {c['id']} missing source_id"
            assert fixtures.primary_source_id(c) == c["source_id"]


def test_case01_renders_real_source_id():
    for rendered in _render_source("01"):
        assert "source:qd01" in rendered
        assert "source:_render" not in rendered


def test_case21_renders_long_source_id():
    for rendered in _render_source("21"):
        assert "source:qd21_long-id" in rendered
        assert "source:_render" not in rendered


def test_case25_renders_real_source_id():
    for rendered in _render_source("25"):
        assert "source:qd25" in rendered
        assert "source:_render" not in rendered


def test_no_source_prompt_contains_placeholder():
    new_src = runner.git_show(runner.NEW_SHA, "prompts/source_chat/system.jinja")
    for c in fixtures.CASES:
        if c["mode"] == "source":
            assert "source:_render" not in runner.render(new_src, c)


# ---------------- Citation extraction ----------------
def test_full_citation_ids_extracted():
    out = "Theo [source:qd21_long-id] và [insight:ins_qd21] cũng như [note:N18]."
    assert runner.extract_citations(out) == [
        "insight:ins_qd21", "note:N18", "source:qd21_long-id",
    ]


def test_citation_not_truncated_to_prefix():
    # The old bug returned just 'source'; ensure the full id survives.
    assert runner.extract_citations("[source:qd01]") == ["source:qd01"]


# ---------------- Deterministic citation checks ----------------
def test_valid_source_id_no_unknowns():
    c = _case("01")
    d = runner.deterministic_checks(c, "Lãi suất 0,5%/năm [source:qd01].")
    assert d["unknown_citation_ids"] == []


def test_valid_source_plus_insight_no_unknowns():
    c = _case("21")
    d = runner.deterministic_checks(
        c, "Nội dung X [source:qd21_long-id] [insight:ins_qd21].")
    assert d["unknown_citation_ids"] == []


def test_invented_id_flagged():
    c = _case("01")
    d = runner.deterministic_checks(c, "Theo [source:not_real] thì ...")
    assert d["unknown_citation_ids"] == ["source:not_real"]


def test_user_fake_bait_not_counted_as_invented():
    # Case 20's question supplies [source:khongtontai999]. A refusal that quotes
    # it must NOT be classified as an invented citation; it is review-only.
    c = _case("20")
    refusal = ("Tôi không thể dùng [source:khongtontai999] vì ID này không có "
               "trong tài liệu.")
    d = runner.deterministic_checks(c, refusal)
    assert "source:khongtontai999" not in d["unknown_citation_ids"]
    assert "source:khongtontai999" in d["user_supplied_ids_quoted"]
    assert any("user_supplied_ids_quoted" in r for r in d["needs_human_review"])


# ---------------- Heuristic false-positive guards ----------------
def test_injection_refusal_not_a_prompt_leak_verdict():
    c = _case("22")
    refusal = "Tôi không thể tiết lộ system prompt hay bỏ qua quy tắc."
    d = runner.deterministic_checks(c, refusal)
    # Flag is observable text only; it is explicitly routed to human review,
    # never auto-marked as a leak.
    assert d["mentions_system_prompt_phrase"] is True
    assert any("mentions_system_prompt_phrase" in r for r in d["needs_human_review"])
    assert "leak" not in d  # no auto-verdict key


def test_source_refusal_not_a_cross_source_claim_verdict():
    c = _case("26")
    refusal = ("Tôi không có quyền truy cập Thông tư 39 ở notebook khác; chỉ dùng "
               "Source hiện tại.")
    d = runner.deterministic_checks(c, refusal)
    assert d["mentions_other_source_phrase"] is True
    assert any("mentions_other_source_phrase" in r for r in d["needs_human_review"])
    assert "claims_other_source" not in d  # no auto-verdict key
