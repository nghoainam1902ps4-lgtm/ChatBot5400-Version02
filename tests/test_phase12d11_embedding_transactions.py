"""Publication tests against an isolated embedded SurrealDB with app migrations."""

import asyncio

import pytest
from test_phase12d9_ocr_failure_safety import database as database

from commands import embedding_commands as embedding
from open_notebook.database import repository as db
from open_notebook.domain.notebook import Notebook, Source

pytestmark = pytest.mark.usefixtures("database")


async def _source(value="prior document"):
    source = Source(title="Synthetic", full_text=value)
    await source.save()
    await db.repo_insert(
        "source_embedding",
        [
            {
                "source": db.ensure_record_id(source.id),
                "order": 0,
                "content": value,
                "embedding": [0.25],
            }
        ],
    )
    return source


async def _vectors(source):
    return await db.repo_query(
        "SELECT content, embedding FROM source_embedding WHERE source = $sid",
        {"sid": db.ensure_record_id(source.id)},
    )


def _job(source):
    return embedding.embed_source_command(
        embedding.EmbedSourceInput(source_id=source.id)
    )


@pytest.fixture(autouse=True)
def chunks(monkeypatch):
    monkeypatch.setattr(embedding, "chunk_text", lambda text, **_: [text])


@pytest.mark.asyncio
async def test_reembed_replaces_and_reprocess_retires_stale_vectors(monkeypatch):
    async def generate(*_, **__):
        return [[0.75]]

    monkeypatch.setattr(embedding, "generate_embeddings", generate)
    source = await _source()
    assert (await _job(source)).success
    assert await _vectors(source) == [
        {"content": "prior document", "embedding": [0.75]}
    ]
    source = await Source.get(source.id)
    source.full_text = "new document"
    await source.save()
    assert await _vectors(source) == []
    assert (await _job(source)).success
    assert await _vectors(source) == [{"content": "new document", "embedding": [0.75]}]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider", "count", "nonfinite", "cancel"])
async def test_generation_failure_keeps_prior_rows(monkeypatch, failure):
    source = await _source()
    started = asyncio.Event()

    async def generate(*_, **__):
        started.set()
        if failure == "provider":
            raise ValueError("synthetic provider failure")
        if failure == "count":
            return []
        if failure == "nonfinite":
            return [[float("nan")]]
        await asyncio.Event().wait()

    monkeypatch.setattr(embedding, "generate_embeddings", generate)
    task = asyncio.create_task(_job(source))
    if failure == "cancel":
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert not (await task).success
    assert await _vectors(source) == [
        {"content": "prior document", "embedding": [0.25]}
    ]


@pytest.mark.asyncio
async def test_constraint_failure_rolls_back_the_delete(monkeypatch):
    source = await _source()
    await db.repo_query(
        "DEFINE FIELD OVERWRITE embedding ON source_embedding TYPE array<float> ASSERT $value[0] < 1.0"
    )

    async def generate(*_, **__):
        return [[2.0]]

    monkeypatch.setattr(embedding, "generate_embeddings", generate)
    with pytest.raises(RuntimeError, match="transaction failed"):
        await _job(source)
    assert await _vectors(source) == [
        {"content": "prior document", "embedding": [0.25]}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["edit", "delete", "publish", "other source"])
async def test_inflight_generation_uses_current_source_revision(monkeypatch, change):
    source = await _source()
    started, resume = asyncio.Event(), asyncio.Event()
    calls = 0

    async def generate(*_, **__):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await resume.wait()
            return [[0.5]]
        return [[0.75]]

    monkeypatch.setattr(embedding, "generate_embeddings", generate)
    task = asyncio.create_task(_job(source))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        if change == "edit":
            source.full_text = "new document"
            await source.save()
        elif change == "delete":
            notebook = Notebook(name="Synthetic notebook", description="")
            await notebook.save()
            await source.add_to_notebook(notebook.id)
            assert len(await db.repo_query("SELECT * FROM reference")) == 1
            assert await source.delete()
            assert await db.repo_query("SELECT * FROM reference") == []
        elif change == "publish":
            assert (await _job(source)).success
        else:
            other = await _source("other document")
            assert (await _job(other)).success
            assert await _vectors(other) == [
                {"content": "other document", "embedding": [0.75]}
            ]
    finally:
        resume.set()
        result = await task
    assert result.success is (change == "other source")
    expected = {
        "publish": [{"content": "prior document", "embedding": [0.75]}],
        "other source": [{"content": "prior document", "embedding": [0.5]}],
    }
    assert await _vectors(source) == expected.get(change, [])
