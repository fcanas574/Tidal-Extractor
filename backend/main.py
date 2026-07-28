import asyncio
import dataclasses
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import AuthManager
from backend.config import AppConfig
from backend.models import Database
from backend.search import search_tidal, get_album_tracks, get_playlist_tracks, resolve_url, score_results, enrich_tracks
from backend.downloader import DownloadOrchestrator
from backend.ws import WebSocketManager

logger = logging.getLogger(__name__)

# Configure logging level for FreqBlog debugging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("backend.freqblog").setLevel(logging.DEBUG)
logging.getLogger("backend.main").setLevel(logging.INFO)

config = AppConfig()
db = Database()
auth_manager = AuthManager()
ws_manager = WebSocketManager()
orchestrator: DownloadOrchestrator = None

# FreqBlog stats counters (in-memory, reset on restart)
freqblog_stats = {
    "hits": 0,      # FreqBlog returned data
    "misses": 0,    # Track not in FreqBlog, fell back to local
    "errors": 0,    # API errors
    "cache_hits": 0,
}

# Search results cache: cache_key -> full list of track IDs (for pagination)
_search_results_cache: dict[str, list[dict]] = {}


def _cleanup_tmp_files(output_dir: str) -> int:
    """Remove stale .tmp files from interrupted downloads. Returns count removed."""
    try:
        path = Path(output_dir).expanduser()
        if not path.is_dir():
            return 0
        removed = 0
        for f in path.glob("*.tmp"):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        if removed:
            logger.info("Cleaned up %d stale .tmp file(s) from %s", removed, path)
        return removed
    except Exception:
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    await db.init()
    _cleanup_tmp_files(config.output_dir)
    if auth_manager.load_saved_session(config.default_quality):
        orchestrator = DownloadOrchestrator(db=db, config=config, ws_manager=ws_manager)
        orchestrator.set_session(auth_manager.session)
    yield
    await db.close()


