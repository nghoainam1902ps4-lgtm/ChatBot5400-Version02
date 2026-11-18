"""Phase 12D5 (12D5A, findings R2-14 / T-01 / T-03): the oracle must SEE damage.

Systematic negative controls: start from an undamaged output, inject one defect
at every place where it applies, and require the oracle to report it - 100 %,
for every defect class the Phase 12D4 re-review found the old oracle blind to
(swap with an artifact line 0/35, insertion of an artifact's text 19/43, a
required line moved across artifacts / placeholders only 0/12, a clause number
deleted while its twin page number stays) and for the classes the Phase 12D5
directive names: wrong deletion, wrong insertion, reordering, wrong join, lost
clause number, lost voucher number, one lost occurrence of repeated content.

Two attribution modes are exercised:
* identity - the oracle is given the DoclingDocument; damage is injected into the
  document AND the displayed lines consistently (what a faulty normalizer would
  produce);
* text - lines only (worst-case attribution of aliased lines).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("docling")

sys.path.insert(0, str(Path(__file__).parent))

import legal_harness as H  # noqa: E402
import phase12_oracle as O  # noqa: E402

FX = H.load_fixtures()
ERRORS = (
    "false_deletion",
    "false_merge",
    "false_insertion",
    "false_reordering",
    "placeholders_lost",
    "altered_units",
    "marker_changed",
)


def _errors(p):
    return {k: p[k] for k in ERRORS if p[k]}


def _base(fx):
    doc = H.build_document(fx)
    lines = O.faithful_lines(doc)
    return doc, lines


def _clean_bases():
    """Fixtures whose faithful rendering is clean (no upstream merge / reorder)."""
    out = []
    for fx in FX.FIXTURES:
        doc, lines = _base(fx)
        if not _errors(H.preservation(fx, lines, document=doc)):
            out.append((fx, doc, lines))
    return out


@pytest.fixture(scope="module")
def bases():
    found = _clean_bases()
    assert len(found) >= 60, len(found)
    return found


def _units(fx):
    return {u["id"]: u for u in O.expected_units(fx)}


def _line_owner(fx, doc, lines):
    """line index -> declared units it shows (via the oracle's own identity view)."""
    view = O._DocView(doc, True)
    units = O.expected_units(fx)
    carrier = {}
    for u in units:
        for item, _ in view.holders(u):
            if item.content_layer == view.BODY:
                carrier.setdefault(id(item), []).append(u)
                break
    owners = []
    for e in view.entries:
        held = carrier.get(id(e["item"]), [])
        if e["row"] is not None:
            held = [u for u in held if u.get("row") == e["row"]]
        elif isinstance(e["item"], view.T["PictureItem"]):
            held = [u for u in held if u["kind"] == "picture"]
        owners.append((e, held))
    assert len(owners) == len(lines)
    return owners


def _required_line(held):
    return any(u["gt"] in ("keep", "join") and u["kind"] != "picture" for u in held)


# (found, total) of every mutation class, for the benchmark report
# (scripts/ocr/phase12_oracle_mutations.py prints them).
DETECTION: dict[str, tuple[int, int]] = {}


def _rate(results, name=None):
    found = sum(1 for r in results if r)
    if name:
        DETECTION[name] = (found, len(results))
    return found, len(results)


# --------------------------------------------------------------------------- #
# Identity mode: damage in the document AND in what is displayed
# --------------------------------------------------------------------------- #


def test_identity_bases_are_clean_and_located(bases):
    for fx, doc, lines in bases:
        p = H.preservation(fx, lines, document=doc)
        assert p["attribution"] == "identity" and p["not_located"] == [], fx["name"]


def test_every_deleted_required_line_is_seen(bases):
    results = []
    for fx, doc, lines in bases:
        for i, (e, held) in enumerate(_line_owner(fx, doc, lines)):
            if _required_line(held):
                damaged = lines[:i] + lines[i + 1 :]
                results.append(
                    H.preservation(fx, damaged, document=doc)["false_deletion"] >= 1
                )
    found, total = _rate(results, "deleted required line")
    assert total > 300 and found == total, (found, total)


def test_every_item_removed_from_the_body_is_seen(bases):
    """The normalizer moves a required item to furniture: line AND item gone."""
    results = []
    from docling_core.types.doc.document import ContentLayer

    for fx, doc, lines in bases:
        owners = _line_owner(fx, doc, lines)
        for i, (e, held) in enumerate(owners):
            if not _required_line(held) or e["row"] is not None:
                continue
            work = doc.model_copy(deep=True)
            target = e["item"].self_ref
            item = next(
                it
                for it, _ in work.iterate_items(traverse_pictures=True)
                if it.self_ref == target
            )
            item.content_layer = ContentLayer.FURNITURE
            damaged = lines[:i] + lines[i + 1 :]
            results.append(
                H.preservation(fx, damaged, document=work)["false_deletion"] >= 1
            )
    found, total = _rate(results, "required item moved out of the body (identity)")
    assert total > 250 and found == total, (found, total)


def test_every_inserted_line_is_seen(bases):
    results = []
    for fx, doc, lines in bases:
        for i in range(len(lines) + 1):
            damaged = lines[:i] + ["Câu này không có trong văn bản gốc."] + lines[i:]
            results.append(
                H.preservation(fx, damaged, document=doc)["false_insertion"] >= 1
            )
    found, total = _rate(results, "inserted line")
    assert total > 350 and found == total, (found, total)


def test_every_swap_of_two_adjacent_lines_is_seen(bases):
    """Includes swaps with artifact and placeholder lines (12D4: 0 / 35)."""
    results, with_artifact = [], []
    for fx, doc, lines in bases:
        owners = _line_owner(fx, doc, lines)
        for i in range(len(lines) - 1):
            a, b = owners[i][1], owners[i + 1][1]
            if not a or not b or lines[i] == lines[i + 1]:
                continue
            if all(u["gt"] == "decoration" for u in a) or all(
                u["gt"] == "decoration" for u in b
            ):
                continue  # a signature / stamp has no reading position of its own
            damaged = lines[:i] + [lines[i + 1], lines[i]] + lines[i + 2 :]
            seen = H.preservation(fx, damaged, document=doc)["false_reordering"] >= 1
            results.append(seen)
            if any(u["gt"] in ("artifact", "furniture") for u in a + b):
                with_artifact.append(seen)
    found, total = _rate(results, "two adjacent lines swapped")
    assert total > 300 and found == total, (found, total)
    found, total = _rate(with_artifact, "swap with an artifact / furniture line")
    assert total >= 20 and found == total, (found, total)


def test_every_wrong_join_is_seen(bases):
    """Two adjacent text lines shown as one line - and the same join made in the
    document - is a false merge unless the second is the declared continuation."""
    from docling_core.types.doc.document import ContentLayer, TextItem

    display, document = [], []
    for fx, doc, lines in bases:
        owners = _line_owner(fx, doc, lines)
        preds = O._predecessors(O.expected_units(fx))
        for i in range(len(lines) - 1):
            (ea, a), (eb, b) = owners[i], owners[i + 1]
            if (
                not (len(a) == 1 and len(b) == 1)
                or ea["row"] is not None
                or eb["row"] is not None
            ):
                continue
            if a[0]["kind"] != "text" or b[0]["kind"] != "text":
                continue
            if preds.get(b[0]["id"]) == a[0]["id"]:
                continue  # an allowed join
            merged = f"{lines[i]} {lines[i + 1]}"
            damaged = lines[:i] + [merged] + lines[i + 2 :]
            display.append(
                H.preservation(fx, damaged, document=doc)["false_merge"] >= 1
            )
            work = doc.model_copy(deep=True)
            items = {
                it.self_ref: it for it, _ in work.iterate_items(traverse_pictures=True)
            }
            ia, ib = items[ea["item"].self_ref], items[eb["item"].self_ref]
            if not (isinstance(ia, TextItem) and isinstance(ib, TextItem)):
                continue
            ia.text = f"{ia.text} {ib.text}"
            ia.prov.extend(ib.prov)
            ib.content_layer = ContentLayer.INVISIBLE
            document.append(
                H.preservation(fx, damaged, document=work)["false_merge"] >= 1
            )
    for results, minimum, label in (
        (display, 200, "wrong join shown as one line"),
        (document, 150, "wrong join made in the document"),
    ):
        found, total = _rate(results, label)
        assert total > minimum and found == total, (found, total)


def test_every_lost_occurrence_of_repeated_content_is_seen(bases):
    results = []
    for fx, doc, lines in bases:
        owners = _line_owner(fx, doc, lines)
        counts = Counter(lines)
        for i, (e, held) in enumerate(owners):
            if counts[lines[i]] >= 2 and _required_line(held):
                damaged = lines[:i] + lines[i + 1 :]
                results.append(
                    H.preservation(fx, damaged, document=doc)["false_deletion"] >= 1
                )
    found, total = _rate(results, "one occurrence of repeated content deleted")
    assert total >= 20 and found == total, (found, total)


def test_a_lost_picture_trace_is_seen(bases):
    results = []
    for fx, doc, lines in bases:
        for i, (e, held) in enumerate(_line_owner(fx, doc, lines)):
            if any(u["kind"] == "picture" and u["gt"] != "decoration" for u in held):
                damaged = lines[:i] + lines[i + 1 :]
                results.append(
                    H.preservation(fx, damaged, document=doc)["placeholders_lost"] >= 1
                )
    found, total = _rate(results, "picture placeholder lost")
    assert total >= 5 and found == total, (found, total)


def test_a_changed_digit_or_table_cell_is_seen(bases):
    results = []
    for fx, doc, lines in bases:
        for i, (e, held) in enumerate(_line_owner(fx, doc, lines)):
            if not _required_line(held):
                continue
            line = lines[i]
            pos = next((k for k, ch in enumerate(line) if ch in "0123456789"), None)
            if pos is None:
                continue
            changed = line[:pos] + str((int(line[pos]) + 1) % 10) + line[pos + 1 :]
            damaged = lines[:i] + [changed] + lines[i + 1 :]
            p = H.preservation(fx, damaged, document=doc)
            # a changed digit in a clause marker is a changed marker; elsewhere
            # the unit is gone and another text is shown in its place
            results.append(
                p["marker_changed"] >= 1
                or (p["false_deletion"] >= 1 and p["false_insertion"] >= 1)
            )
    found, total = _rate(results, "digit changed (number / marker / table cell)")
    assert total > 100 and found == total, (found, total)


# --------------------------------------------------------------------------- #
# The defects of the Phase 12D4 re-review, named
# --------------------------------------------------------------------------- #


def _move_to_furniture(doc, refs):
    from docling_core.types.doc.document import ContentLayer

    work = doc.model_copy(deep=True)
    for it, _ in work.iterate_items(traverse_pictures=True):
        if it.self_ref in refs:
            it.content_layer = ContentLayer.FURNITURE
    return work


def _carrier_refs(fx, doc, predicate):
    view = O._DocView(doc, True)
    refs = []
    for u in O.expected_units(fx):
        if predicate(u):
            refs += [it.self_ref for it, _ in view.holders(u)]
    return refs


def test_clause_number_deleted_while_its_twin_page_number_stays():
    """F-02 as the old oracle missed it: the page numbers stay, the clause
    numbers 2, 3, 4 are moved out of the body - same displayed texts."""
    fx = FX.by_name("d5_f02_page_number_and_clause_number_alias")
    doc, lines = _base(fx)
    refs = _carrier_refs(
        fx, doc, lambda u: u["gt"] == "keep" and u["text"] in ("2", "3", "4")
    )
    assert len(refs) == 3
    work = _move_to_furniture(doc, set(refs))
    shown = O.faithful_lines(work)
    assert Counter(shown)["2"] == 1  # the page number "2" is still displayed
    p = H.preservation(fx, shown, document=work)
    assert p["false_deletion"] == 3, p["false_deletion_units"]
    # and lines only (worst case): never 0 either
    assert H.preservation(fx, shown)["false_deletion"] == 3


def test_voucher_number_deleted_is_seen():
    fx = FX.by_name("d5_f02_voucher_numbers_beside_label")
    doc, lines = _base(fx)
    refs = _carrier_refs(fx, doc, lambda u: u["text"] == "0003")
    work = _move_to_furniture(doc, set(refs))
    p = H.preservation(fx, O.faithful_lines(work), document=work)
    assert p["false_deletion_units"] == ["0003"]
    assert not p["critical_ok"]


def test_furniture_content_is_measured():
    """R2-11: business content labelled header / footer is REQUIRED (declared),
    furniture that is not content is counted, never silently ignored."""
    fx = FX.by_name("d5_r211_letterhead_document_number")
    doc = H.build_document(fx)
    std = doc.export_to_markdown()
    p = H.preservation(
        fx, H.display_lines(std), std, document=doc, pictures_traversed=False
    )
    assert "Số: 1234/QĐ-NHM-KHCN" in p["false_deletion_units"]
    fx2 = FX.by_name("d5_r211_running_header_and_footer_numbers")
    doc2 = H.build_document(fx2)
    std2 = doc2.export_to_markdown()
    p2 = H.preservation(
        fx2, H.display_lines(std2), std2, document=doc2, pictures_traversed=False
    )
    assert p2["furniture_declared"] == 6 and p2["furniture_shown"] == 0
    assert p2["false_deletion"] == 0


def test_upstream_merge_and_dehyphenation_are_seen():
    """R2-01: Docling's own merge is a false merge for the oracle; its removed
    hyphen is reported as an altered unit."""
    fx = FX.by_name("d5_r201_hyphen_lowercase")
    doc = H.build_document(fx)
    std = doc.export_to_markdown()
    p = H.preservation(
        fx, H.display_lines(std), std, document=doc, pictures_traversed=False
    )
    assert p["false_merge"] == 1 and p["altered_units"] == 1
    assert "hyphen" in p["altered"][0]["why"]


def test_text_mode_never_lets_an_artifact_stand_in_for_a_required_unit():
    fx = FX.by_name("d5_f02_page_number_and_clause_number_alias")
    truth = [u["text"] for u in O.expected_units(fx)]
    assert H.preservation(fx, truth)["false_deletion"] == 0
    damaged = list(truth)
    for n in ("2", "3", "4"):
        damaged.remove(n)  # one of the two "n" lines is gone
    assert H.preservation(fx, damaged)["false_deletion"] == 3
    assert set(H.preservation(fx, damaged)["ambiguous"]) == {"2", "3", "4"}


def test_text_mode_sees_an_artifact_line_reinserted_elsewhere():
    fx = FX.by_name("d5_f02_true_page_numbers_bottom_centre")
    truth = [u["text"] for u in O.expected_units(fx)]
    moved = [x for x in truth if x != "1"]
    moved.insert(len(moved) - 2, "1")  # page number of page 1 shown near the end
    p = H.preservation(fx, moved)
    assert p["false_reordering"] + p["false_insertion"] >= 1
