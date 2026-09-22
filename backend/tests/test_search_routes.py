import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import backend.main as main

pytestmark = pytest.mark.asyncio


@pytest.fixture
def authenticated(monkeypatch):
    auth = MagicMock()
    auth.is_authenticated = True
    auth.session = MagicMock()
    auth.session.track.side_effect = RuntimeError("track enrichment disabled")
    monkeypatch.setattr(main, "auth_manager", auth)
    main._search_results_cache.clear()
    return auth


@pytest.fixture
def typed_search_results():
    return {
        "tracks": [{"id": 1, "title": "Track One"}],
        "artists": [
            {"id": 10, "name": "Artist One"},
            {"id": 11, "name": "Artist Two"},
        ],
        "albums": [
            {"id": 20, "name": "Album One"},
            {"id": 21, "name": "Album Two"},
        ],
        "playlists": [{"id": "playlist-1", "name": "Playlist One"}],
    }


async def test_search_route_returns_typed_page_and_metadata(
    monkeypatch, authenticated, typed_search_results
):
    search_mock = MagicMock(return_value=typed_search_results)
    monkeypatch.setattr(main, "search_tidal", search_mock)

    result = await main.search(q="  Mitski  ", type="artist", offset=1, limit=1)

    assert result["tracks"] == []
    assert result["artists"] == [{"id": 11, "name": "Artist Two"}]
    assert result["albums"] == []
    assert result["playlists"] == []
    assert result["offset"] == 1
    assert result["limit"] == 1
    assert result["has_more"] is False

    search_mock.assert_called_once()
    assert search_mock.call_args.args[2] == ["artist"]
    assert search_mock.call_args.kwargs["limit"] == 300
    assert search_mock.call_args.kwargs["offset"] == 0


async def test_search_route_supports_album_results(monkeypatch, authenticated):
    albums = [
        {"id": 20, "name": "Album One"},
        {"id": 21, "name": "Album Two"},
    ]
    monkeypatch.setattr(
        main,
        "search_tidal",
        MagicMock(
            return_value={
                "tracks": [],
                "artists": [],
                "albums": albums,
                "playlists": [],
            }
        ),
    )

    result = await main.search(q="Album", type="album", offset=0, limit=1)

    assert result["albums"] == [albums[0]]
    assert result["has_more"] is True


async def test_search_route_rejects_unknown_type(monkeypatch, authenticated):
    with pytest.raises(HTTPException) as exc_info:
        await main.search(q="anything", type="video")

    assert exc_info.value.status_code == 400


async def test_search_cache_is_scoped_to_page_and_refreshable(
    monkeypatch, authenticated
):
    search_mock = MagicMock(
        return_value={
            "tracks": [
                {"id": 1, "title": "Track One"},
                {"id": 2, "title": "Track Two"},
            ],
            "artists": [],
            "albums": [],
            "playlists": [],
        }
    )
    monkeypatch.setattr(main, "search_tidal", search_mock)

    first_page = await main.search(q="  Track  ", type="track", offset=0, limit=1)
    cached_first_page = await main.search(q="track", type="track", offset=0, limit=1)
    second_page = await main.search(q="Track", type="track", offset=1, limit=1)
    refreshed_page = await main.search(
        q="Track", type="track", offset=0, limit=1, refresh=True
    )

    assert first_page["tracks"] == [{"id": 1, "title": "Track One"}]
    assert cached_first_page["tracks"] == first_page["tracks"]
    assert second_page["tracks"] == [{"id": 2, "title": "Track Two"}]
    assert refreshed_page["tracks"] == first_page["tracks"]
    assert search_mock.call_count == 3


async def test_unfiltered_search_merges_cached_metadata_and_schedules_background_work(
    monkeypatch, authenticated
):
    track = {
        "id": 7,
        "title": "Night Drive",
        "artist": "Pilot",
        "bpm": None,
        "key": None,
    }
    cached_track = {**track, "genre": "dance", "metadata_status": "partial"}
    monkeypatch.setattr(
        main,
        "search_tidal",
        MagicMock(return_value={"tracks": [track], "artists": [], "albums": [], "playlists": []}),
    )
    enrich = AsyncMock(return_value=[cached_track])
    jobs = MagicMock()
    jobs.schedule.return_value = True
    monkeypatch.setattr(main, "_enrich_response_tracks", enrich)
    monkeypatch.setattr(main, "search_metadata_jobs", jobs)
    monkeypatch.setattr(main, "enrich_tracks", lambda session, tracks, top_n: tracks)

    result = await main.search(q="Night Drive", type="track")

    assert result["tracks"][0]["genre"] == "dance"
    assert result["metadata_pending"] is True
    enrich.assert_awaited_once_with(
        [track], required_fields={"bpm", "key", "genre"}, lookup_limit=0
    )
    assert jobs.schedule.call_args.args[1] == [cached_track]


