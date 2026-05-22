import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

import tidalapi
from tidalapi import Quality

from backend.config import AppConfig
from backend.models import Database
from backend.quality import get_bitrate, bitrate_meets_threshold, QUALITY_PRESETS, QUALITY_PRESETS_ORDER
from backend.converter import convert_format
from backend.tagger import tag_file
from backend.search import get_album_tracks, get_playlist_tracks

logger = logging.getLogger(__name__)

QUALITY_ENUM_MAP = {
    "hi_res_lossless": Quality.hi_res_lossless,
    "high_lossless": Quality.high_lossless,
    "low_320k": Quality.low_320k,
    "low_96k": Quality.low_96k,
}

FORMAT_EXT_MAP = {
    "FLAC": ".flac",
    "MP3": ".mp3",
    "M4A": ".m4a",
}


def extract_track_metadata(track) -> dict:
    """Extract extended metadata from a tidalapi Track object."""
    return {
        "title": track.title or "Unknown",
        "artist": track.artist.name if track.artist else "Unknown",
        "artists": [a.name for a in track.artists] if track.artists else [],
        "album": track.album.name if track.album else "Unknown",
        "album_id": track.album.id if track.album else None,
        "track_num": track.track_num or 0,
        "duration": track.duration or 0,
        "isrc": track.isrc or None,
        "bpm": track.bpm or 0,
        "key": track.key_scale if hasattr(track, "key_scale") and track.key_scale else (track.key if hasattr(track, "key") and track.key else None),
        "explicit": track.explicit or False,
        "quality": track.audio_quality or "UNKNOWN",
        "cover_art_url": None,
    }


