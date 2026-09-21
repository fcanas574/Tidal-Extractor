import asyncio
import dataclasses
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import AuthManager
from backend.config import AppConfig
from backend.models import Database
from backend.search import (
    search_tidal,
    get_album_details,
    get_playlist_tracks,
    resolve_url,
    score_results,
    enrich_tracks,
    get_artist_details,
)
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

# Search response cache. Entries are deliberately short-lived because Tidal
# search results can change while the app is open.
@dataclasses.dataclass
class _SearchCacheEntry:
    expires_at: float
    result: dict


_SEARCH_CACHE_TTL_SECONDS = 60.0
_search_results_cache: dict[str, _SearchCacheEntry] = {}


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


_SEARCH_TYPES = {"track", "artist", "album", "playlist"}
_SEARCH_RESULT_KEYS = ("tracks", "artists", "albums", "playlists")


def _normalized_search_value(value: Optional[str]) -> str:
    return " ".join((value or "").split()).casefold()


def _search_cache_key(
    query: str,
    result_type: str,
    offset: int,
    limit: int,
    bpm_min: Optional[int],
    bpm_max: Optional[int],
    key: Optional[str],
    key_compatible: bool,
    genre: Optional[str],
    artist_filter: Optional[str],
) -> str:
    return repr(
        (
            _normalized_search_value(query),
            result_type,
            offset,
            limit,
            bpm_min,
            bpm_max,
            _normalized_search_value(key),
            key_compatible,
            _normalized_search_value(genre),
            _normalized_search_value(artist_filter),
        )
    )


def _copy_search_response(result: dict) -> dict:
    """Return a response copy so callers cannot mutate cached list values."""
    return {
        **{key: list(result.get(key, [])) for key in _SEARCH_RESULT_KEYS},
        "offset": result["offset"],
        "limit": result["limit"],
        "has_more": result["has_more"],
    }


@app.get("/search")
async def search(
    q: str,
    type: str = "track",
    offset: int = 0,
    limit: int = 50,
    refresh: bool = False,
    bpm_min: Optional[int] = None,
    bpm_max: Optional[int] = None,
    key: Optional[str] = None,
    key_compatible: bool = False,
    genre: Optional[str] = None,
):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if type not in _SEARCH_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported search type: {type}")

    offset = max(0, offset)
    limit = max(1, min(limit, 300))
    query = " ".join(q.split())
    artist_filter = None

    # Handle "track - artist" format only for track searches.
    if " - " in query and type == "track":
        query, artist_filter = query.split(" - ", 1)

    # Prepend genre prefix if selected. Tidal supports genre: prefixes in the
    # normal search query, while the other filters are applied locally.
    search_query = query
    if genre:
        search_query = f"genre:{genre} {query}" if query else f"genre:{genre}"

    cache_key = _search_cache_key(
        search_query,
        type,
        offset,
        limit,
        bpm_min,
        bpm_max,
        key,
        key_compatible,
        genre,
        artist_filter,
    )
    now = time.monotonic()
    cached = _search_results_cache.get(cache_key)
    if not refresh and cached and cached.expires_at > now:
        return _copy_search_response(cached.result)
    if cached:
        _search_results_cache.pop(cache_key, None)

    raw = await asyncio.to_thread(
        search_tidal,
        auth_manager.session,
        search_query,
        [type],
        limit=300,
        offset=0,
        artist_filter=artist_filter if type == "track" else None,
    )
    all_results = {
        key: list(raw.get(key, []) or []) for key in _SEARCH_RESULT_KEYS
    }

    selected_results = all_results[f"{type}s"]
    if type == "track":
        if selected_results:
            scored = score_results(selected_results, query, artist_filter)
            selected_results = [track for track, _ in scored]

        if bpm_min is not None or bpm_max is not None or key:
            selected_results = filter_tracks_by_dj_metadata(
                selected_results, bpm_min, bpm_max, key, key_compatible
            )

    page_results = selected_results[offset:offset + limit]
    if type == "track" and page_results:
        page_results = await asyncio.to_thread(
            enrich_tracks, auth_manager.session, page_results, 5
        )

    response = {
        key: page_results if key == f"{type}s" else []
        for key in _SEARCH_RESULT_KEYS
    }
    response.update(
        {
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(page_results) < len(selected_results),
        }
    )
    _search_results_cache[cache_key] = _SearchCacheEntry(
        expires_at=time.monotonic() + _SEARCH_CACHE_TTL_SECONDS,
        result=response,
    )
    return _copy_search_response(response)