async def test_filtered_search_enriches_before_filtering_without_background_job(
    monkeypatch, authenticated
):
    track = {
        "id": 7,
        "title": "Night Drive",
        "artist": "Pilot",
        "bpm": None,
        "key": None,
        "key_scale": None,
    }
    monkeypatch.setattr(
        main,
        "search_tidal",
        MagicMock(return_value={"tracks": [track], "artists": [], "albums": [], "playlists": []}),
    )
    calls = []

    async def enrich(tracks, *, required_fields, lookup_limit=None):
        calls.append((required_fields, lookup_limit))
        return [{**track, "camelot": "8A", "metadata_status": "complete"}]

    jobs = MagicMock()
    monkeypatch.setattr(main, "_enrich_response_tracks", enrich)
    monkeypatch.setattr(main, "search_metadata_jobs", jobs)
    monkeypatch.setattr(main, "enrich_tracks", lambda session, tracks, top_n: tracks)

    result = await main.search(q="Night Drive", type="track", key="8A")

    assert result["tracks"][0]["camelot"] == "8A"
    assert calls[0] == ({"bpm", "key"}, None)
    jobs.schedule.assert_not_called()


async def test_metadata_completion_updates_matching_cache_and_broadcasts(monkeypatch):
    key = "matching-page"
    original = {"id": 7, "title": "Night Drive", "genre": None}
    enriched = {**original, "genre": "dance", "genre_source": "freqblog"}
    main._search_results_cache[key] = main._SearchCacheEntry(
        expires_at=time.monotonic() + 60,
        result={
            "tracks": [original],
            "artists": [],
            "albums": [],
            "playlists": [],
            "offset": 0,
            "limit": 50,
            "has_more": False,
            "metadata_pending": True,
        },
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(main.ws_manager, "broadcast", broadcast)

    await main._apply_search_metadata_completion({key: (7,)}, [enriched])

    assert main._search_results_cache[key].result["tracks"] == [enriched]
    assert main._search_results_cache[key].result["metadata_pending"] is False
    broadcast.assert_awaited_once_with({"type": "catalog_metadata", "tracks": [enriched]})


async def test_metadata_completion_does_not_overwrite_changed_cache_page(monkeypatch):
    key = "refreshed-page"
    current = {"id": 99, "title": "New Search"}
    main._search_results_cache[key] = main._SearchCacheEntry(
        expires_at=time.monotonic() + 60,
        result={
            "tracks": [current],
            "artists": [],
            "albums": [],
            "playlists": [],
            "offset": 0,
            "limit": 50,
            "has_more": False,
            "metadata_pending": True,
        },
    )
    broadcast = AsyncMock()
    monkeypatch.setattr(main.ws_manager, "broadcast", broadcast)

    await main._apply_search_metadata_completion(
        {key: (7,)}, [{"id": 7, "title": "Old Search", "genre": "dance"}]
    )

    assert main._search_results_cache[key].result["tracks"] == [current]
    assert main._search_results_cache[key].result["metadata_pending"] is True
    broadcast.assert_awaited_once()


async def test_search_cache_expires(monkeypatch, authenticated):
    search_mock = MagicMock(
        return_value={"tracks": [], "artists": [], "albums": [], "playlists": []}
    )
    monkeypatch.setattr(main, "search_tidal", search_mock)
    monkeypatch.setattr(main, "_SEARCH_CACHE_TTL_SECONDS", 0, raising=False)

    await main.search(q="Track", type="track")
    await main.search(q="Track", type="track")

    assert search_mock.call_count == 2


async def test_search_route_enriches_before_dj_filtering(monkeypatch, authenticated):
    raw_track = {
        "id": 7,
        "title": "Night Drive",
        "artist": "The Pilot",
        "bpm": None,
        "key": None,
        "key_scale": None,
    }
    monkeypatch.setattr(
        main,
        "search_tidal",
        MagicMock(return_value={"tracks": [raw_track], "artists": [], "albums": [], "playlists": []}),
    )

    async def enrich(tracks, *, required_fields, lookup_limit=None):
        return [{**track, "bpm": 128.0, "key": None, "camelot": "8A", "genre": "house"} for track in tracks]

    monkeypatch.setattr(main, "_enrich_response_tracks", enrich, raising=False)

    result = await main.search(q="Night Drive", type="track", key="8A")

    assert result["tracks"] == [{**raw_track, "bpm": 128.0, "key": None, "camelot": "8A", "genre": "house"}]


async def test_search_route_keeps_raw_tracks_when_enrichment_fails(monkeypatch, authenticated):
    raw_track = {"id": 8, "title": "Fallback", "artist": "Artist", "bpm": None, "key": None}
    monkeypatch.setattr(
        main,
        "search_tidal",
        MagicMock(return_value={"tracks": [raw_track], "artists": [], "albums": [], "playlists": []}),
    )
    async def enrich_catalog_metadata_fails(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "enrich_catalog_tracks", enrich_catalog_metadata_fails)

    result = await main.search(q="Fallback", type="track")

    assert result["tracks"] == [raw_track]


async def test_artist_id_route_uses_shared_artist_detail_helper(
    monkeypatch, authenticated
):
    expected = {
        "artist": {"id": 42, "name": "Test Artist"},
        "top_tracks": [],
        "albums": [],
    }
    helper = MagicMock(return_value=expected)
    monkeypatch.setattr(main, "get_artist_details", helper)

    result = await main.artist_details(42)

    assert result == {**expected, "tracks": [], "playlists": []}
    helper.assert_called_once_with(authenticated.session, 42)


async def test_artist_summary_route_returns_overview_without_full_track_wait(
    monkeypatch, authenticated
):
    expected = {
        "artist": {"id": 42, "name": "Test Artist"},
        "top_tracks": [],
        "tracks": [],
        "albums": [],
    }
    helper = MagicMock(return_value=expected)
    monkeypatch.setattr(main, "get_artist_summary", helper)

    result = await main.artist_summary(42)

    assert result == {**expected, "playlists": []}
    helper.assert_called_once_with(authenticated.session, 42)


async def test_artist_summary_route_enriches_top_tracks(monkeypatch, authenticated):
    expected = {
        "artist": {"id": 42, "name": "Test Artist"},
        "top_tracks": [{"id": 7, "title": "Night Drive"}],
        "tracks": [],
        "albums": [],
    }
    monkeypatch.setattr(main, "get_artist_summary", MagicMock(return_value=expected))
    calls = []

    async def enrich(tracks, *, required_fields, lookup_limit=None):
        calls.append((tracks, required_fields))
        return [{**track, "genre": "house"} for track in tracks]

    monkeypatch.setattr(main, "_enrich_response_tracks", enrich, raising=False)

    result = await main.artist_summary(42)

    assert result["top_tracks"] == [{"id": 7, "title": "Night Drive", "genre": "house"}]
    assert calls[0][0] == expected["top_tracks"]


async def test_album_tracks_route_enriches_tracks(monkeypatch, authenticated):
    expected = {
        "album": {"id": 42, "name": "After Hours"},
        "tracks": [{"id": 7, "title": "Night Drive"}],
    }
    monkeypatch.setattr(main, "get_album_details", MagicMock(return_value=expected))

    async def enrich(tracks, *, required_fields, lookup_limit=None):
        return [{**track, "genre": "house"} for track in tracks]

    monkeypatch.setattr(main, "_enrich_response_tracks", enrich, raising=False)

    result = await main.album_tracks(42)

    assert result["tracks"] == [{"id": 7, "title": "Night Drive", "genre": "house"}]


async def test_artist_tracks_route_returns_full_track_catalog(
    monkeypatch, authenticated
):
    expected = {"tracks": [{"id": 7, "title": "Night Drive"}]}
    helper = MagicMock(return_value=expected)
    monkeypatch.setattr(main, "get_artist_tracks", helper)

    result = await main.artist_tracks(42)

    assert result == expected
    helper.assert_called_once_with(authenticated.session, 42)


async def test_album_tracks_route_returns_album_metadata_and_tracks(
    monkeypatch, authenticated
):
    expected = {
        "album": {"id": 42, "name": "After Hours"},
        "tracks": [{"id": 7, "title": "Night Drive"}],
    }
    helper = MagicMock(return_value=expected)
    monkeypatch.setattr(main, "get_album_details", helper)

    result = await main.album_tracks(42)

    assert result == expected
    helper.assert_called_once_with(authenticated.session, 42)
