import pytest
import pytest_asyncio
from backend.models import Database

TEST_DB = "test_models.db"


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = str(tmp_path / TEST_DB)
    database = Database(db_path)
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_add_and_get_queue_item(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    assert item["id"] == 1
    assert item["status"] == "queued"

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "12345"
    assert queue[0]["title"] == "Test Song"


@pytest.mark.asyncio
async def test_update_queue_status(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    await db.update_queue_status(item["id"], "downloading")
    queue = await db.get_queue()
    assert queue[0]["status"] == "downloading"


@pytest.mark.asyncio
async def test_remove_from_queue(db):
    item = await db.add_to_queue(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
    )
    await db.remove_from_queue(item["id"])
    queue = await db.get_queue()
    assert len(queue) == 0


@pytest.mark.asyncio
async def test_remove_completed(db):
    item1 = await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    item2 = await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )
    await db.update_queue_status(item1["id"], "complete")
    await db.update_queue_status(item2["id"], "downloading")

    removed = await db.remove_completed()
    assert removed == 1

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "2"


@pytest.mark.asyncio
async def test_remove_batch(db):
    item1 = await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    item2 = await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )
    item3 = await db.add_to_queue(
        tidal_id="3", item_type="track", title="Song C",
        artist="C", album="C", quality="high_lossless", format="FLAC",
    )

    removed = await db.remove_batch([item1["id"], item3["id"]])
    assert removed == 2

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "2"


@pytest.mark.asyncio
async def test_remove_all(db):
    await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )

    removed = await db.remove_all()
    assert removed == 2

    queue = await db.get_queue()
    assert len(queue) == 0


@pytest.mark.asyncio
async def test_add_to_history(db):
    await db.add_to_history(
        tidal_id="12345",
        item_type="track",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        quality="high_lossless",
        format="FLAC",
        file_path="/music/test.flac",
        file_size=27000000,
        actual_bitrate=1011,
    )
    history = await db.get_history()
    assert len(history) == 1
    assert history[0]["actual_bitrate"] == 1011


@pytest.mark.asyncio
async def test_quality_cache_set_and_get(db):
    await db.set_quality_cache("high_lossless", 1011)
    cached = await db.get_quality_cache()
    assert cached == {"preset": "high_lossless", "bitrate": 1011}

    await db.clear_quality_cache()
    cached = await db.get_quality_cache()
    assert cached is None


@pytest.mark.asyncio
async def test_catalog_metadata_cache_round_trips_normalized_data(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7,
        "isrc": "US123",
        "data": {"bpm": 128.0, "camelot": "8A", "genre": "electronic"},
        "status": "found",
        "checked_at": 100.0,
        "expires_at": 200.0,
    }])

    result = await db.get_catalog_metadata([7], now=150.0)

    assert result[7]["data"]["bpm"] == 128.0
    assert result[7]["status"] == "found"


@pytest.mark.asyncio
async def test_expired_catalog_metadata_is_not_returned(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": None, "data": {}, "status": "queued",
        "checked_at": 100.0, "expires_at": 120.0,
    }])

    assert await db.get_catalog_metadata([7], now=121.0) == {}


@pytest.mark.asyncio
async def test_catalog_metadata_upsert_replaces_previous_status(db):
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": None, "data": {}, "status": "queued",
        "checked_at": 100.0, "expires_at": 200.0,
    }])
    await db.set_catalog_metadata([{
        "tidal_id": 7, "isrc": "US123", "data": {"bpm": 128.0}, "status": "found",
        "checked_at": 150.0, "expires_at": 300.0,
    }])

    result = await db.get_catalog_metadata([7], now=200.0)

    assert result[7]["status"] == "found"
    assert result[7]["data"] == {"bpm": 128.0}