app = FastAPI(title="TidalExtractor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Endpoints ---

@app.post("/auth/device-link")
async def create_device_link():
    try:
        result = auth_manager.get_device_link()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/device-link/verify")
async def verify_device_link():
    global orchestrator
    success = await asyncio.to_thread(auth_manager.wait_for_device_auth)
    if success:
        orchestrator = DownloadOrchestrator(db=db, config=config, ws_manager=ws_manager)
        orchestrator.set_session(auth_manager.session)
        return {"authenticated": True}
    raise HTTPException(status_code=401, detail="Authentication failed")


@app.get("/auth/status")
async def get_auth_status():
    return auth_manager.get_status()


@app.post("/auth/logout")
async def logout():
    global orchestrator
    auth_manager.logout()
    orchestrator = None
    return {"authenticated": False}


# --- Search Endpoints ---

def filter_tracks_by_dj_metadata(
    tracks: List[dict],
    bpm_min: Optional[int],
    bpm_max: Optional[int],
    key: Optional[str],
    key_compatible: bool,
) -> List[dict]:
    """Filter tracks by BPM range and/or Camelot key.

    Tracks without the required metadata are excluded from filtered results.
    """
    from backend.key_detection import convert_to_camelot, get_compatible_keys

    # Expand key if compatible mode is on
    target_keys = [key] if key else []
    if key and key_compatible:
        target_keys = get_compatible_keys(key)

    filtered = []
    for track in tracks:
        # BPM filter
        track_bpm = track.get("bpm")
        if bpm_min is not None or bpm_max is not None:
            if track_bpm is None:
                continue  # Skip tracks without BPM data
            if bpm_min is not None and track_bpm < bpm_min:
                continue
            if bpm_max is not None and track_bpm > bpm_max:
                continue

        # Key filter
        if target_keys:
            track_key = track.get("key")
            track_scale = track.get("key_scale")
            if not track_key or not track_scale:
                continue  # Skip tracks without key data
            track_camelot = convert_to_camelot(track_key, track_scale)
            if not track_camelot or track_camelot not in target_keys:
                continue

        filtered.append(track)

    return filtered


@app.get("/search")
async def search(
    q: str,
    type: str = "track",
    offset: int = 0,
    limit: int = 50,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    key: Optional[str] = None,
    key_compatible: bool = False,
    genre: Optional[str] = None,
):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    models = [type] if type in ("track", "album", "playlist") else ["track", "album", "playlist"]
    artist_filter = None

    # Handle "track - artist" format
    if " - " in q and type == "track":
        parts = q.split(" - ", 1)
        q = parts[0]
        artist_filter = parts[1]

    # Prepend genre prefix if selected
    search_query = q
    if genre:
        # Tidal's genre: prefix filters by genre
        search_query = f"genre:{genre} {q}" if q else f"genre:{genre}"

    # Get raw search results - always fetch full batch (Tidal doesn't support offset)
    # Cache key: just search_query + type (filters applied per-request, not cached)
    cache_key = f"{search_query}:{type}"

    # Check cache first
    if cache_key in _search_results_cache:
        all_tracks = _search_results_cache[cache_key]
    else:
        # First request - fetch and cache ALL results (no filters yet)
        raw = await asyncio.to_thread(search_tidal, auth_manager.session, search_query, models, artist_filter=artist_filter, limit=500)
        all_tracks = raw.get("tracks", [])

        # Score and sort
        if all_tracks:
            scored = score_results(all_tracks, q, artist_filter)
            all_tracks = [t for t, _ in scored]

        # Cache unfiltered results
        _search_results_cache[cache_key] = all_tracks

    # Apply DJ filters (BPM, Key) to the full set BEFORE pagination
    filtered_tracks = all_tracks
    if (bpm_min is not None or bpm_max is not None or key):
        filtered_tracks = filter_tracks_by_dj_metadata(
            all_tracks, bpm_min, bpm_max, key, key_compatible
        )

    # Slice the page we need
    page_tracks = filtered_tracks[offset:offset + limit]

    # Enrich top 5 titles
    if page_tracks:
        page_tracks = await asyncio.to_thread(enrich_tracks, auth_manager.session, page_tracks, 5)

    return {"tracks": page_tracks, "albums": [], "playlists": []}


@app.get("/album/{album_id}/tracks")
async def album_tracks(album_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tracks = await asyncio.to_thread(get_album_tracks, auth_manager.session, album_id)
    return {"tracks": tracks}


@app.get("/playlist/{playlist_id}/tracks")
async def playlist_tracks(playlist_id: str):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tracks = await asyncio.to_thread(get_playlist_tracks, auth_manager.session, playlist_id)
    return {"tracks": tracks}


@app.get("/resolve")
async def resolve_tidal_url(url: str):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        result = await asyncio.to_thread(resolve_url, auth_manager.session, url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Content not found: {e}")
    return result


# --- Preview Endpoint ---

from backend.waveform import get_waveform_cached
from backend.preview_jobs import PreviewJobManager


async def _preview_analyzer(stream_url: str, duration: float | None, track_id: int) -> dict:
    """Background analyzer for preview metadata jobs.

    Resolves the track for key lookup, then runs waveform and key detection in
    threads / awaitables. Exceptions propagate to the PreviewJobManager, which
    converts them into a `failed` snapshot rather than crashing the app.
    """
    track = auth_manager.session.track(track_id)
    waveform = await asyncio.to_thread(get_waveform_cached, stream_url)
    key_data = await _detect_preview_key(stream_url, track_id, track)
    return {
        "waveform": waveform,
        "key": key_data.get("key"),
        "camelot": key_data.get("camelot"),
        "bpm": key_data.get("bpm"),
    }


preview_job_manager = PreviewJobManager(analyzer=_preview_analyzer)


@app.get("/preview/{track_id}")
async def preview_track(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)
        logger.info(f"Preview track {track_id}: '{track.title}' by {track.artist.name if track.artist else 'Unknown'}")

        # Use lowest quality for previews to save bandwidth
        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality
        waveform = await asyncio.to_thread(get_waveform_cached, url)

        # Pass track object for FreqBlog metadata lookup
        key_data = await _detect_preview_key(url, track_id, track)

        return {"stream_url": url, "waveform": waveform, **key_data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


@app.get("/preview/{track_id}/stream")
async def preview_stream(track_id: int):
    """Fast stream-only endpoint: resolve the LOW-quality url and return.

    Does NOT run waveform generation or key detection -- playback starts
    immediately.
    """
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)

        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality

        duration = getattr(track, "duration", None)
        return {
            "track_id": track_id,
            "stream_url": url,
            "duration": duration,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


@app.get("/preview/{track_id}/metadata")
async def preview_metadata(track_id: int):
    """Resolve the same LOW-quality url, kick off (or fetch) the preview
    metadata job, and return the current snapshot without waiting for the
    background analyzer.
    """
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)

        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality

        duration = getattr(track, "duration", None)
        snapshot = preview_job_manager.start_or_get(track_id, url, duration)
        return dataclasses.asdict(snapshot)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


async def _detect_preview_key(stream_url: str, track_id: int, track=None) -> dict:
    """Detect key/camelot for preview track.

    Uses hybrid approach:
    1. Try FreqBlog API first (fast, ~100ms, no audio download)
    2. Fall back to local audio analysis if not in FreqBlog catalog
    3. Cache results by track_id to avoid re-fetching
    """
    import tempfile
    import os as _os
    from backend.key_detection import detect_key as _dk
    from backend.freqblog import lookup_track_metadata

    # Check cache first
    cache_key = f"preview_key_{track_id}"
    logger.info(f"Checking cache for key: {cache_key}")
    cached = await db.get_key_cache(cache_key)
    if cached:
        logger.info(f"Cache HIT for track {track_id}: key={cached['key']}, camelot={cached['camelot']}")
        freqblog_stats["cache_hits"] += 1
        return {"key": cached["key"], "camelot": cached["camelot"], "bpm": cached.get("bpm")}
    else:
        logger.info(f"Cache MISS for track {track_id}, checking FreqBlog")

    # Step 1: Try FreqBlog API first (fast metadata lookup)
    if track:
        logger.info(f"FreqBlog lookup: '{track.title}' by {track.artist.name if track.artist else 'Unknown'}")
        metadata = await lookup_track_metadata(track.title, track.artist.name if track.artist else "")
        if metadata:
            freqblog_stats["hits"] += 1
            logger.info(
                f"[FreqBlog HIT] Track {track_id}: BPM={metadata.get('bpm')}, Key={metadata.get('key')}, Camelot={metadata.get('camelot')}"
            )
            # Cache the result (including BPM)
            await db.set_key_cache(
                cache_key,
                metadata["key"],
                metadata["camelot"],
                metadata.get("key_confidence", 1.0),
                bpm=metadata.get("bpm")
            )
            return {"key": metadata["key"], "camelot": metadata["camelot"], "bpm": metadata.get("bpm")}
        else:
            freqblog_stats["misses"] += 1
            logger.info(f"[FreqBlog MISS] Track {track_id}: Not in catalog, falling back to local analysis")

    # Step 2: Fallback to local audio analysis (slower, requires download)
    tmp_path = None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            # Download the full preview stream (not just a chunk)
            async with client.stream("GET", stream_url) as resp:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                    tmp_path = f.name
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        result = await asyncio.to_thread(_dk, tmp_path)
        await db.set_key_cache(
            cache_key,
            result["key"],
            result["camelot"],
            result["confidence"],
            bpm=result.get("bpm")
        )

        logger.info(f"[Local Analysis] Track {track_id}: Key={result['key']}, Camelot={result['camelot']}, BPM={result.get('bpm')}")
        return {"key": result["key"], "camelot": result["camelot"], "bpm": result.get("bpm")}
    except Exception as e:
        freqblog_stats["errors"] += 1
        logger.warning(f"Preview key detection failed for track {track_id}: {e}")
        return {"key": None, "camelot": None}
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            _os.unlink(tmp_path)


# --- Queue Endpoints ---

class AddToQueueRequest(BaseModel):
    tidal_id: str
    item_type: str = "track"
    title: str
    artist: str = ""
    album: str = ""
    quality: str = None
    format: str = None


class BatchRemoveRequest(BaseModel):
    ids: list[int]


@app.post("/queue/add")
async def add_to_queue(item: AddToQueueRequest):
    quality = item.quality or config.default_quality
    fmt = item.format or config.default_format
    queue_item = await db.add_to_queue(
        tidal_id=item.tidal_id,
        item_type=item.item_type,
        title=item.title,
        artist=item.artist,
        album=item.album,
        quality=quality,
        format=fmt,
    )
    asyncio.create_task(_process_queue_if_idle())
    return queue_item


@app.get("/queue")
async def get_queue():
    return await db.get_queue()


@app.delete("/queue/completed")
async def clear_completed():
    removed = await db.remove_completed()
    return {"removed": removed}


@app.delete("/queue/batch")
async def remove_batch(body: BatchRemoveRequest):
    removed = await db.remove_batch(body.ids)
    return {"removed": removed}


@app.delete("/queue/all")
async def clear_all():
    global orchestrator
    if orchestrator and orchestrator._running:
        orchestrator._running = False
    removed = await db.remove_all()
    return {"removed": removed}


@app.delete("/queue/{item_id}")
async def remove_from_queue(item_id: int):
    await db.remove_from_queue(item_id)
    return {"ok": True}


async def _process_queue_if_idle():
    if orchestrator and not orchestrator._running:
        await orchestrator.process_queue()


# --- History Endpoints ---

@app.get("/history")
async def get_history(offset: int = 0, limit: int = 100):
    return await db.get_history(limit=limit, offset=offset)


class ReDownloadRequest(BaseModel):
    tidal_id: str
    item_type: str = "track"
    title: str
    artist: str = ""
    album: str = ""
    quality: str = None
    format: str = None


@app.post("/history/re-download")
async def re_download(item: ReDownloadRequest):
    quality = item.quality or config.default_quality
    fmt = item.format or config.default_format
    queue_item = await db.add_to_queue(
        tidal_id=item.tidal_id,
        item_type=item.item_type,
        title=item.title,
        artist=item.artist,
        album=item.album,
        quality=quality,
        format=fmt,
    )
    asyncio.create_task(_process_queue_if_idle())
    return queue_item


# --- Settings Endpoints ---

@app.get("/settings")
async def get_settings():
    return config.as_dict()


class UpdateSettingsRequest(BaseModel):
    default_quality: str = None
    default_format: str = None
    output_dir: str = None


@app.put("/settings")
async def update_settings(settings: UpdateSettingsRequest):
    if settings.default_quality:
        config.default_quality = settings.default_quality
    if settings.default_format:
        config.default_format = settings.default_format
    if settings.output_dir:
        config.output_dir = settings.output_dir
    config.save()
    return config.as_dict()


# --- Quality Probe Endpoint ---

@app.post("/quality/probe")
async def probe_quality():
    if not orchestrator or not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    preset = await orchestrator.probe_quality()
    if preset:
        cache = await db.get_quality_cache()
        await ws_manager.broadcast({
            "type": "quality",
            "id": "session",
            "preset": preset,
            "bitrate": cache["bitrate"] if cache else 0,
        })
        return {"preset": preset, "bitrate": cache["bitrate"] if cache else 0}
    raise HTTPException(status_code=500, detail="All quality presets failed probe")


@app.get("/quality/cache")
async def get_quality_cache():
    return await db.get_quality_cache()


# --- Key Detection Endpoints ---

from backend.key_detection import detect_key as _detect_key, file_hash, convert_to_camelot, get_compatible_keys


@app.get("/key/detect")
async def detect_file_key(path: str):
    h = file_hash(path)
    cached = await db.get_key_cache(h)
    if cached:
        return {"cached": True, **cached}

    result = _detect_key(path)
    await db.set_key_cache(h, result["key"], result["camelot"], result["confidence"])
    return {"cached": False, **result}


@app.get("/keys/compatible")
async def get_compatible_keys_route(key: str):
    """Return list of Camelot keys harmonically compatible with the given key."""
    if not key:
        raise HTTPException(status_code=400, detail="key parameter required")
    compatible = get_compatible_keys(key)
    if not compatible:
        raise HTTPException(status_code=400, detail="Invalid Camelot key format. Use format like '8A' or '12B'")
    return {"key": key, "compatible": compatible}


# --- Stats Endpoint ---

@app.get("/stats")
async def get_stats():
    stats = await db.get_all_stats()
    return stats


# --- FreqBlog Stats Endpoint ---

@app.get("/freqblog/stats")
async def get_freqblog_stats():
    """Return FreqBlog API usage stats (in-memory, reset on restart)."""
    total = freqblog_stats["hits"] + freqblog_stats["misses"] + freqblog_stats["cache_hits"]
    hit_rate = freqblog_stats["hits"] / max(freqblog_stats["hits"] + freqblog_stats["misses"], 1)
    return {
        **freqblog_stats,
        "total_requests": total,
        "hit_rate": round(hit_rate * 100, 1),
    }


# --- WebSocket Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
