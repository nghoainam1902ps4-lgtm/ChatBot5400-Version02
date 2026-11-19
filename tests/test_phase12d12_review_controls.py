"""Phase 12D12 - independent re-review controls for candidate 18eeecb.

Synthetic fixtures only. Three groups:

* passing controls: behaviour the 12D11 remediation claims and this review
  re-derived with its own inputs (they must keep passing);
* ``xfail(strict=True)`` controls: deviations this review reproduced. None is a
  release blocker (see docs/review/PHASE12D12_TARGETED_REVIEW.md); the marker
  makes the suite report when the safe behaviour is back;
* standalone-server controls: the embedding write fence depends on the storage
  engine's write-conflict detection, which the embedded SDK engine used by the
  12D11 suite does not provide across connections. They run only when
  ``CB5400_D12_SURREAL_URL`` designates a disposable loopback SurrealDB server
  (never the application default port) and are skipped otherwise.
"""

import asyncio
import ipaddress
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_phase12d9_ocr_failure_safety import database as database  # noqa: F401

try:  # the rendered-OCR rig needs Docling; the other controls do not
    import test_phase12d9_standard_gate as ocr_rig
    from test_phase12d9_standard_gate import gate as d12_rendered  # noqa: F401
except pytest.skip.Exception:  # pragma: no cover - Docling not installed
    ocr_rig = None

    @pytest.fixture
    def d12_rendered():
        pytest.skip("needs Docling")


ROOT = Path(__file__).resolve().parents[1]
SERVER_URL_VAR = "CB5400_D12_SURREAL_URL"
SERVER_USER_VAR = "CB5400_D12_SURREAL_USER"
SERVER_PASSWORD_VAR = "CB5400_D12_SURREAL_PASSWORD"


# --------------------------------------------------------------------------- #
# R03 - embedding publication
# --------------------------------------------------------------------------- #


def _embedding():
    from commands import embedding_commands

    return embedding_commands


async def _vectors(source_id):
    from open_notebook.database import repository as db

    return await db.repo_query(
        "SELECT order, content, embedding FROM source_embedding "
        "WHERE source = $sid ORDER BY order",
        {"sid": db.ensure_record_id(source_id)},
    )


def _job(source):
    embedding = _embedding()
    return embedding.embed_source_command(
        embedding.EmbedSourceInput(source_id=source.id)
    )


@pytest.fixture
def two_chunks(monkeypatch):
    monkeypatch.setattr(
        _embedding(), "chunk_text", lambda text, **_: [text, text + " (2)"]
    )


@pytest.fixture
def server_database(monkeypatch):
    """A fresh namespace on a disposable standalone SurrealDB server."""
    url = os.environ.get(SERVER_URL_VAR)
    if not url:
        pytest.skip(f"standalone SurrealDB control: set {SERVER_URL_VAR}")
    parts = urlsplit(url)
    host = parts.hostname or ""
    loopback = host == "localhost" or (
        host.replace(".", "").isdigit() and ipaddress.ip_address(host).is_loopback
    )
    if parts.scheme not in ("ws", "http") or not loopback or parts.port in (None, 8000):
        pytest.fail(
            f"{SERVER_URL_VAR} must be a loopback endpoint on a port other than "
            "the application default"
        )
    import surreal_commands.core.service as cmd_service

    from open_notebook.database import repository

    name = "d12test_" + uuid.uuid4().hex[:12]
    for key, value in {
        "SURREAL_URL": url,
        "SURREAL_USER": os.environ.get(SERVER_USER_VAR, "root"),
        "SURREAL_PASSWORD": os.environ.get(SERVER_PASSWORD_VAR, "root"),
        "SURREAL_NAMESPACE": name,
        "SURREAL_DATABASE": name,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cmd_service, "_command_service", None)
    guarded = repository.AsyncSurreal

    def designated_only(u, *a, **k):
        if u == url:
            return getattr(guarded, "original", guarded)(u, *a, **k)
        return guarded(u, *a, **k)

    monkeypatch.setattr(repository, "AsyncSurreal", designated_only)

    async def boot():
        from open_notebook.database.async_migrate import AsyncMigrationManager

        await AsyncMigrationManager().run_migration_up()

    asyncio.run(boot())
    sys.path.insert(0, str(ROOT))
    import commands.embedding_commands  # noqa: F401 - registers embed_source

    yield url
    monkeypatch.setattr(cmd_service, "_command_service", None)


