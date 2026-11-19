"""Independent 12D10 controls. Strict xfails record open release blockers."""

import asyncio
import errno
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.ocr import phase12_standard_diff as diff
from scripts.ocr import phase12d9_standard_export as export
from scripts.offline import offline_package as offline


def _paired_outputs(tmp_path, old, new):
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    for folder, body in ((before, old), (after, new)):
        (folder / "sample.md").write_bytes(body)
    return before, after


def _gate(tmp_path, before, after):
    out = tmp_path / "report"
    status = diff.main(
        ["--before", str(before), "--after", str(after), "--out", str(out)]
    )
    return status, json.loads((out / "standard_diff.json").read_text(encoding="utf-8"))


@pytest.mark.xfail(
    strict=True, reason="D10-05: universal-newline read hides a byte difference"
)
def test_gate_rejects_lf_to_crlf_change(tmp_path):
    before, after = _paired_outputs(
        tmp_path, b"Article 1\nText\n", b"Article 1\r\nText\r\n"
    )
    status, report = _gate(tmp_path, before, after)
    assert status == 1, report


@pytest.mark.xfail(
    strict=True, reason="D10-05: manifest-listed successes can lack both outputs"
)
def test_gate_rejects_a_success_missing_on_both_sides(tmp_path):
    body = b"Article 1\n"
    before, after = _paired_outputs(tmp_path, body, body)
    for folder in (before, after):
        documents = [
            {
                "name": name,
                "conversion_status": "success",
                "output": f"{name}.md",
                "input_sha256": "0" * 64,
                "output_sha256": hashlib.sha256(body).hexdigest(),
            }
            for name in ("sample", "missing")
        ]
        (folder / "manifest.json").write_text(
            json.dumps({"documents": documents}), encoding="utf-8"
        )
    status, report = _gate(tmp_path, before, after)
    assert status == 3, report


@pytest.mark.xfail(
    strict=True, reason="D10-06: a free-standing sidecar proves an unrelated run"
)
def test_gate_does_not_accept_orientation_without_invocation_evidence(tmp_path):
    before, after = _paired_outputs(tmp_path, b"incorrect", b"correct")
    evidence = after / "sample.evidence"
    evidence.mkdir()
    # The element record supplies no changes. Neither file identifies a run.
    (evidence / "elements.jsonl").write_text("{}\n", encoding="utf-8")
    (evidence / "orientation.jsonl").write_text(
        json.dumps({"v120_text": "incorrect", "text": "correct"}) + "\n",
        encoding="utf-8",
    )
    status, report = _gate(tmp_path, before, after)
    assert status != 0, report


@pytest.mark.xfail(
    strict=True, reason="D10-06: the gate ignores the actual model identity"
)
def test_gate_rejects_different_models_even_with_equal_output(tmp_path):
    body = b"Article 1\n"
    before, after = _paired_outputs(tmp_path, body, body)
    for folder, digest in ((before, "a" * 64), (after, "b" * 64)):
        manifest = {
            "schema": export.SCHEMA,
            "engine": "tesseract_agri",
            "custom_version": "v1",
            "documents": [
                {
                    "name": "sample",
                    "conversion_status": "success",
                    "output": "sample.md",
                    "input_sha256": "0" * 64,
                    "output_sha256": hashlib.sha256(body).hexdigest(),
                    "ocr_engine": "tesseract_agri",
                    "ocr_model_version": "v1",
                    "ocr_model_sha256": digest,
                }
            ],
        }
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    status, report = _gate(tmp_path, before, after)
    assert status == 3, report


@pytest.mark.xfail(
    strict=True, reason="D10-07: the same output occurrence is counted twice"
)
def test_hyphen_count_requires_two_distinct_occurrences(tmp_path):
    evidence = tmp_path / "tesseract"
    evidence.mkdir()
    for crop in ("1_0", "2_0"):
        (evidence / f"{crop}.tsv").write_text(
            "level\ttext\n5\t12-34\n", encoding="utf-8"
        )
    counts = export.hyphen_words(tmp_path, "Page 1: 12-34.\n\nPage 2: 1234.")
    assert counts == {"tsv_hyphen_words": 2, "tsv_hyphen_words_in_output": 1}


