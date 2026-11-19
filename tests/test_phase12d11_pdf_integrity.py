"""Native conversion acceptance and Source lifecycle on synthetic input."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_phase12d9_ocr_failure_safety import database as database
from test_phase12d10_review_controls import native_source as native_source


@pytest.mark.asyncio
@pytest.mark.usefixtures("database")
@pytest.mark.parametrize(
    "status,error,body",
    [
        ("partial_success", False, "Article 1 only"),
        ("success", True, "Article 1 only"),
        ("success", False, " "),
        (None, False, "unknown conversion outcome"),
    ],
)
async def test_native_worker_never_stores_or_queues_incomplete_text(
    native_source,  # noqa: F811
    monkeypatch,
    status,
    error,
    body,  # noqa: F811
):
    from commands.source_commands import SourceProcessingInput, process_source_command
    from open_notebook.database.repository import repo_query
    from open_notebook.domain.notebook import Asset, Source
    from open_notebook.ocr.docling_extract import IncompleteConversionError

    _, native, path = native_source
    result = SimpleNamespace(
        status=status,
        errors=[SimpleNamespace(module_name="synthetic stage", page_no=2)]
        if error
        else [],
        document=SimpleNamespace(export_to_markdown=lambda: body),
    )
    monkeypatch.setattr(
        native,
        "DocumentConverter",
        lambda **_: SimpleNamespace(convert=lambda _: result),
    )
    source = Source(title="Synthetic", asset=Asset(file_path=str(path)))
    await source.save()
    with pytest.raises(IncompleteConversionError):
        await process_source_command(
            SourceProcessingInput(
                source_id=source.id,
                content_state={"file_path": str(path)},
                notebook_ids=[],
                transformations=[],
                embed=True,
            )
        )
    assert (await Source.get(source.id)).full_text is None
    assert await repo_query("SELECT * FROM command WHERE name = 'embed_source'") == []


@pytest.mark.asyncio
async def test_sync_timeout_removes_the_source_before_leaving_request(monkeypatch):
    from api.routers import sources

    source = SimpleNamespace(
        id="source:synthetic", save=AsyncMock(), delete=AsyncMock()
    )
    monkeypatch.setattr(sources, "Source", lambda **_: source)

    def timeout(*_, **__):
        raise TimeoutError("synthetic 300-second deadline")

    monkeypatch.setattr(sources, "execute_command_sync", timeout)
    data = sources.SourceCreate(type="text", content="Synthetic document", embed=True)
    with pytest.raises(TimeoutError):
        await sources._create_source_sync_path(
            data, {"content": "Synthetic document"}, []
        )
    source.delete.assert_awaited_once()


def test_known_non_pdf_uses_upstream_floating_serializer():
    pytest.importorskip("docling")
    from docling_core.types.doc import DocItemLabel, DoclingDocument, TableData
    from docling_core.types.doc.document import DocumentOrigin

    from open_notebook.ocr.docling_patches import apply_text_preservation

    assert apply_text_preservation(required=True)
    doc = DoclingDocument(
        name="synthetic",
        origin=DocumentOrigin(
            filename="demo.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            binary_hash=0,
        ),
    )
    table = doc.add_table(data=TableData(num_rows=0, num_cols=0, table_cells=[]))
    note = doc.add_text(
        label=DocItemLabel.FOOTNOTE, text="Synthetic attached note", parent=table
    )
    table.footnotes.append(note.get_ref())
    assert "Synthetic attached note" not in doc.export_to_markdown()


@pytest.mark.parametrize("fmt", ["markdown", "html", "json"])
def test_empty_document_never_accepts_serializer_markup_as_text(fmt):
    from docling_core.types.doc import DoclingDocument

    from open_notebook.ocr import docling_extract

    doc = DoclingDocument(name="synthetic")
    doc.add_picture()
    with pytest.raises(
        docling_extract.IncompleteConversionError, match="empty document"
    ):
        docling_extract._require_text(docling_extract._export(doc, fmt))