class DownloadOrchestrator:
    def __init__(self, db: Database, config: AppConfig, ws_manager=None):
        self.db = db
        self.config = config
        self.ws_manager = ws_manager
        self.session: Optional[tidalapi.Session] = None
        self._probed_quality: Optional[str] = None
        self._running = False

    def set_session(self, session: tidalapi.Session):
        self.session = session

    def _sanitize_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', ' -', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _build_filename(
        self,
        title: str,
        artist: str,
        ext: str,
        collection_name: str = None,
        track_num: int = None,
    ) -> str:
        safe_title = self._sanitize_filename(title)
        safe_artist = self._sanitize_filename(artist)

        if collection_name:
            safe_collection = self._sanitize_filename(collection_name)
            num_prefix = f"{track_num:02d} - " if track_num else ""
            return f"{safe_collection}/{num_prefix}{safe_artist} - {safe_title}{ext}"
        else:
            return f"{safe_artist} - {safe_title}{ext}"

    async def probe_quality(self) -> Optional[str]:
        """Try quality presets from highest to lowest, probe actual bitrate,
        and cache the first preset that delivers expected quality."""
        if not self.session:
            raise RuntimeError("Tidal session not initialized")

        for preset_name in QUALITY_PRESETS:
            logger.info(f"Probing quality preset: {preset_name}")
            quality_enum = QUALITY_ENUM_MAP[preset_name]

            try:
                test_track = self.session.get_tracks(limit=1)[0]
                self.session.audio_quality = quality_enum
                stream = test_track.get_stream()
                manifest = stream.get_stream_manifest()
                urls = manifest.get_urls()

                if not urls:
                    continue

                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(urls[0])
                    partial = resp.content[:512000]

                import tempfile
                with tempfile.NamedTemporaryFile(suffix=manifest.file_extension, delete=False) as f:
                    f.write(partial)
                    tmp_path = f.name

                try:
                    bitrate = get_bitrate(tmp_path)
                    if bitrate and bitrate_meets_threshold(preset_name, bitrate):
                        logger.info(f"Quality probe success: {preset_name} delivered {bitrate}kbps")
                        await self.db.set_quality_cache(preset_name, bitrate)
                        self._probed_quality = preset_name
                        return preset_name
                finally:
                    os.unlink(tmp_path)

            except Exception as e:
                logger.warning(f"Quality probe failed for {preset_name}: {e}")
                continue

        logger.error("All quality presets failed probe")
        return None

    async def download_track(self, queue_item: dict, on_progress=None):
        """Download a single track from the queue."""
        if not self.session:
            raise RuntimeError("Tidal session not initialized")

        tidal_id = queue_item["tidal_id"]
        target_format = queue_item["format"]
        quality_preset = queue_item["quality"]
        item_type = queue_item["item_type"]

        track = self.session.track(int(tidal_id))
        metadata = extract_track_metadata(track)

        quality_enum = QUALITY_ENUM_MAP.get(quality_preset, Quality.high_lossless)
        self.session.audio_quality = quality_enum
        stream = track.get_stream()
        manifest = stream.get_stream_manifest()
        urls = manifest.get_urls()

        if not urls:
            raise RuntimeError(f"No stream URL for track {tidal_id}")

        ext = FORMAT_EXT_MAP.get(target_format, ".flac")
        collection = queue_item.get("album") or None
        filename = self._build_filename(
            metadata["title"], metadata["artist"], ext, collection_name=collection,
        )
        output_dir = Path(os.path.expanduser(self.config.output_dir))
        output_path = output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = str(output_path) + ".tmp"
        import httpx
        total_size = 0

        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", urls[0]) as resp:
                total = int(resp.headers.get("content-length", 0))
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        total_size += len(chunk)
                        if on_progress and total > 0:
                            pct = (total_size / total) * 100
                            await on_progress(queue_item["id"], pct, total_size, total)

        actual_bitrate = get_bitrate(tmp_path) or 0

        final_path = str(output_path)
        if ext != manifest.file_extension:
            final_path = await asyncio.to_thread(
                convert_format, tmp_path, final_path, target_format.lower()
            )
        else:
            shutil.move(tmp_path, final_path)

        try:
            album = self.session.album(track.album.id)
            cover_url = album.image(1280)
            metadata["cover_art_url"] = cover_url
        except Exception:
            pass

        await asyncio.to_thread(tag_file, final_path, metadata, metadata.get("cover_art_url"))

        file_size = os.path.getsize(final_path)
        await self.db.add_to_history(
            tidal_id=tidal_id, item_type=item_type, title=metadata["title"],
            artist=metadata["artist"], album=metadata["album"],
            quality=quality_preset, format=target_format,
            file_path=final_path, file_size=file_size, actual_bitrate=actual_bitrate,
        )
        await self.db.remove_from_queue(queue_item["id"])

        logger.info(f"Downloaded: {final_path} ({actual_bitrate}kbps)")
        return final_path

    async def _expand_collection(self, item: dict):
        """Expand an album or playlist queue item into individual track items."""
        item_type = item["item_type"]
        tidal_id = item["tidal_id"]
        quality = item["quality"]
        fmt = item["format"]
        collection_name = item["title"]

        if item_type == "album":
            tracks = await asyncio.to_thread(get_album_tracks, self.session, int(tidal_id))
        elif item_type == "playlist":
            tracks = await asyncio.to_thread(get_playlist_tracks, self.session, tidal_id)
        else:
            return

        for track in tracks:
            await self.db.add_to_queue(
                tidal_id=str(track["id"]),
                item_type="track",
                title=track["title"],
                artist=track["artist"],
                album=collection_name,
                quality=quality,
                format=fmt,
            )

        await self.db.update_queue_status(item["id"], "complete")
        logger.info(f"Expanded {item_type} '{collection_name}' into {len(tracks)} tracks")

    async def process_queue(self):
        """Process all items in the download queue sequentially."""
        self._running = True
        try:
            while self._running:
                queue = await self.db.get_queue()
                queued = [item for item in queue if item["status"] == "queued"]
                if not queued:
                    break

                item = queued[0]

                if item["item_type"] in ("album", "playlist"):
                    await self.db.update_queue_status(item["id"], "downloading")
                    try:
                        await self._expand_collection(item)
                    except Exception as e:
                        logger.error(f"Failed to expand {item['item_type']} {item['id']}: {e}")
                        await self.db.update_queue_status(item["id"], "failed", error=str(e))
                    continue

                await self.db.update_queue_status(item["id"], "downloading")

                try:
                    async def on_progress(item_id, pct, bytes_done, bytes_total):
                        await self.db.update_queue_status(item_id, "downloading", progress=pct)
                        if self.ws_manager:
                            await self.ws_manager.broadcast({
                                "type": "progress",
                                "id": str(item_id),
                                "pct": round(pct, 1),
                                "bytes": bytes_done,
                                "total": bytes_total,
                            })

                    path = await self.download_track(item, on_progress=on_progress)
                    if self.ws_manager:
                        file_size = os.path.getsize(path)
                        await self.ws_manager.broadcast({
                            "type": "complete",
                            "id": str(item["id"]),
                            "path": path,
                            "size": file_size,
                        })
                except Exception as e:
                    logger.error(f"Download failed for item {item['id']}: {e}")
                    await self.db.update_queue_status(item["id"], "failed", error=str(e))
                    if self.ws_manager:
                        await self.ws_manager.broadcast({
                            "type": "error",
                            "id": str(item["id"]),
                            "reason": str(e),
                        })
        finally:
            self._running = False

    def stop(self):
        self._running = False
