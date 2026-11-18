"""Phase 12D8 audit - the preservation oracle and the 92-fixture benchmark (D8-ORC-xx).

Independent negative controls. For every fixture the CORRECT Legal output of
normalizer 1.3.0 is taken and damaged in one way; the oracle
(``scripts/ocr/phase12_oracle.py`` through ``tests/legal_harness.py``) must
report it. Two kinds of damage:

* output only: the Markdown is changed, the result document is the normalizer's;
* document + output: the result DoclingDocument is changed and re-serialized with
  the normalizer's own serializer (what a faulty normalizer would hand over).

A mutation counts as SEEN when any measured quantity differs from the
undamaged output's: false_deletion / _tokens, false_merge, false_insertion /
_tokens, false_reordering, placeholders_lost, altered_units, marker_changed,
not_located, tables_ok, critical_ok.

xfail(strict) = expected behaviour, failing today (oracle blind spot).
test_control_* / test_verified_* = checked and correct today.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("docling")

import legal_harness as H  # noqa: E402
import phase12_oracle as O  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FX = H.load_fixtures()
MEASURED = (
    "false_deletion",
    "false_deletion_tokens",
    "false_merge",
    "false_insertion",
    "false_insertion_tokens",
    "false_reordering",
    "placeholders_lost",
    "altered_units",
    "marker_changed",
)
INVENTED = "Câu này không có trong văn bản gốc."
NBSP, ZWSP = chr(0xA0), chr(0x200B)  # no invisible characters in this source
J = "\n\n".join


def _verdict(fx, markdown, document):
    p = H.preservation(fx, H.legal_lines(markdown), markdown, document=document)
    seen = {k: p[k] for k in MEASURED if p[k]}
    if p["not_located"]:
        seen["not_located"] = len(p["not_located"])
    if not p["tables_ok"]:
        seen["tables_ok"] = False
    if not p["critical_ok"]:
        seen["critical_ok"] = False
    return seen


def _serialize(document):
    return N._build_serializer(document, set()).serialize().text


class _Case:
    def __init__(self, fx):
        self.fx = fx
        self.name = fx["name"]
        self.doc = H.build_document(fx)
        self.res = N.normalize_document(self.doc, evidence=H.evidence(self.doc))
        self.md = self.res.content
        self.blocks = self.md.split("\n\n")
        self.base = _verdict(fx, self.md, self.res.document)
        self.units = O.expected_units(fx)
        self.optional = {
            O._norm(u["text"]) for u in self.units if u["gt"] in O.OPTIONAL_GT
        }

    def seen(self, markdown, document=None):
        return _verdict(self.fx, markdown, document or self.res.document) != self.base

    # document + output mutations ------------------------------------------- #
    def copy(self):
        from docling_core.types.doc.document import ContentLayer

        work = self.res.document.model_copy(deep=True)
        items = {
            it.self_ref: it
            for it, _ in work.iterate_items(
                with_groups=False,
                traverse_pictures=True,
                included_content_layers={ContentLayer.BODY},
            )
        }
        return work, items

    def owners(self):
        """self_ref -> declared units the body item carries (by provenance)."""
        view = O._DocView(self.res.document, True)
        out: dict[str, list] = {}
        for u in self.units:
            for item, _ in view.holders(u):
                if item.content_layer == view.BODY:
                    out.setdefault(item.self_ref, []).append(u)
                    break
        return out

    def required_text_items(self):
        from docling_core.types.doc.document import ContentLayer, TableItem, TextItem

        owners = self.owners()
        out = []
        for it, _ in self.res.document.iterate_items(
            with_groups=False,
            traverse_pictures=True,
            included_content_layers={ContentLayer.BODY},
        ):
            if (
                isinstance(it, TextItem)
                and not isinstance(it, TableItem)
                and (it.text or "").strip()
                and any(u["gt"] in O.REQUIRED_GT for u in owners.get(it.self_ref, []))
            ):
                out.append(it)
        return out

    def seen_doc(self, work):
        base = _verdict(self.fx, _serialize(self.res.document), self.res.document)
        return _verdict(self.fx, _serialize(work), work) != base


@pytest.fixture(scope="module")
def cases():
    return [_Case(fx) for fx in FX.FIXTURES]


def _is_text(block: str) -> bool:
    return bool(block.strip()) and not block.lstrip().startswith("|") and (
        block.strip() != O.PLACEHOLDER
    )


def _sample(seq, n=4):
    """At most ``n`` evenly spread elements (keeps the module fast)."""
    seq = list(seq)
    if len(seq) <= n:
        return seq
    step = (len(seq) - 1) / (n - 1)
    return [seq[round(i * step)] for i in range(n)]


def _rate(results, minimum):
    found, total = sum(1 for r in results if r), len(results)
    assert total >= minimum, (found, total)
    return found, total


# --------------------------------------------------------------------------- #
# Baseline and benchmark
# --------------------------------------------------------------------------- #


def test_control_baseline_92_fixtures(cases):
    assert len(cases) == 92
    dirty = {c.name: c.base for c in cases if c.base}
    # only Docling's own reading order, and only where the fixture documents it
    assert set(dirty) == {
        "f12_two_columns",
        "d5_f02_voucher_numbers_beside_label",
        "d5_f02_voucher_numbers_alone_top_right",
    }
    for name, seen in dirty.items():
        assert set(seen) == {"false_reordering"}
        assert FX.by_name(name).get("upstream_reordering")


def test_control_committed_benchmark_reproduces_on_head(cases):
    """docs/review/phase12d9/benchmark_legal_1_3_1.json, every row and the
    aggregate, without the timing / memory fields.

    Phase 12D9: the audit pinned the 12D7 benchmark of normalizer 1.3.0
    (``docs/review/phase12d7/benchmark_legal_1_3_0.json``, kept unchanged as
    evidence). D8-01 / D8-02 / D8-03 changed the code (owner decision of
    12D9), so the benchmark was produced again for 1.3.1 and committed; the
    only differences to 1.3.0 outside timing are in Standard
    (``altered_units`` 1 -> 0, ``critical_fields`` 84 -> 85 of 89: the hyphen
    of ``d5_r201_hyphen_lowercase`` is now kept)."""
    import phase12_benchmark as B

    # was: docs/review/phase12d7/benchmark_legal_1_3_0.json
    committed = json.loads(
        (ROOT / "docs/review/phase12d9/benchmark_legal_1_3_1.json").read_text("utf-8")
    )
    timing = {"ms_median", "peak_kib", "ms_total", "peak_kib_max"}

    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in timing}
        return [strip(v) for v in x] if isinstance(x, list) else x

    assert committed["fixtures"] == 92
    # was: == "1.3.0" (12D7 benchmark)
    assert committed["normalizer_version"] == N.NORMALIZER_VERSION == "1.3.1"
    rows = []
    for c in cases:
        row = {"name": c.name, "pages": len(c.fx["pages"])}
        row["standard"] = B.measure(
            c.fx, c.doc.export_to_markdown(), legal=False, document=c.doc
        )
        row["legal"] = B.measure(c.fx, c.md, legal=True, document=c.res.document)
        row["legal"]["counts"] = c.res.counts
        row["legal"]["warnings"] = sorted({w["code"] for w in c.res.warnings})
        if c.fx.get("table_identical"):
            row["legal"]["tables_identical"] = all(
                t.export_to_markdown(c.doc) in c.md for t in c.doc.tables
            )
        row["standard"]["ms_median"] = row["legal"]["ms_median"] = 0.0
        row["legal"]["peak_kib"] = 0.0
        rows.append(row)
    assert strip(rows) == strip(committed["rows"])
    assert strip(B.aggregate(rows)) == strip(committed["aggregate"])
    legal = committed["aggregate"]["legal"]
    assert legal["false_deletion_units"] == legal["false_insertion"] == 0
    # was: == 14 (len - LIS). Phase 12D9 (D8-ORC-05): false_reordering counts
    # the pairs shown in the wrong order (Kendall distance) - same 3 upstream
    # fixtures, every pair counted (len - LIS kept as false_reordering_lis)
    assert legal["false_reordering"] == 35
    assert legal["false_deletion_units"] == legal["false_insertion"] == 0


def test_verified_ground_truth_is_declared_not_generated():
    """No fixture expectation is computed from an output of the system: the
    fixture module imports nothing but typing, and the oracle never imports
    the normalizer."""
    import ast

    src = (ROOT / "tests/fixtures/legal/legal_fixtures.py").read_text("utf-8")
    imports = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name)
        for n in ast.walk(ast.parse(src))
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in n.names
    }
    assert imports == {"__future__", "typing"}
    oracle = (ROOT / "scripts/ocr/phase12_oracle.py").read_text("utf-8")
    assert "legal_normalizer" not in oracle and "open_notebook" not in oracle


# --------------------------------------------------------------------------- #
# Controls, output only
# --------------------------------------------------------------------------- #


def test_control_occurrence_count_one_copy_of_a_repeated_line_deleted(cases):
    """Multiset: a required line shown 3 times must be shown 3 times."""
    results = []
    for c in cases:
        count = Counter(c.blocks)
        for i, b in enumerate(c.blocks):
            if count[b] >= 2 and O._norm(b) not in c.optional:
                results.append(c.seen(J(c.blocks[:i] + c.blocks[i + 1 :])))
    found, total = _rate(results, 60)
    assert found == total, (found, total)


def test_control_deleted_or_duplicated_block(cases):
    deleted, duplicated = [], []
    for c in cases:
        for i in _sample(range(len(c.blocks)), 5):
            b = c.blocks[i]
            if O._norm(b) not in c.optional and b.strip() != O.PLACEHOLDER:
                deleted.append(c.seen(J(c.blocks[:i] + c.blocks[i + 1 :])))
            if b.strip() != O.PLACEHOLDER:
                duplicated.append(c.seen(J(c.blocks[:i] + [b, b] + c.blocks[i + 1 :])))
    for results in (deleted, duplicated):
        found, total = _rate(results, 300)
        assert found == total, (found, total)


def test_control_reading_order_two_adjacent_blocks_swapped(cases):
    results = []
    for c in cases:
        if c.fx.get("upstream_reordering"):
            continue  # see test_reordering_inside_an_already_reordered_document
        for i in _sample(range(len(c.blocks) - 1), 5):
            a, b = c.blocks[i], c.blocks[i + 1]
            if a == b or O.PLACEHOLDER in (a.strip(), b.strip()):
                continue
            results.append(c.seen(J(c.blocks[:i] + [b, a] + c.blocks[i + 2 :])))
    found, total = _rate(results, 300)
    assert found == total, (found, total)


def test_control_changed_characters(cases):
    """Điều 12 -> Điều 13, 0001 -> 1, a trailing dot, a clause marker, one
    letter, one capital, NFC -> NFD: every one is seen."""
    kinds: dict[str, list[bool]] = {}

    def run(kind, c, i, new):
        if new != c.blocks[i]:
            kinds.setdefault(kind, []).append(
                c.seen(J(c.blocks[:i] + [new] + c.blocks[i + 1 :]))
            )

    for c in cases:
        for i in _sample([k for k, b in enumerate(c.blocks) if _is_text(b)], 5):
            b = c.blocks[i]
            m = re.search(r"\d", b)
            if m:
                run("digit", c, i, b[: m.start()] + str((int(m.group()) + 1) % 10) + b[m.end() :])
            m = re.search(r"(?<![\d.,/])0+(?=\d)", b)
            if m:
                run("leading zero", c, i, b[: m.start()] + b[m.end() :])
            if b.rstrip().endswith("."):
                run("trailing dot", c, i, b.rstrip()[:-1])
            m = re.match(r"^(\d+)\. ", b)
            if m:
                run("marker dot", c, i, m.group(1) + " " + b[m.end() :])
                run("marker", c, i, b[m.end() :])
            elif not b.startswith("#"):
                run("invented marker", c, i, "7. " + b)
            m = re.search(r"[A-Za-zÀ-ỹ]{2,}", b)
            if m:
                w = m.group(0)
                run("letter", c, i, b[: m.end() - 1] + ("x" if w[-1] != "x" else "y") + b[m.end() :])
                run("case", c, i, b[: m.start()] + w[0].swapcase() + b[m.start() + 1 :])
            run("nfd", c, i, unicodedata.normalize("NFD", b))
            glue = [s.start() for s in re.finditer(r"(?<=\S) (?=\S)", b)]
            if glue:
                k = glue[len(glue) // 2]
                run("words glued", c, i, b[:k] + b[k + 1 :])
                run("zero-width space", c, i, b[:k] + ZWSP + b[k:])
    minimum = {"leading zero": 15, "marker dot": 15, "marker": 15}
    assert set(kinds) == {
        "digit", "leading zero", "trailing dot", "marker dot", "marker",
        "invented marker", "letter", "case", "nfd", "words glued", "zero-width space",
    }  # fmt: skip
    for kind, results in kinds.items():
        found, total = _rate(results, minimum.get(kind, 150))
        assert found == total, (kind, found, total)


def test_control_table_cell_row_and_placeholder_in_the_output(cases):
    cell, row, swapped, placeholder = [], [], [], []
    for c in cases:
        for i, b in enumerate(c.blocks):
            if b.strip() == O.PLACEHOLDER:
                placeholder.append(c.seen(J(c.blocks[:i] + c.blocks[i + 1 :])))
            if not b.lstrip().startswith("|"):
                continue
            rows = b.split("\n")
            data = [r for r in range(len(rows)) if not set(rows[r].strip()) <= set("|-: ")]
            for r in data:
                cells = rows[r].split("|")
                for k in range(1, len(cells) - 1):
                    if cells[k].strip():
                        new = "|".join(cells[:k] + [" "] + cells[k + 1 :])
                        cell.append(c.seen(J(c.blocks[:i] + ["\n".join(rows[:r] + [new] + rows[r + 1 :])] + c.blocks[i + 1 :])))
                row.append(c.seen(J(c.blocks[:i] + ["\n".join(rows[:r] + rows[r + 1 :])] + c.blocks[i + 1 :])))
            for r1, r2 in zip(data[1:], data[2:]):
                new_rows = list(rows)
                new_rows[r1], new_rows[r2] = rows[r2], rows[r1]
                swapped.append(c.seen(J(c.blocks[:i] + ["\n".join(new_rows)] + c.blocks[i + 1 :])))
    for results, minimum in ((cell, 30), (row, 10), (swapped, 3), (placeholder, 9)):
        found, total = _rate(results, minimum)
        assert found == total, (found, total)


def test_control_merge_and_invented_text_in_the_output(cases):
    merged, cross_page, inserted, comment = [], [], [], []
    for c in cases:
        page_of: dict[str, set[int]] = {}
        for u in c.units:
            page_of.setdefault(O._norm(u["text"]), set()).add(u["page"])
        for i in _sample(range(len(c.blocks) - 1), 6):
            a, b = c.blocks[i], c.blocks[i + 1]
            if not (_is_text(a) and _is_text(b)):
                continue
            b_text = re.sub(r"^#+ ", "", b)
            seen = c.seen(J(c.blocks[:i] + [f"{a} {b_text}"] + c.blocks[i + 2 :]))
            merged.append(seen)
            pa = page_of.get(O._norm(re.sub(r"^#+ ", "", a)), set())
            pb = page_of.get(O._norm(b_text), set())
            if len(pa) == 1 and len(pb) == 1 and pa != pb:
                cross_page.append(seen)
        for i in _sample(range(len(c.blocks) + 1), 4):
            inserted.append(c.seen(J(c.blocks[:i] + [INVENTED] + c.blocks[i:])))
            comment.append(c.seen(J(c.blocks[:i] + [f"<!-- {INVENTED} -->"] + c.blocks[i:])))
    for results, minimum in ((merged, 300), (cross_page, 40), (inserted, 300), (comment, 300)):
        found, total = _rate(results, minimum)
        assert found == total, (found, total)


# --------------------------------------------------------------------------- #
# Controls, document + output (source identity: page, box, item text)
# --------------------------------------------------------------------------- #


def test_control_identity_page_box_text_and_deletion(cases):
    """The same text on another page, in a shifted box, with one digit changed,
    removed from the document, or exchanged between two items is seen."""
    kinds: dict[str, list[bool]] = {}
    for c in cases:
        items = c.required_text_items()
        for it in _sample(items, 3):
            work, m = c.copy()
            x = m[it.self_ref]
            if x.prov and len(c.fx["pages"]) > 1:
                x.prov[0].page_no = x.prov[0].page_no % len(c.fx["pages"]) + 1
                kinds.setdefault("page", []).append(c.seen_doc(work))
            work, m = c.copy()
            x = m[it.self_ref]
            if x.prov:
                x.prov[0].bbox.l += 5
                x.prov[0].bbox.r += 5
                kinds.setdefault("box", []).append(c.seen_doc(work))
            d = re.search(r"[0-9]", it.text)
            if d:
                work, m = c.copy()
                m[it.self_ref].text = (
                    it.text[: d.start()] + str((int(d.group()) + 1) % 10) + it.text[d.end() :]
                )
                kinds.setdefault("digit", []).append(c.seen_doc(work))
            work, m = c.copy()
            work.delete_items(node_items=[m[it.self_ref]])
            kinds.setdefault("deleted", []).append(c.seen_doc(work))
        for a, b in _sample(list(zip(items, items[1:])), 3):
            if a.text == b.text:
                continue
            work, m = c.copy()
            m[a.self_ref].text, m[b.self_ref].text = b.text, a.text
            kinds.setdefault("texts exchanged", []).append(c.seen_doc(work))
    minimum = {"page": 150, "box": 200, "digit": 100, "deleted": 200, "texts exchanged": 150}
    assert set(kinds) == set(minimum)
    for kind, results in kinds.items():
        found, total = _rate(results, minimum[kind])
        assert found == total, (kind, found, total)


def test_control_identity_undeclared_merge_and_invented_item(cases):
    from docling_core.types.doc.document import ContentLayer, ListItem
    from docling_core.types.doc.labels import DocItemLabel

    merged, invented = [], []
    for c in cases:
        owners = c.owners()
        preds = O._predecessors(c.units)
        items = [it for it in c.required_text_items() if not isinstance(it, ListItem)]
        for a, b in _sample(list(zip(items, items[1:])), 3):
            ua, ub = owners[a.self_ref], owners[b.self_ref]
            if len(ua) == 1 and len(ub) == 1 and preds.get(ub[0]["id"]) == ua[0]["id"]:
                continue  # a declared join: see test_cross_page_join_...
            work, m = c.copy()
            x, y = m[a.self_ref], m[b.self_ref]
            x.text = f"{x.text} {y.text}"
            x.prov.extend(y.prov)
            y.content_layer = ContentLayer.INVISIBLE
            merged.append(c.seen_doc(work))
        work, _ = c.copy()
        work.add_text(label=DocItemLabel.TEXT, text=INVENTED)
        invented.append(c.seen_doc(work))
    for results, minimum in ((merged, 150), (invented, 92)):
        found, total = _rate(results, minimum)
        assert found == total, (found, total)


def test_verified_whitespace_only_changes_are_not_measured(cases):
    """Judgement, not a defect: the oracle compares whitespace-collapsed text
    (``_norm``), like an HTML renderer. A doubled space, a TAB or a no-break
    space inside a paragraph changes none of the nine counters; only a declared
    ``protected`` value that contains the space notices (critical_ok). A
    REMOVED space is seen (control above: "words glued")."""
    results, critical = [], 0
    for c in cases:
        for i in _sample([k for k, b in enumerate(c.blocks) if _is_text(b)], 3):
            b = c.blocks[i]
            gaps = [s.start() for s in re.finditer(r"(?<=\w) (?=\w)", b)]
            if not gaps or b.startswith("#"):
                continue
            k = gaps[len(gaps) // 2]
            for ws in ("  ", "\t", NBSP):
                md = J(c.blocks[:i] + [b[:k] + ws + b[k + 1 :]] + c.blocks[i + 1 :])
                seen = _verdict(c.fx, md, c.res.document)
                critical += "critical_ok" in seen
                seen.pop("critical_ok", None)
                results.append(seen != c.base)
    assert len(results) >= 400 and not any(results)
    assert 0 < critical < len(results) // 4


# --------------------------------------------------------------------------- #
# Blind spots
# --------------------------------------------------------------------------- #


# was: xfail(strict) D8-ORC-01 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_table_cells_exchanged_in_document_and_output_are_seen(cases):
    from docling_core.types.doc.document import TableItem

    results = []
    for c in cases:
        for ref, it in c.copy()[1].items():
            if not isinstance(it, TableItem):
                continue
            n = len(it.data.table_cells)
            for i in range(n):
                for j in range(i + 1, n):
                    if it.data.table_cells[i].text == it.data.table_cells[j].text:
                        continue
                    work, m = c.copy()
                    cells = m[ref].data.table_cells
                    cells[i].text, cells[j].text = cells[j].text, cells[i].text
                    results.append(c.seen_doc(work))
    found, total = _rate(results, 100)
    assert found == total, (found, total)  # today 0 / 138 (3 tables)


# was: xfail(strict) D8-ORC-01 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_emptied_table_cell_is_seen_even_when_its_text_occurs_elsewhere(cases):
    from docling_core.types.doc.document import TableItem

    c = next(x for x in cases if x.name == "f10_table_across_pages")
    results = {}
    for ref, it in c.copy()[1].items():
        if isinstance(it, TableItem):
            for i, cell in enumerate(it.data.table_cells):
                work, m = c.copy()
                m[ref].data.table_cells[i].text = ""
                results[(ref, i, cell.text)] = c.seen_doc(work)
    assert len(results) >= 10
    assert all(results.values()), [k for k, v in results.items() if not v]


# was: xfail(strict) D8-ORC-02 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
@pytest.mark.parametrize("shape", ["```\n{}\n```", "    {}"])
def test_invented_text_in_a_code_block_is_seen(cases, shape):
    results = []
    for c in cases:
        for i in _sample(range(len(c.blocks) + 1), 4):
            block = shape.format(INVENTED)
            results.append(c.seen(J(c.blocks[:i] + [block] + c.blocks[i:])))
    found, total = _rate(results, 300)
    assert found == total, (found, total)


def test_verified_code_blocks_are_shown_by_the_reference_renderer():
    """...and they ARE displayed: markdown-it produces a block for them, and
    legal_display_markdown leaves fences / indentation alone."""
    from markdown_it import MarkdownIt

    for block in (f"```\n{INVENTED}\n```", f"    {INVENTED}"):
        shown = H.legal_display_markdown(f"Điều 1.\n\n{block}\n\nĐiều 2.")
        tokens = MarkdownIt("commonmark").parse(shown)
        code = [t for t in tokens if t.type in ("fence", "code_block")]
        assert len(code) == 1 and INVENTED in code[0].content
        # was: legal_lines(...) == ["Điều 1.", "Điều 2."] - Phase 12D9 (D8-ORC-02):
        # the oracle's display now shows the code block's lines, as the renderer does
        assert H.legal_lines(f"Điều 1.\n\n{block}\n\nĐiều 2.") == [
            "Điều 1.",
            INVENTED,
            "Điều 2.",
        ]


# was: xfail(strict) D8-ORC-03 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_removed_artifact_text_reinserted_as_a_new_item_is_seen(cases):
    from docling_core.types.doc.labels import DocItemLabel

    results = []
    for c in cases:
        shown = H.legal_lines(_serialize(c.res.document))
        for u in c.units:
            if u["gt"] in O.OPTIONAL_GT and u["kind"] == "text" and u["text"] not in shown:
                work, _ = c.copy()
                work.add_text(label=DocItemLabel.TEXT, text=u["text"])
                # put it first: far from where the artifact was
                work.body.children.insert(0, work.body.children.pop())
                results.append(c.seen_doc(work))
    found, total = _rate(results, 50)
    assert found == total, (found, total)


# was: xfail(strict) D8-ORC-04 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_changed_block_structure_is_seen(cases):
    results = []
    for c in cases:
        for i in _sample([k for k, b in enumerate(c.blocks) if _is_text(b)], 4):
            b = c.blocks[i]
            new = re.sub(r"^#+ ", "", b) if b.startswith("#") else f"## {b}"
            results.append(c.seen(J(c.blocks[:i] + [new] + c.blocks[i + 1 :])))
    found, total = _rate(results, 300)
    assert found == total, (found, total)


# was: xfail(strict) D8-ORC-05 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_reordering_inside_an_already_reordered_document_is_seen(cases):
    results = []
    for c in cases:
        if not c.base.get("false_reordering"):
            continue
        for i in range(len(c.blocks) - 1):
            a, b = c.blocks[i], c.blocks[i + 1]
            if a != b and _is_text(a) and _is_text(b):
                results.append(c.seen(J(c.blocks[:i] + [b, a] + c.blocks[i + 2 :])))
    found, total = _rate(results, 30)
    assert found == total, (found, total)  # today 15 / 37


# was: xfail(strict) D8-ORC-06 - fixed in Phase 12D9 (phase12_oracle / phase12_metrics)
def test_cross_page_join_of_a_declared_pair_is_an_error(cases):
    from docling_core.types.doc.document import ContentLayer

    results = {}
    for c in cases:
        for b_id, a_id in O._predecessors(c.units).items():
            ua = next(u for u in c.units if u["id"] == a_id)
            ub = next(u for u in c.units if u["id"] == b_id)
            if ua["page"] == ub["page"]:
                continue
            work, _ = c.copy()
            view = O._DocView(work, True)
            x = next(i for i, _ in view.holders(ua) if i.content_layer == view.BODY)
            y = next(i for i, _ in view.holders(ub) if i.content_layer == view.BODY)
            x.text = f"{x.text} {y.text}"
            x.prov.extend(y.prov)
            y.content_layer = ContentLayer.INVISIBLE
            p = H.preservation(
                c.fx, H.legal_lines(_serialize(work)), _serialize(work), document=work
            )
            assert p["joins_made"] == 1  # the oracle does notice the join...
            results[(c.name, a_id, b_id)] = bool(
                p["false_merge"] or p["altered_units"] or p["false_deletion"]
            )
    assert len(results) == 8
    assert all(results.values()), [k for k, v in results.items() if not v]
