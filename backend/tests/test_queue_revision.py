import aiosqlite
import pytest
import pytest_asyncio

from backend.models import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "queue.db"))
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_queue_revision_increments_and_is_rereadable(db):
    item = await db.add_to_queue(
        "123", "track", "Song", "Artist", "Album", "high_lossless", "FLAC"
    )
    assert item["revision"] == 1

    updated = await db.update_queue_status(item["id"], "downloading", progress=25.0)
    assert updated["revision"] == 2
    assert updated["progress"] == 25.0
    assert (await db.get_queue_item(item["id"]))["revision"] == 2


@pytest.mark.asyncio
async def test_legacy_queue_gets_idempotent_revision_migration(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = await aiosqlite.connect(db_path)
    await connection.execute(
        """CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tidal_id TEXT NOT NULL,
            item_type TEXT NOT NULL DEFAULT 'track',
            title TEXT NOT NULL,
            artist TEXT NOT NULL DEFAULT '',
            album TEXT NOT NULL DEFAULT '',
            quality TEXT NOT NULL DEFAULT 'high_lossless',
            format TEXT NOT NULL DEFAULT 'FLAC',
            status TEXT NOT NULL DEFAULT 'queued',
            progress REAL NOT NULL DEFAULT 0.0,
            error TEXT,
            from_collection INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    await connection.execute(
        "INSERT INTO queue (tidal_id, title) VALUES ('legacy', 'Legacy Song')"
    )
    await connection.commit()
    await connection.close()

    database = Database(str(db_path))
    await database.init()
    try:
        columns = await database._conn.execute_fetchall("PRAGMA table_info(queue)")
        assert "revision" in {column["name"] for column in columns}
        assert (await database.get_queue())[0]["revision"] == 0

        await database.close()
        await database.init()
        assert (await database.get_queue())[0]["revision"] == 0
    finally:
        await database.close()
