import pytest

import backend.freqblog as freqblog
from backend.freqblog import lookup_track_metadata


def lookup_tracks_metadata(tracks):
    assert hasattr(freqblog, "lookup_tracks_metadata"), "lookup_tracks_metadata is not implemented"
    return freqblog.lookup_tracks_metadata(tracks)


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class RecordingClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_bulk_lookup_prefers_isrc_and_preserves_input_mapping(monkeypatch):
    client = RecordingClient([
        FakeResponse(200, {
            "results": [{
                "isrc": "US123",
                "found": True,
                "result": {
                    "bpm": 128.0,
                    "bpm_alt": None,
                    "bpm_confidence": 4.2,
                    "key": "A-Minor",
                    "key_confidence": 0.9,
                    "camelot": "8A",
                    "open_key": "1m",
                    "genre": "electronic",
                },
            }],
        }),
    ])
    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    result = await lookup_tracks_metadata([{
        "id": 7,
        "title": "Night Drive",
        "artist": "The Pilot",
        "isrc": "US123",
    }])

    assert client.requests[0][1]["json"] == [{
        "isrc": "US123",
        "track": "Night Drive",
        "artist": "The Pilot",
    }]
    assert result[7]["status"] == "found"
    assert result[7]["data"]["camelot"] == "8A"
    assert result[7]["data"]["genre"] == "electronic"


@pytest.mark.asyncio
async def test_bulk_lookup_splits_requests_at_fifty_items(monkeypatch):
    payloads = []

    class BatchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            payload = kwargs["json"]
            payloads.append(payload)
            return FakeResponse(200, {
                "results": [
                    {
                        "track": row.get("track"),
                        "artist": row.get("artist"),
                        "isrc": row.get("isrc"),
                        "found": False,
                        "result": None,
                    }
                    for row in payload
                ],
            })

    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: BatchClient())
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    tracks = [{"id": index, "title": f"Track {index}", "artist": "Artist"} for index in range(51)]
    result = await lookup_tracks_metadata(tracks)

    assert [len(payload) for payload in payloads] == [50, 1]
    assert list(result) == list(range(51))
    assert all(item["status"] == "miss" for item in result.values())


@pytest.mark.asyncio
async def test_bulk_lookup_maps_queued_and_rate_limited_statuses_without_raising(monkeypatch):
    client = RecordingClient([
        FakeResponse(200, {"results": [{"found": False, "backfill_status": "queued", "result": None}]}),
        FakeResponse(429, {"detail": "quota exceeded"}),
    ])
    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    queued = await lookup_tracks_metadata([{"id": 1, "title": "Queued", "artist": "Artist"}])
    limited = await lookup_tracks_metadata([{"id": 2, "title": "Limited", "artist": "Artist"}])

    assert queued[1]["status"] == "queued"
    assert limited[2]["status"] == "rate_limited"


@pytest.mark.asyncio
async def test_bulk_lookup_marks_provider_misses_and_malformed_responses(monkeypatch):
    client = RecordingClient([
        FakeResponse(200, {"unexpected": []}),
        FakeResponse(404, {"detail": "not found"}),
    ])
    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    malformed = await lookup_tracks_metadata([{"id": 1, "title": "Unknown", "artist": "Artist"}])
    missing = await lookup_tracks_metadata([{"id": 2, "title": "Missing", "artist": "Artist"}])

    assert malformed[1]["status"] == "unavailable"
    assert missing[2]["status"] == "miss"


@pytest.mark.asyncio
async def test_bulk_lookup_skips_provider_when_api_key_is_missing(monkeypatch):
    class UnexpectedClient:
        def __init__(self, **kwargs):
            raise AssertionError("client should not be created without an API key")

    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", UnexpectedClient)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", None)

    result = await lookup_tracks_metadata([{"id": 7, "title": "Night Drive", "artist": "The Pilot"}])

    assert result == {7: {"status": "unavailable", "data": None}}


@pytest.mark.asyncio
async def test_single_lookup_uses_isrc_only_and_preserves_partial_metadata(monkeypatch):
    client = RecordingClient([
        FakeResponse(200, {"bpm": 128.0, "key": None, "camelot": None, "genre": "electronic"}),
    ])
    monkeypatch.setattr("backend.freqblog.httpx.AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr("backend.freqblog.FREQBLOG_API_KEY", "test-key")

    result = await lookup_track_metadata("Night Drive", "The Pilot", isrc="US123")

    assert client.requests[0][1]["params"] == {"isrc": "US123"}
    assert result["bpm"] == 128.0
    assert result["key"] is None
    assert result["genre"] == "electronic"