async def _release_jobs_together(monkeypatch, count):
    from open_notebook.domain.notebook import Source

    source = Source(title="Synthetic", full_text="synthetic document")
    await source.save()
    gate = asyncio.Event()
    seen = 0

    async def generate(*_, **__):
        nonlocal seen
        seen += 1
        mine = float(seen)
        await gate.wait()
        return [[mine], [mine]]

    monkeypatch.setattr(_embedding(), "generate_embeddings", generate)
    tasks = [asyncio.create_task(_job(source)) for _ in range(count)]
    for _ in range(100):
        if seen == count:
            break
        await asyncio.sleep(0.05)
    assert seen == count, "every job must hold vectors for the same revision"
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return source, results


@pytest.mark.asyncio
async def test_server_same_revision_jobs_publish_exactly_one_chunk_set(
    server_database, two_chunks, monkeypatch
):
    """Four jobs that loaded the same Source revision commit at the same time.

    Standalone server: exactly one set survives, the others are refused
    (stale revision) or fail with a retryable write conflict.
    """
    source, results = await _release_jobs_together(monkeypatch, 4)
    rows = await _vectors(source.id)
    assert [row["order"] for row in rows] == [0, 1], rows
    assert len({tuple(row["embedding"]) for row in rows}) == 1, rows
    published = [r for r in results if getattr(r, "success", False)]
    assert len(published) == 1, results
    for other in results:
        if other in published:
            continue
        assert isinstance(other, RuntimeError) or (
            other.success is False
            and "Source changed before publication" in (other.error_message or "")
        ), other


@pytest.mark.asyncio
async def test_server_stale_job_cannot_restore_a_deleted_source(
    server_database, two_chunks, monkeypatch
):
    from open_notebook.database import repository as db
    from open_notebook.domain.notebook import Notebook, Source

    source = Source(title="Synthetic", full_text="synthetic document")
    await source.save()
    notebook = Notebook(name="Synthetic notebook", description="")
    await notebook.save()
    keep = Source(title="Other", full_text="other document")
    await keep.save()
    await source.add_to_notebook(notebook.id)
    await keep.add_to_notebook(notebook.id)
    started, resume = asyncio.Event(), asyncio.Event()

    async def generate(*_, **__):
        started.set()
        await resume.wait()
        return [[0.5], [0.5]]

    monkeypatch.setattr(_embedding(), "generate_embeddings", generate)
    task = asyncio.create_task(_job(source))
    await asyncio.wait_for(started.wait(), 5)
    assert await source.delete()
    resume.set()
    result = await task
    assert result.success is False
    assert await Source.get(keep.id)
    assert (
        await db.repo_query("SELECT * FROM $id", {"id": db.ensure_record_id(source.id)})
        == []
    )
    assert await _vectors(source.id) == []
    links = await db.repo_query("SELECT VALUE in FROM reference")
    assert [str(link) for link in links] == [str(keep.id)], links


