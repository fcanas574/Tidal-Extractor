import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import AuthManager
from backend.config import AppConfig
from backend.models import Database
from backend.search import search_tidal, get_album_tracks, get_playlist_tracks, resolve_url
from backend.downloader import DownloadOrchestrator
from backend.ws import WebSocketManager

logger = logging.getLogger(__name__)

config = AppConfig()
db = Database()
auth_manager = AuthManager()
ws_manager = WebSocketManager()
orchestrator: DownloadOrchestrator = None


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

@app.get("/search")
async def search(q: str, type: str = "track"):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    models = [type] if type in ("track", "album", "playlist") else ["track", "album", "playlist"]
    artist_filter = None
    if " - " in q and type == "track":
        parts = q.split(" - ", 1)
        q = parts[0]
        artist_filter = parts[1]
    results = await asyncio.to_thread(search_tidal, auth_manager.session, q, models, artist_filter=artist_filter)
    return results


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

@app.get("/preview/{track_id}")
async def preview_track(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        track = auth_manager.session.track(track_id)
        # Use lowest quality for previews to save bandwidth
        orig_quality = auth_manager.session.config.quality
        auth_manager.session.config.quality = "LOW"
        try:
            url = track.get_url()
        finally:
            auth_manager.session.config.quality = orig_quality
        waveform = await asyncio.to_thread(get_waveform_cached, url)
        return {"stream_url": url, "waveform": waveform}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Preview unavailable: {e}")


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


@app.delete("/queue/{item_id}")
async def remove_from_queue(item_id: int):
    await db.remove_from_queue(item_id)
    return {"ok": True}


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


# --- Key Detection Endpoint ---

from backend.key_detection import detect_key as _detect_key, file_hash

@app.get("/key/detect")
async def detect_file_key(path: str):
    h = file_hash(path)
    cached = await db.get_key_cache(h)
    if cached:
        return {"cached": True, **cached}

    result = _detect_key(path)
    await db.set_key_cache(h, result["key"], result["camelot"], result["confidence"])
    return {"cached": False, **result}


# --- Stats Endpoint ---

@app.get("/stats")
async def get_stats():
    stats = await db.get_all_stats()
    return stats


# --- WebSocket Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