def test_interrupted_publish_restores_previous_hash_with_its_actual_filename(tmp_path):
    name = "ChatBot5400-synthetic"
    package = tmp_path / f"{name}.tar.gz"
    package.write_bytes(b"previous synthetic package")
    sidecar = package.with_name(f"{package.name}.sha256")
    old_line = f"{hashlib.sha256(package.read_bytes()).hexdigest()}  {package.name}\n"
    previous = sidecar.with_name(f"{sidecar.name}.previous-500")
    previous.write_text(old_line, encoding="utf-8")
    staged = tmp_path / f".{name}.tar.gz.sha256.partial-500"
    staged.write_text(f"{'f' * 64}  {package.name}\n", encoding="utf-8")

    offline._recover_interrupted_publish(tmp_path, name)

    assert sidecar.is_file(), sorted(p.name for p in tmp_path.iterdir())
    assert sidecar.read_text(encoding="utf-8") == old_line
    assert not previous.exists()


@pytest.mark.xfail(
    strict=True, reason="D10-08: persistent write failure deletes the recovery hashes"
)
def test_failed_hash_publish_leaves_enough_to_recover(tmp_path, monkeypatch):
    commit = "0" * 40
    repo = tmp_path / "repo"
    docs = repo / "docs" / "deployment"
    docs.mkdir(parents=True)
    (docs / offline.MANUAL_PROCEDURE).touch()
    out = tmp_path / "out"
    out.mkdir()
    package = out / "ChatBot5400-1.2.0-linux-amd64-offline.tar.gz"
    package.write_bytes(b"previous package")
    sidecar = package.with_name(f"{package.name}.sha256")
    sidecar.write_text(
        f"{offline.sha256_file(package)}  {package.name}\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        offline, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=commit)
    )
    monkeypatch.setattr(
        offline, "_git", lambda *a, **kw: "" if "status" in a else commit
    )
    monkeypatch.setattr(offline, "check_build_version", lambda *a, **kw: None)
    monkeypatch.setattr(offline, "_build_stage", lambda *a, **kw: {})
    args = [
        "build",
        "--version",
        "1.2.0",
        "--image",
        "chatbot5400:1.2.0",
        "--repo",
        str(repo),
        "--out",
        str(out),
    ]
    real_replace = offline.os.replace

    def cannot_replace_sidecar(src, dst, *a, **kw):
        if dst == sidecar:
            raise PermissionError(errno.EACCES, "synthetic persistent publish failure")
        return real_replace(src, dst, *a, **kw)

    with monkeypatch.context() as blocked:
        blocked.setattr(offline.os, "replace", cannot_replace_sidecar)
        try:
            assert offline.main(args) != 0
        except PermissionError:
            pass
    offline._recover_interrupted_publish(out, package.name.removesuffix(".tar.gz"))

    assert sidecar.is_file(), sorted(p.name for p in out.iterdir())
    assert (
        sidecar.read_text(encoding="utf-8")
        == f"{offline.sha256_file(package)}  {package.name}\n"
    )


@pytest.mark.xfail(
    strict=True,
    reason="D10-09: no-writes can miss changes to source_embedding contents",
)
def test_offline_no_writes_detects_in_place_vector_change(monkeypatch, capsys):
    from open_notebook.database import repository

    vector = [1.0]

    async def query(statement):
        projection, table = statement.removeprefix("SELECT ").split(" FROM ")
        if table != "source_embedding":
            return []
        row = {"id": "source_embedding:fixture", "embedding": list(vector)}
        return (
            [row]
            if projection == "*"
            else [{k: row[k] for k in projection.split(", ") if k in row}]
        )

    monkeypatch.setattr(repository, "repo_query", query)

    def snapshot():
        exec(offline.FINGERPRINT_PROBE, {})
        line = capsys.readouterr().out.strip().removeprefix("FINGERPRINT ")
        fingerprint = offline.make_fingerprint(json.loads(line))
        return {
            "kind": "chatbot5400-offline-snapshot",
            "data": fingerprint["summary"],
            "records": fingerprint["ids"],
            "db": {"container_id": "synthetic-db", "running": True},
        }

    before = snapshot()
    vector[:] = [0.5]
    after = snapshot()
    assert offline.compare_snapshots(before, before, no_writes=True)[0] == 0
    status, details = offline.compare_snapshots(before, after, no_writes=True)
    assert status != 0, details


