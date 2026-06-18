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
async def test_increment_and_get_stat(db):
    await db.increment_stat("total_tracks", 1)
    await db.increment_stat("total_tracks", 2)
    assert await db.get_stat("total_tracks") == 3


@pytest.mark.asyncio
async def test_get_all_stats(db):
    await db.increment_stat("total_tracks", 5)
    await db.increment_stat("total_bytes", 1024)
    stats = await db.get_all_stats()
    assert stats["total_tracks"] == 5
    assert stats["total_bytes"] == 1024
