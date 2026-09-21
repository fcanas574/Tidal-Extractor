import pytest
import pytest_asyncio

from backend.catalog_metadata import enrich_catalog_tracks, merge_catalog_metadata
from backend.models import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "catalog-metadata.db"))
    await database.init()
    yield database
    await database.close()


def test_merge_catalog_metadata_preserves_tidal_bpm_and_key():
    track = {"id": 7, "bpm": 126.0, "key": "C", "key_scale": "MINOR", "genre": None}
    lookup = {"status": "found", "data": {
        "bpm": 128.0, "key": "A-Minor", "camelot": "8A",
        "bpm_alt": 64.0, "genre": "electronic",
    }}

    result = merge_catalog_metadata(track, lookup)

    assert result["bpm"] == 126.0
    assert result["bpm_source"] == "tidal"
    assert result["key"] == "C"
    assert result["key_source"] == "tidal"
    assert result["genre"] == "electronic"
    assert result["genre_source"] == "freqblog"
    assert result["camelot"] == "8A"


def test_merge_catalog_metadata_fills_missing_dj_fields():
    result = merge_catalog_metadata(
        {"id": 7, "bpm": None, "key": None, "key_scale": None, "genre": None},
        {"status": "found", "data": {
            "bpm": 128.0, "key": "A-Minor", "camelot": "8A",
            "key_confidence": 0.9, "genre": "electronic",
        }},
    )

    assert result["bpm"] == 128.0
    assert result["bpm_source"] == "freqblog"
    assert result["key_source"] == "freqblog"
    assert result["key_confidence"] == 0.9


@pytest.mark.asyncio
async def test_enrich_catalog_tracks_uses_cache_before_provider(monkeypatch, db):
    await db.set_catalog_metadata([{
        "tidal_id": 7,
        "isrc": "US123",
        "data": {"bpm": 128.0, "genre": "electronic", "camelot": "8A"},
        "status": "found",
        "checked_at": 100.0,
        "expires_at": 9999999999.0,
    }])

    async def provider_must_not_run(tracks):
        raise AssertionError("cache hit should skip FreqBlog")

    monkeypatch.setattr("backend.catalog_metadata.lookup_tracks_metadata", provider_must_not_run)
    result = await enrich_catalog_tracks(
        db,
        [{"id": 7, "title": "Night Drive", "artist": "The Pilot", "bpm": None, "key": None, "genre": None}],
        required_fields={"bpm", "genre"},
    )

    assert result[0]["bpm"] == 128.0
    assert result[0]["genre"] == "electronic"
    assert result[0]["metadata_status"] == "complete"


@pytest.mark.asyncio
async def test_enrich_catalog_tracks_requests_only_missing_tracks_and_preserves_order(monkeypatch, db):
    requested = []

    async def provider(tracks):
        requested.extend(track["id"] for track in tracks)
        return {
            8: {"status": "found", "data": {"bpm": 124.0, "key": "G", "genre": "house", "camelot": "9B"}},
            9: {"status": "miss", "data": None},
        }

    monkeypatch.setattr("backend.catalog_metadata.lookup_tracks_metadata", provider)
    tracks = [
        {"id": 7, "title": "Complete", "artist": "A", "bpm": 120.0, "key": "C", "genre": "pop"},
        {"id": 8, "title": "Missing", "artist": "B", "bpm": None, "key": None, "genre": None},
        {"id": 9, "title": "Unknown", "artist": "C", "bpm": None, "key": "D", "genre": None},
    ]

    result = await enrich_catalog_tracks(db, tracks, required_fields={"bpm", "key", "genre"})

    assert requested == [8, 9]
    assert [track["id"] for track in result] == [7, 8, 9]
    assert result[1]["bpm"] == 124.0
    assert result[1]["genre"] == "house"
    assert result[1]["metadata_status"] == "complete"
    assert result[2]["metadata_status"] == "partial"
    cached = await db.get_catalog_metadata([8, 9])
    assert cached[8]["status"] == "found"
    assert cached[9]["status"] == "miss"


@pytest.mark.asyncio
async def test_enrich_catalog_tracks_preserves_explicitly_empty_required_fields(monkeypatch, db):
    async def provider_must_not_run(tracks):
        raise AssertionError("empty required fields should not request provider metadata")

    monkeypatch.setattr("backend.catalog_metadata.lookup_tracks_metadata", provider_must_not_run)
    result = await enrich_catalog_tracks(
        db,
        [{"id": 7, "title": "Unrefined", "artist": "Artist", "bpm": None, "key": None, "genre": None}],
        required_fields=set(),
    )

    assert result[0]["metadata_status"] == "complete"