@pytest.fixture
def native_source(tmp_path, monkeypatch):
    pytest.importorskip("docling")
    from content_core import extraction
    from content_core.processors.document import docling as native

    from open_notebook.graphs import source

    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(tmp_path))
    monkeypatch.setattr(
        source.ContentSettings,
        "get_instance",
        AsyncMock(return_value=source.ContentSettings()),
    )
    monkeypatch.setattr(
        source,
        "ModelManager",
        lambda: SimpleNamespace(
            get_defaults=AsyncMock(
                return_value=SimpleNamespace(default_speech_to_text_model=None)
            )
        ),
    )
    monkeypatch.setattr(source, "should_use_native_ocr", AsyncMock(return_value=False))
    monkeypatch.setattr(extraction, "DOCLING_AVAILABLE", True)
    monkeypatch.setattr(extraction, "DOCLING_SUPPORTED", {"application/pdf"})
    monkeypatch.setattr(extraction, "extract_docling", native.extract_docling)
    return source, native, pdf


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,error", [("partial_success", False), ("success", True)]
)
@pytest.mark.xfail(
    strict=True, reason="D10-02: content-core discards the conversion verdict"
)
async def test_native_content_core_refuses_incomplete_docling_result(
    native_source, monkeypatch, status, error
):
    from open_notebook.ocr.docling_extract import IncompleteConversionError

    source, native, pdf = native_source
    result = SimpleNamespace(
        status=status,
        errors=[SimpleNamespace(module_name="synthetic page stage", page_no=2)]
        if error
        else [],
        document=SimpleNamespace(export_to_markdown=lambda: "Article 1 only"),
    )
    monkeypatch.setattr(
        native,
        "DocumentConverter",
        lambda **_: SimpleNamespace(convert=lambda _: result),
    )
    with pytest.raises(IncompleteConversionError):
        await source.content_process({"content_state": {"file_path": str(pdf)}})


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, reason="D10-01: the native PDF URL only requests optional patching"
)
async def test_remote_native_pdf_fails_closed_if_patch_is_incompatible(
    native_source, monkeypatch
):
    from content_core import extraction

    from open_notebook.ocr import docling_patches as patches

    source, native, pdf = native_source
    monkeypatch.setattr(source, "assert_url_ingestion_enabled", lambda: None)
    monkeypatch.setattr(source, "validate_source_url", AsyncMock())
    monkeypatch.setattr(
        source, "should_use_native_ocr_for_url", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        extraction, "detect_remote_mime", AsyncMock(return_value="application/pdf")
    )
    monkeypatch.setattr(
        extraction, "_download_remote_file", AsyncMock(return_value=str(pdf))
    )
    monkeypatch.setattr(patches, "text_patches_applied", lambda: False)
    monkeypatch.setattr(
        patches, "text_problems", lambda: ["synthetic source-hash mismatch"]
    )
    result = SimpleNamespace(
        document=SimpleNamespace(export_to_markdown=lambda: "Unverified content")
    )
    monkeypatch.setattr(
        native,
        "DocumentConverter",
        lambda **_: SimpleNamespace(convert=lambda _: result),
    )

    with pytest.raises(patches.TextPreservationPatchError):
        await source.content_process(
            {"content_state": {"url": "https://example.invalid/sample.pdf"}}
        )


@pytest.mark.xfail(strict=True, reason="D10-04: the note bypasses LegalTextSerializer")
def test_attached_legal_note_preserves_literal_block_syntax():
    pytest.importorskip("docling")
    from docling_core.types.doc import (
        DocItemLabel,
        DoclingDocument,
        TableCell,
        TableData,
    )

    from open_notebook.ocr.legal_normalizer import normalize_document

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
    literal = "# Valuation applies under Article 9."
    note = doc.add_text(label=DocItemLabel.FOOTNOTE, text=literal, parent=table)
    table.footnotes.append(note.get_ref())
    doc.add_text(label=DocItemLabel.TEXT, text=literal)

    content = normalize_document(doc).content

    assert content.count(r"\# Valuation applies under Article 9.") == 2, content


@pytest.mark.xfail(
    strict=True, reason="D10-03: vertical displacement can join separate columns"
)
def test_assembly_does_not_fuse_hyphenated_cell_across_a_column_gutter():
    pytest.importorskip("docling")
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from docling_core.types.doc.page import BoundingRectangle

    from open_notebook.ocr.docling_patches import same_line_flags

    cells = [
        SimpleNamespace(
            rect=BoundingRectangle.from_bounding_box(
                BoundingBox(
                    l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.TOPLEFT
                )
            )
        )
        for left, top, right, bottom in [(70, 100, 120, 112), (400, 118, 460, 130)]
    ]
    model = PageAssembleModel(options=PageAssembleOptions())
    content = model.sanitize_text(["12/AB-", "TERM"], same_line=same_line_flags(cells))

    assert content == "12/AB- TERM"


