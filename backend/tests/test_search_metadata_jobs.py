import asyncio

import pytest

from backend.search_metadata_jobs import SearchMetadataJobManager


@pytest.mark.asyncio
async def test_schedule_joins_matching_track_sets_and_notifies_all_cache_keys():
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    provider_calls = []
    notifications = []

    async def enrich(tracks):
        provider_calls.append([track["id"] for track in tracks])
        started.set()
        await release.wait()
        return [{**track, "genre": "dance", "genre_source": "freqblog"} for track in tracks]

    async def on_complete(subscriptions, tracks):
        notifications.append((subscriptions, tracks))
        completed.set()

    manager = SearchMetadataJobManager(enrich=enrich, on_complete=on_complete)
    tracks = [{"id": 7, "title": "Night Drive"}, {"id": 8, "title": "Day Shift"}]

    assert manager.schedule("first", tracks) is True
    await started.wait()
    assert manager.schedule("second", list(reversed(tracks))) is True
    release.set()
    await completed.wait()

    assert provider_calls == [[7, 8]]
    assert notifications[0][0] == {"first": (7, 8), "second": (8, 7)}
    assert notifications[0][1][0]["genre"] == "dance"
    await manager.close()


@pytest.mark.asyncio
async def test_schedule_notifies_with_original_tracks_after_enrichment_failure():
    completed = []
    finished = asyncio.Event()

    async def enrich(tracks):
        raise RuntimeError("provider unavailable")

    async def on_complete(subscriptions, tracks):
        completed.append((subscriptions, tracks))
        finished.set()

    manager = SearchMetadataJobManager(enrich=enrich, on_complete=on_complete)
    source = [{"id": 7, "title": "Night Drive"}]
    manager.schedule("search", source)
    await asyncio.wait_for(finished.wait(), timeout=1)

    assert completed == [({"search": (7,)}, source)]
    await manager.close()


@pytest.mark.asyncio
async def test_schedule_after_completion_snapshot_starts_a_new_job():
    notifications = []
    provider_calls = []
    second_completed = asyncio.Event()
    source = [{"id": 7, "title": "Night Drive"}]

    async def enrich(tracks):
        provider_calls.append([track["id"] for track in tracks])
        return tracks

    async def on_complete(subscriptions, tracks):
        notifications.append(subscriptions)
        if "first" in subscriptions:
            assert manager.schedule("second", source) is True
        else:
            second_completed.set()

    manager = SearchMetadataJobManager(enrich=enrich, on_complete=on_complete)
    assert manager.schedule("first", source) is True
    await asyncio.wait_for(second_completed.wait(), timeout=1)

    assert notifications == [{"first": (7,)}, {"second": (7,)}]
    assert provider_calls == [[7], [7]]
    await manager.close()