@app.get("/artist/{artist_id}")
async def artist_details(artist_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        details = await asyncio.to_thread(
            get_artist_details, auth_manager.session, artist_id
        )
        return {"tracks": [], "playlists": [], **details}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Artist not found: {exc}")


@app.get("/album/{album_id}/tracks")
async def album_tracks(album_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await asyncio.to_thread(get_album_details, auth_manager.session, album_id)


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
from backend.waveform_stream import analyze_stream


async def _preview_analyzer(
    stream_url: str, duration: float | None, track_id: int,
    on_snapshot=None,
) -> dict:
    """Background analyzer for preview metadata jobs (streaming pipeline).

    Uses ``analyze_stream`` to produce progressive waveform snapshots via
    ``on_snapshot``, then performs key detection via FreqBlog or local analysis
    on the single temp WAV that was already streamed (no second full-track
    network request).  Exceptions propagate to the ``PreviewJobManager``, which
    converts them into a ``failed`` snapshot.
    """
    result = await analyze_stream(
        stream_url, duration, width=600,
        on_snapshot=on_snapshot,
    )
    bands = result["bands"]
    stream_duration = result["duration"]
    temp_wav_path = result["temp_wav_path"]

    try:
        track = await asyncio.to_thread(auth_manager.session.track, track_id)
        key_data = await _detect_preview_key(
            stream_url, track_id, track,
            audio_path=temp_wav_path,
        )
    except Exception:
        logger.debug("Key detection failed for track %d", track_id, exc_info=True)
        key_data = {"key": None, "camelot": None, "bpm": None}
    finally:
        if temp_wav_path:
            try:
                os.unlink(temp_wav_path)
            except OSError:
                logger.debug("could not remove temp wav %s", temp_wav_path, exc_info=True)

    return {
        # Match the frontend WaveformData contract: { bands: {low,mid,high}, duration }.
        "waveform": {"bands": bands, "duration": stream_duration},
        "key": key_data.get("key"),
        "camelot": key_data.get("camelot"),
        "bpm": key_data.get("bpm"),
    }


preview_job_manager = PreviewJobManager(analyzer=_preview_analyzer)


def _resolve_preview_track(track_id: int):
    track = auth_manager.session.track(track_id)
    orig_quality = auth_manager.session.config.quality
    auth_manager.session.config.quality = "LOW"
    try:
        url = track.get_url()
    finally:
        auth_manager.session.config.quality = orig_quality
    return track, url


@app.get("/preview/{track_id}")
async def preview_track(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track, url = await asyncio.to_thread(_resolve_preview_track, track_id)
        logger.info(f"Preview track {track_id}: '{track.title}' by {track.artist.name if track.artist else 'Unknown'}")
        waveform = await asyncio.to_thread(get_waveform_cached, url)

        # Pass track object for FreqBlog metadata lookup
        key_data = await _detect_preview_key(url, track_id, track)

        return {"stream_url": url, "waveform": waveform, **key_data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


import dataclasses
from backend.preview_jobs import PreviewJobManager
from backend.waveform_stream import analyze_stream

preview_job_manager = PreviewJobManager()

_WAVEFORM_COLORS = {"low": "#0055e2", "mid": "#f2aa3c", "high": "#ffffff"}


async def _freqblog_lookup(title: str, artist: str):
    from backend.freqblog import lookup_track_metadata
    return await lookup_track_metadata(title, artist)


async def _detect_key_local(path: str):
    from backend.key_detection import detect_key
    return await asyncio.to_thread(detect_key, path)


async def _detect_preview_key_cached(track_id: int) -> dict:
    try:
        cached = await db.get_key_cache(f"preview_key_{track_id}")
    except Exception as e:
        logger.warning("key cache read failed for %s: %s", track_id, e)
        return {}
    if not cached:
        return {}
    return {"key": cached.get("key"), "camelot": cached.get("camelot"),
            "bpm": cached.get("bpm")}


async def _remove_temp_file(path: str | None) -> None:
    if path and os.path.exists(path):
        os.unlink(path)


async def preview_analyzer(stream_url: str, duration: float | None, track_id: int,
                           on_snapshot=None) -> dict:
    cached = await db.get_waveform_cache(str(track_id))
    bands = cached.get("bands") if isinstance(cached, dict) else None
    if (isinstance(bands, dict)
            and all(isinstance(bands.get(band), list) and bands[band]
                    for band in ("low", "mid", "high"))):
        key_data = await _detect_preview_key_cached(track_id)
        return {"waveform": {"bands": bands, "colors": _WAVEFORM_COLORS,
                             "duration": cached["duration"]}, **key_data}

    track = await asyncio.to_thread(auth_manager.session.track, track_id)
    title = getattr(track, "title", "") or ""
    artist = getattr(getattr(track, "artist", None), "name", "") or ""

    async def on_snap(snap):
        if on_snapshot:
            await on_snapshot(snap)
        preview_job_manager.publish_progress(track_id, {"waveform": snap})

    result = await analyze_stream(stream_url, duration, on_snapshot=on_snap)
    waveform = {"bands": result["bands"], "colors": _WAVEFORM_COLORS,
                "duration": result["duration"]}
    if not (isinstance(result["bands"], dict)
            and all(isinstance(result["bands"].get(band), list) and result["bands"][band]
                    for band in ("low", "mid", "high"))):
        raise RuntimeError("Waveform analysis produced no samples")
    preview_job_manager.publish_progress(track_id, {"waveform": waveform})

    key_payload = {}
    tmp_path = result.get("temp_wav_path")
    try:
        metadata = await _freqblog_lookup(title, artist)
        if metadata:
            key_payload = {"key": metadata["key"], "camelot": metadata["camelot"],
                           "bpm": metadata.get("bpm")}
        elif tmp_path:
            local = await _detect_key_local(tmp_path)
            key_payload = {"key": local.get("key"), "camelot": local.get("camelot"),
                           "bpm": local.get("bpm")}
        if key_payload.get("key"):
            await db.set_key_cache(f"preview_key_{track_id}", key_payload["key"],
                                   key_payload.get("camelot"), 1.0,
                                   bpm=key_payload.get("bpm"))
    except Exception as e:
        logger.warning("key detection failed for %s: %s", track_id, e)
    finally:
        # Each cleanup step is isolated so one failure can't leak the temp WAV
        # or mask another error (including any exception from the body above).
        result_bands = result.get("bands") if isinstance(result, dict) else None
        if (isinstance(result_bands, dict)
                and all(isinstance(result_bands.get(band), list) and result_bands[band]
                        for band in ("low", "mid", "high"))):
            with suppress(Exception):
                await db.set_waveform_cache(str(track_id), result_bands, result["duration"])
        with suppress(Exception):
            await _remove_temp_file(tmp_path)
    return {"waveform": waveform, **key_payload}


preview_job_manager.analyzer = preview_analyzer

@app.get("/preview/{track_id}/stream")
async def preview_stream(track_id: int):
    """Fast stream-only endpoint: resolve the LOW-quality url and return.

    Does NOT run waveform generation or key detection -- playback starts
    immediately.
    """
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track, url = await asyncio.to_thread(_resolve_preview_track, track_id)

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

    Track/url resolution failures are reported as 404 (mirroring the legacy
    route); a failure from `start_or_get` (e.g. scheduling error) propagates as
    a 500 rather than masquerading as "not found."
    """
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        snap = preview_job_manager.snapshot(track_id)
        if snap is None:
            # No job yet: resolve the stream URL once to kick one off. Subsequent
            # polls hit the snapshot above and never touch the session.
            track, url = await asyncio.to_thread(_resolve_preview_track, track_id)
            snap = preview_job_manager.start_or_get(track_id, url, getattr(track, "duration", None))
        return dataclasses.asdict(snap)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


async def _detect_preview_key(stream_url: str, track_id: int, track=None, audio_path: str | None = None) -> dict:
    """Detect key/camelot for preview track.

    Uses hybrid approach:
    1. Try FreqBlog API first (fast, ~100ms, no audio download)
    2. Fall back to local audio analysis on the provided ``audio_path`` (when
       called from the streaming pipeline) or on a freshly downloaded file
       (when called from the legacy combined preview endpoint).
    3. Cache results by track_id to avoid re-fetching.
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

    # Step 2: Fallback to local audio analysis.
    # Use the provided audio_path (from the streaming pipeline) or download.
    tmp_path = None
    try:
        if audio_path and _os.path.exists(audio_path):
            # Use the temp WAV already produced by analyze_stream — no download.
            logger.info(f"Using pre-downloaded audio at {audio_path}")
            tmp_path = audio_path
        else:
            import httpx
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                # Download the full preview stream
                async with client.stream("GET", stream_url) as resp:
                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                        tmp_path = f.name
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
            logger.info(f"Downloaded audio to {tmp_path}")

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
        # Only clean up if we downloaded ourselves — the streaming pipeline owns
        # its own temp WAV deletion.
        if tmp_path and audio_path is None and _os.path.exists(tmp_path):
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
    waveform_color: str = None


@app.put("/settings")
async def update_settings(settings: UpdateSettingsRequest):
    if settings.default_quality:
        config.default_quality = settings.default_quality
    if settings.default_format:
        config.default_format = settings.default_format
    if settings.output_dir:
        config.output_dir = settings.output_dir
    if settings.waveform_color is not None:
        try:
            config.update(waveform_color=settings.waveform_color)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
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