def test_legal_keeps_cross_page_continuation_before_three_column_articles():
    pytest.importorskip("docling")
    from test_phase12d9_text_preservation import _blocks

    from open_notebook.ocr.legal_normalizer import normalize_document

    first = "The registered amount must be paid"
    continuation = "under the schedule in the appendix."
    articles = ["Article 2. Fees", "Article 3. Interest", "Article 4. Notices"]
    doc = _blocks(
        [
            [("text", first, [40, 720, 550, 744])],
            [
                ("text", continuation, [40, 60, 230, 310]),
                ("section_header", articles[0], [40, 340, 230, 360]),
                ("section_header", articles[1], [330, 40, 540, 55]),
                ("section_header", articles[2], [620, 70, 845, 90]),
            ],
        ],
        sizes=[(595, 820), (900, 600)],
    )
    assert len(doc.texts[0].prov) == 2, "fixture must exercise a real Docling merge"
    result = normalize_document(doc)
    items = [line.lstrip("# ") for line in result.content.splitlines() if line.strip()]
    assert items == [first, continuation, *articles]


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="D10-02: an already running embedding job removes valid chunks before replacement",
)
async def test_old_embedding_survives_failed_ocr_and_failed_inflight_embedding(
    monkeypatch,
):
    from commands import embedding_commands as embedding
    from commands import source_commands as processing
    from open_notebook.ocr.docling_extract import IncompleteConversionError

    sid = "source:synthetic"
    original_text = "This is the prior complete synthetic source."
    original = SimpleNamespace(
        id=sid, full_text=original_text, asset=None, save=AsyncMock()
    )
    records = [{"content": original_text, "embedding": [1.0]}]
    embedding_started, finish_embedding = asyncio.Event(), asyncio.Event()

    async def delete_records(query, _params):
        assert query.startswith("DELETE source_embedding ")
        records.clear()

    async def fail_embedding(chunks, **_):
        assert chunks == [original_text]
        embedding_started.set()
        await finish_embedding.wait()
        raise ValueError("synthetic provider rejection")

    monkeypatch.setattr(processing.Source, "get", AsyncMock(return_value=original))
    monkeypatch.setattr(embedding, "repo_query", delete_records)
    monkeypatch.setattr(embedding, "chunk_text", lambda content, **_: [content])
    monkeypatch.setattr(embedding, "generate_embeddings", fail_embedding)
    monkeypatch.setattr(
        processing.source_graph,
        "ainvoke",
        AsyncMock(
            side_effect=IncompleteConversionError(
                ocr_region=True, details="synthetic page 2"
            )
        ),
    )
    job = asyncio.create_task(
        embedding.embed_source_command(embedding.EmbedSourceInput(source_id=sid))
    )
    try:
        await asyncio.wait_for(embedding_started.wait(), timeout=2)
        with pytest.raises(IncompleteConversionError):
            await processing.process_source_command(
                processing.SourceProcessingInput(
                    source_id=sid,
                    content_state={},
                    notebook_ids=[],
                    transformations=[],
                    embed=True,
                )
            )
    finally:
        finish_embedding.set()
        result = await job

    assert not result.success
    assert original.full_text == original_text
    assert records == [{"content": original_text, "embedding": [1.0]}]


@pytest.mark.asyncio
async def test_sync_ingestion_removes_new_source_for_reported_failure(monkeypatch):
    from fastapi import HTTPException

    from api.routers import sources

    source = SimpleNamespace(
        id="source:synthetic", save=AsyncMock(), delete=AsyncMock()
    )
    monkeypatch.setattr(sources, "Source", lambda **_: source)
    monkeypatch.setattr(
        sources,
        "execute_command_sync",
        lambda *_a, **_kw: SimpleNamespace(
            is_success=lambda: False, error_message="Synthetic incomplete OCR"
        ),
    )
    data = sources.SourceCreate(type="text", content="Synthetic document", embed=True)

    with pytest.raises(HTTPException, match="Synthetic incomplete OCR"):
        await sources._create_source_sync_path(
            data, {"content": "Synthetic document"}, []
        )

    source.delete.assert_awaited_once()
