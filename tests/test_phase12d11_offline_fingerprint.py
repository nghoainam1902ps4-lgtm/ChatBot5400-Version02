"""Content comparison using an isolated database and no console payload."""

import asyncio
import json
import runpy
from pathlib import Path

import pytest
from test_phase12d9_ocr_failure_safety import database as database

from open_notebook.database import repository as db
from open_notebook.domain.notebook import Source
from scripts.offline import offline_package


@pytest.mark.usefixtures("database")
def test_probe_detects_business_changes_and_is_order_independent(capsys, monkeypatch):
    async def seed():
        source = Source(title="Synthetic", full_text="review fixture private body")
        await source.save()
        return source, await db.repo_insert(
            "source_embedding",
            [
                {
                    "source": db.ensure_record_id(source.id),
                    "order": 0,
                    "content": "review fixture private chunk",
                    "embedding": [0.25],
                },
                {
                    "source": db.ensure_record_id(source.id),
                    "order": 1,
                    "content": "another review fixture private chunk",
                    "embedding": [0.5],
                },
            ],
        )

    source, rows = asyncio.run(seed())

    def snapshot():
        exec(offline_package.FINGERPRINT_PROBE, {})
        output = capsys.readouterr().out
        assert "review fixture private" not in output
        result = offline_package.make_fingerprint(
            json.loads(output.split("FINGERPRINT ")[1])
        )
        return {
            "kind": "chatbot5400-offline-snapshot",
            "db": {"running": True},
            "data": result["summary"],
            "records": result["ids"],
        }

    original = snapshot()
    assert (
        offline_package.compare_snapshots(original, snapshot(), no_writes=True)[0] == 0
    )
    original_query = db.repo_query

    async def reverse(query, variables=None):
        return list(reversed(await original_query(query, variables)))

    with monkeypatch.context() as patch:
        patch.setattr(db, "repo_query", reverse)
        assert snapshot() == original

    rid = db.ensure_record_id(rows[0]["id"])
    for field, value in (
        ("embedding", [0.125]),
        ("content", "different chunk"),
        ("order", 9),
    ):
        earlier = snapshot()
        asyncio.run(db.repo_update("source_embedding", rid, {field: value}))
        assert (
            offline_package.compare_snapshots(earlier, snapshot(), no_writes=True)[0]
            != 0
        )

    earlier = snapshot()
    asyncio.run(
        db.repo_query(
            "UPDATE $id SET full_text = 'different body'",
            {"id": db.ensure_record_id(source.id)},
        )
    )
    assert (
        offline_package.compare_snapshots(earlier, snapshot(), no_writes=True)[0] != 0
    )
    earlier = snapshot()
    asyncio.run(db.repo_delete(rid))
    assert (
        offline_package.compare_snapshots(earlier, snapshot(), no_writes=True)[0] != 0
    )


def test_no_writes_rejects_missing_content_fingerprint():
    snapshot = {
        "kind": "chatbot5400-offline-snapshot",
        "db": {"running": True},
        "records": {},
        "data": {"tables": {}},
    }
    assert offline_package.compare_snapshots(snapshot, snapshot, no_writes=True)[0] != 0


def test_no_writes_rejects_unreadable_fingerprint(monkeypatch):
    async def fail(*_, **__):
        raise RuntimeError("synthetic server read failure")

    monkeypatch.setattr(db, "repo_query", fail)
    with pytest.raises(RuntimeError, match="synthetic server read failure"):
        exec(offline_package.FINGERPRINT_PROBE, {})


@pytest.mark.usefixtures("database")
def test_phase12f1_eight_controls_and_live_metadata(capsys):
    fixture = Path(__file__).parent / "fixtures/phase12f1/f0_synthetic.py"
    f0 = runpy.run_path(str(fixture))
    cases = f0["CASES"]
    assert len(cases) == 8

    def snapshot():
        capsys.readouterr()
        exec(offline_package.FINGERPRINT_PROBE, {})
        line = capsys.readouterr().out.split("FINGERPRINT ", 1)[1]
        live = offline_package.make_fingerprint(json.loads(line))
        assert offline_package._has_content_fingerprint(live["summary"])
        return live["summary"]

    for case, (table, _, _) in cases.items():
        asyncio.run(f0["seed"](True))
        before = snapshot()
        assert before["tables"]["source_embedding"]["count"] == 12
        asyncio.run(f0["mutate"](case))
        after = snapshot()
        assert before["sha256"] != after["sha256"], case
        assert before["tables"][table] != after["tables"][table], case

    async def live_control():
        async with db.db_connection() as connection:
            await connection.query("DEFINE TABLE IF NOT EXISTS command SCHEMALESS")
            await connection.query("LIVE SELECT * FROM command")
            runtime_before = await connection.query("INFO FOR TABLE command")
            schema_before = await connection.query("INFO FOR DB")
            before = await asyncio.to_thread(snapshot)
            await connection.query("LIVE SELECT * FROM command")
            runtime_after = await connection.query("INFO FOR TABLE command")
            assert len(runtime_after["lives"]) == len(runtime_before["lives"]) + 1
            assert await connection.query("INFO FOR DB") == schema_before
            assert await asyncio.to_thread(snapshot) == before

    asyncio.run(live_control())
