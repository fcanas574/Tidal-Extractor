import asyncio
import pytest
import pytest_asyncio
from backend.models import Database


@pytest_asyncio.fixture
async def db():
    db = Database(":memory:")
    await db.init()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_get_history_paginated(db):
    await db.add_to_history("1", "track", "Song A", "Artist", "Album", "lossless", "FLAC", "/path/a.flac", 1000, 900)
    await asyncio.sleep(1.1)  # Ensure distinct downloaded_at timestamps (SQLite second granularity)
    await db.add_to_history("2", "track", "Song B", "Artist", "Album", "high", "MP3", "/path/b.mp3", 500, 320)

    all_items = await db.get_history(limit=10, offset=0)
    assert len(all_items) == 2
    assert all_items[0]["tidal_id"] == "2"  # DESC order

    page = await db.get_history(limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["tidal_id"] == "1"