@pytest.mark.asyncio
@pytest.mark.usefixtures("database")
@pytest.mark.xfail(
    strict=True,
    reason="D12-01 (non-blocking): any write to the Source record between the "
    "job's load and its commit makes embed_source end as a non-retried "
    "'Source changed before publication'; unchanged text is left without vectors",
)
async def test_metadata_only_edit_does_not_drop_an_inflight_embedding(
    two_chunks, monkeypatch
):
    from open_notebook.domain.notebook import Source

    source = Source(title="Processing...", full_text="synthetic document")
    await source.save()
    started, resume = asyncio.Event(), asyncio.Event()

    async def generate(*_, **__):
        started.set()
        await resume.wait()
        return [[0.5], [0.5]]

    monkeypatch.setattr(_embedding(), "generate_embeddings", generate)
    task = asyncio.create_task(_job(source))
    await asyncio.wait_for(started.wait(), 5)
    edited = await Source.get(source.id)
    edited.title = "Renamed while embedding"
    await edited.save()
    resume.set()
    result = await task

    current = await Source.get(source.id)
    assert current.full_text == "synthetic document"  # the text never changed
    rows = await _vectors(source.id)
    # Safe behaviour: the same text is embedded (now, or by an automatic retry).
    assert result.success and [row["order"] for row in rows] == [0, 1], (
        result.error_message,
        rows,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("database")
async def test_metadata_only_save_from_a_stale_copy_keeps_the_published_text(
    two_chunks, monkeypatch
):
    """Control: the API's stale copy (no text yet) saves after the worker published."""
    from open_notebook.domain.notebook import Source

    async def generate(*_, **__):
        return [[0.5], [0.5]]

    monkeypatch.setattr(_embedding(), "generate_embeddings", generate)
    stale = Source(title="Processing...")
    await stale.save()
    worker = await Source.get(stale.id)
    worker.full_text = "published document"
    await worker.save()
    assert (await _job(worker)).success
    stale.title = "Late metadata"
    await stale.save()

    current = await Source.get(stale.id)
    assert current.full_text == "published document"
    assert current.title == "Late metadata"
    assert [row["content"] for row in await _vectors(stale.id)] == [
        "published document",
        "published document (2)",
    ]


# --------------------------------------------------------------------------- #
# R04 - text preservation
# --------------------------------------------------------------------------- #


def _cell(index, text, left, top, right, bottom):
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from docling_core.types.doc.page import BoundingRectangle, TextCell

    return TextCell(
        index=index,
        text=text,
        orig=text,
        from_ocr=True,
        rect=BoundingRectangle.from_bounding_box(
            BoundingBox(
                l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.TOPLEFT
            )
        ),
    )


HYPHEN_GEOMETRY = {
    # a wrapped identifier closes up only on line-break evidence
    "line cells, same margin": (
        [
            ("Thong tu 05/2024/TT-", 72, 100, 500, 112),
            ("BNNPTNT ngay 1", 72, 116, 300, 128),
        ],
        "Thong tu 05/2024/TT-BNNPTNT ngay 1",
    ),
    "word cells, wrapped": (
        [
            ("Thong", 72, 100, 110, 112),
            ("tu", 114, 100, 126, 112),
            ("05/2024/TT-", 130, 100, 210, 112),
            ("BNNPTNT", 72, 116, 140, 128),
        ],
        "Thong tu 05/2024/TT-BNNPTNT",
    ),
    "leading zero kept": (
        [("So 05-", 72, 100, 110, 112), ("007/QD", 72, 116, 120, 128)],
        "So 05-007/QD",
    ),
    "repeated identifiers": (
        [
            ("12-", 72, 100, 90, 112),
            ("34", 72, 116, 90, 128),
            ("12-", 100, 116, 120, 128),
            ("34", 72, 132, 90, 144),
        ],
        "12-34 12-34",
    ),
    # everything else keeps the cell boundary (and every hyphen)
    "same line": ([("VT-", 72, 100, 90, 112), ("KHTC", 94, 100, 130, 112)], "VT- KHTC"),
    "same line, vertical offset": (
        [("VT-", 72, 100, 90, 112), ("KHTC", 94, 103, 130, 115)],
        "VT- KHTC",
    ),
    "other column, lower": (
        [("12/AB-", 72, 100, 120, 112), ("TERM", 400, 116, 440, 128)],
        "12/AB- TERM",
    ),
    "other column, same baseline": (
        [("12/AB-", 72, 100, 120, 112), ("TERM", 400, 100, 440, 112)],
        "12/AB- TERM",
    ),
    "right column end, then left column across a wide gutter": (
        [
            ("left", 72, 100, 200, 112),
            ("12/AB-", 330, 100, 380, 112),
            ("TERM", 72, 116, 120, 128),
        ],
        "left 12/AB- TERM",
    ),
    "next cell above": (
        [("12/AB-", 72, 200, 120, 212), ("TERM", 72, 100, 120, 112)],
        "12/AB- TERM",
    ),
    "five lines below": (
        [("12/AB-", 72, 100, 120, 112), ("TERM", 72, 180, 120, 192)],
        "12/AB- TERM",
    ),
    "unattached hyphen": (
        [("muc -", 72, 100, 110, 112), ("tieu", 72, 116, 100, 128)],
        "muc - tieu",
    ),
}


@pytest.mark.parametrize("name", sorted(HYPHEN_GEOMETRY))
def test_hyphen_closes_only_on_line_break_evidence(name):
    pytest.importorskip("docling")
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    from open_notebook.ocr import docling_patches

    assert docling_patches.apply_text_preservation(required=True)
    boxes, expected = HYPHEN_GEOMETRY[name]
    cells = [_cell(i, *box) for i, box in enumerate(boxes)]
    model = PageAssembleModel(options=PageAssembleOptions())
    text = model.sanitize_text(
        [cell.text for cell in cells],
        same_line=docling_patches.same_line_flags(cells),
    )
    assert text == expected
    assert text.count("-") == sum(cell.text.count("-") for cell in cells)


def _legal_document(literal):
    from docling_core.types.doc import (
        DocItemLabel,
        DoclingDocument,
        TableCell,
        TableData,
    )

    doc = DoclingDocument(name="synthetic")
    table = doc.add_table(
        data=TableData(
            num_rows=1,
            num_cols=1,
            table_cells=[
                TableCell(
                    text="Rate",
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    column_header=True,
                )
            ],
        )
    )
    note = doc.add_text(label=DocItemLabel.FOOTNOTE, text=literal, parent=table)
    table.footnotes.append(note.get_ref())
    doc.add_text(label=DocItemLabel.TEXT, text=literal)
    return doc


@pytest.mark.parametrize("literal", ["> quoted remark", "# Valuation applies."])
def test_attached_legal_note_is_literal_and_written_once(literal):
    pytest.importorskip("docling")
    from open_notebook.ocr import docling_patches
    from open_notebook.ocr.legal_normalizer import normalize_document

    assert docling_patches.apply_text_preservation(required=True)
    blocks = normalize_document(_legal_document(literal)).content.split("\n\n")
    # table, its note (once), the body paragraph - both literal, same form
    assert blocks[1:] == ["\\" + literal, "\\" + literal], blocks


@pytest.mark.xfail(
    strict=True,
    reason="D12-02 (non-blocking, Legal mode only): the 12D11 footnote branch "
    "also backslash-escapes _ [ ] * ~ ` and clause markers, so a Legal footnote "
    "is no longer stored as printed (F-17) while the same body text is",
)
def test_legal_footnote_is_stored_as_printed_like_body_text():
    pytest.importorskip("docling")
    from open_notebook.ocr import docling_patches
    from open_notebook.ocr.legal_normalizer import normalize_document

    assert docling_patches.apply_text_preservation(required=True)
    literal = "1. Tai khoan TK_VND_01 theo [Dieu 5] cua 05/2024/TT-BNNPTNT"
    blocks = normalize_document(_legal_document(literal)).content.split("\n\n")
    assert blocks[2] == literal  # body paragraph: printed characters (F-17)
    assert blocks[1] == literal, blocks[1]  # the footnote: same characters


# --------------------------------------------------------------------------- #
# R05 - Standard expected-diff, release mode
# --------------------------------------------------------------------------- #

D12_03 = (
    "D12-03 (release gate, residual of D10-06): verify_bound_output proves the "
    "BASELINE text of a span from its TSV rows but takes the candidate text from "
    "the candidate's own element record; a candidate token no row supports is "
    "classified 'expected TSV fix' with exit 0"
)


def _bound_case(tmp_path, rows, joined, upstream):
    """One page, one crop, honest row-to-cell evidence; only the JOINED text of
    the element (what the candidate's assembly produced) is the caller's."""
    import hashlib
    import json

    from scripts.ocr import phase12_standard_diff as gate

    folder = tmp_path / "case.evidence"
    (folder / "tesseract").mkdir(parents=True)
    identity = {"document": "case", "run_id": "a" * 32}
    models = {"vie": "b" * 64}
    raw = (
        gate._TSV_HEADER
        + gate._TSV_PARENTS
        + "".join(
            f"5\t1\t1\t1\t1\t{i + 1}\t{7 + 15 * i}\t7\t8\t9\t96\t{word}\n"
            for i, word in enumerate(rows)
        )
    )
    (folder / "tesseract/0001_001_000001.tsv").write_text(raw, encoding="utf-8")
    (folder / "tesseract/0001_001_000001.json").write_text(
        json.dumps(
            {
                **identity,
                "invocation": "0001-001-000001",
                "page": 1,
                "region": 1,
                "bbox": [0, 0, 500, 50],
                "engine": "vie",
                "model_files": [{"name": "vie", "sha256": models["vie"]}],
            }
        ),
        encoding="utf-8",
    )
    element = {
        **identity,
        "page": 1,
        "cluster": 1,
        "bbox": [0, 0, 500, 50],
        "text": joined,
        "v120_text": upstream,
        "cells": [
            {
                "invocation": "0001-001-000001",
                "row": 4 + i,
                "raw": word,
                "text": word,
                "bbox": [7 + 15 * i, 7, 15 + 15 * i, 16],
            }
            for i, word in enumerate(rows)
        ],
    }
    span = {
        **{k: element[k] for k in ("document", "run_id", "page", "cluster", "bbox")},
        "text": joined,
        "v120_text": upstream,
        "item": "#/texts/0",
        "start": 0,
        "end": len(joined),
        "hyphens": [],
    }
    for name, record in (("elements", element), ("output_spans", span)):
        (folder / f"{name}.jsonl").write_text(
            json.dumps(record) + "\n", encoding="utf-8"
        )
    files = {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*")
        if p.is_file()
    }
    report = gate.verify_bound_output(
        upstream,
        joined,
        folder,
        {"name": "case", "evidence_files": files, "ocr_model_files": models},
        identity,
    )
    return gate, report


def test_bound_gate_control_unchanged_span_is_accepted(tmp_path):
    gate, report = _bound_case(
        tmp_path, ["Article", "5", "applies"], "Article 5 applies", "Article 5 applies"
    )
    assert report["class"] not in (gate.NOT_VERIFIED, gate.UNEXPECTED), report


@pytest.mark.xfail(strict=True, reason=D12_03)
@pytest.mark.parametrize(
    "joined",
    [
        "Article 6 applies",  # a digit no OCR row contains
        "Article applies",  # a recognised token dropped
        "Article 5 applies and an invented clause",  # text without a source cell
    ],
)
def test_bound_gate_refuses_candidate_text_its_own_rows_do_not_support(
    tmp_path, joined
):
    gate, report = _bound_case(
        tmp_path, ["Article", "5", "applies"], joined, "Article 5 applies"
    )
    assert report["class"] == gate.NOT_VERIFIED, report


@pytest.mark.xfail(strict=True, reason=D12_03)
def test_release_gate_refuses_a_candidate_join_defect_real_ocr(
    d12_rendered,  # noqa: F811
    monkeypatch,
):
    """Real Tesseract + Docling, the unmodified exporter and comparator. Only the
    candidate's text join is given a defect, after the baseline export."""
    import json

    if ocr_rig.needs_ocr.args[0]:
        pytest.skip("needs Tesseract with the vie model")
    rendered = d12_rendered
    patches = ocr_rig.P
    rendered.pdf(
        "defect",
        [["Điều 5. Hiệu lực thi hành"], ["Bên A không chịu trách nhiệm bồi thường"]],
    )
    baseline = rendered.export_v120()

    def defective(model, page, cluster, kept_cells, textlines):
        text = model.sanitize_text(
            textlines, same_line=patches.same_line_flags(kept_cells)
        )
        text = text.replace("Điều 5", "Điều 6").replace("không ", "")
        if patches._evidence is not None:
            patches._evidence.element(model, page, cluster, kept_cells, text)
        return text

    monkeypatch.setattr(patches, "_assembled_text", defective)
    candidate = rendered.export_candidate()
    before = (rendered.before / "defect.md").read_text(encoding="utf-8")
    after = (rendered.after / "defect.md").read_text(encoding="utf-8")
    assert "Điều 5" in before and "không chịu" in before, "OCR precondition"
    assert "Điều 6" in after and "không" not in after, "defect precondition"
    folder = rendered.after / "defect.evidence"
    sidecar = json.loads(
        sorted((folder / "tesseract").glob("*.json"))[0].read_text(encoding="utf-8")
    )
    models = {m["name"]: m["sha256"] for m in sidecar["model_files"]}
    candidate["documents"][0]["ocr_model_files"] = models
    baseline["documents"][0]["ocr_model_files"] = models
    baseline.update(
        commit="f2fdf2714a7c0b5b196132f71cfc091928befc06", image_id="sha256:" + "a" * 64
    )
    candidate.update(commit="a" * 40, image_id="sha256:" + "b" * 64)
    for root, manifest in ((rendered.before, baseline), (rendered.after, candidate)):
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    code, report = rendered.diff(
        "--release",
        "--candidate-commit",
        candidate["commit"],
        "--candidate-image",
        candidate["image_id"],
    )
    assert code != 0, report["documents"]["defect"]["class"]
