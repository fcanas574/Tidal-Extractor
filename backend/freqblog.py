"""FreqBlog API integration for musical key and BPM metadata."""
import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

FREQBLOG_BASE = "https://api.freqblog.com"
FREQBLOG_API_KEY = os.getenv("FREQBLOG_API_KEY")
FREQBLOG_BATCH_SIZE = 50
FREQBLOG_TIMEOUT_SECONDS = 10.0
_METADATA_FIELDS = (
    "bpm",
    "bpm_alt",
    "bpm_confidence",
    "key",
    "key_int",
    "mode",
    "camelot",
    "open_key",
    "key_confidence",
    "genre",
    "source",
)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "TidalExtractor/0.1.0",
        "X-API-Key": FREQBLOG_API_KEY or "",
    }


def normalize_track_metadata(data: Any) -> dict:
    """Keep the provider response small and stable at the application boundary."""
    if not isinstance(data, dict):
        return {}
    return {field: data.get(field) for field in _METADATA_FIELDS}


def _batch_result(status: str, data: Optional[dict] = None) -> dict:
    return {"status": status, "data": data}


def _request_payload(track: dict) -> dict:
    payload = {}
    if track.get("isrc"):
        payload["isrc"] = track["isrc"]
    if track.get("title"):
        payload["track"] = track["title"]
    if track.get("artist"):
        payload["artist"] = track["artist"]
    return payload


def _status_for_bulk_row(row: Any) -> dict:
    if not isinstance(row, dict):
        return _batch_result("unavailable")

    if row.get("found") and isinstance(row.get("result"), dict):
        return _batch_result("found", normalize_track_metadata(row["result"]))

    backfill_status = row.get("backfill_status")
    if backfill_status in {"queued", "processing"}:
        return _batch_result("queued")
    return _batch_result("miss")


async def lookup_track_metadata(
    track_title: str,
    artist: str,
    isrc: Optional[str] = None,
) -> Optional[dict]:
    """
    Lookup track metadata from FreqBlog API.

    Returns dict with BPM, key, and Camelot notation if found, None if not in catalog.
    """
    if not FREQBLOG_API_KEY:
        logger.warning("FREQBLOG_API_KEY not set, skipping metadata lookup")
        return None

    # Log the lookup attempt
    logger.debug(f"FreqBlog lookup: '{track_title}' by {artist}")

    try:
        params = {"isrc": isrc} if isrc else {"track": track_title, "artist": artist}
        async with httpx.AsyncClient(timeout=FREQBLOG_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{FREQBLOG_BASE}/lookup",
                params=params,
                headers=_headers(),
            )

            logger.debug(f"FreqBlog response status: {resp.status_code}")

            if resp.status_code != 200:
                logger.info(f"Track not found in FreqBlog: '{track_title}' by {artist}")
                return None

            resp.raise_for_status()
            data = resp.json()
            normalized = normalize_track_metadata(data)
            if not any(value is not None for value in normalized.values()):
                logger.info(f"Track found without usable metadata: '{track_title}' by {artist}")
                return None
            logger.debug(f"FreqBlog response: bpm={normalized.get('bpm')}, key={normalized.get('key')}")
            return normalized

    except httpx.HTTPError as e:
        logger.warning(f"FreqBlog API error for '{track_title}' by {artist}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error looking up '{track_title}' by {artist}: {e}")
        return None


async def lookup_tracks_metadata(tracks: list[dict]) -> dict[int, dict]:
    """Look up catalog track metadata in FreqBlog batches without raising provider errors."""
    if not tracks:
        return {}

    if not FREQBLOG_API_KEY:
        logger.warning("FREQBLOG_API_KEY not set, skipping batch metadata lookup")
        return {int(track["id"]): _batch_result("unavailable") for track in tracks}

    results = {int(track["id"]): _batch_result("unavailable") for track in tracks}
    try:
        async with httpx.AsyncClient(timeout=FREQBLOG_TIMEOUT_SECONDS) as client:
            for start in range(0, len(tracks), FREQBLOG_BATCH_SIZE):
                batch = tracks[start:start + FREQBLOG_BATCH_SIZE]
                payload = [_request_payload(track) for track in batch]
                try:
                    response = await client.post(
                        f"{FREQBLOG_BASE}/bulk",
                        json=payload,
                        headers=_headers(),
                    )
                except httpx.HTTPError as exc:
                    logger.warning("FreqBlog batch request failed: %s", exc)
                    for track in batch:
                        results[int(track["id"])] = _batch_result("unavailable")
                    continue

                if response.status_code == 429:
                    status = "rate_limited"
                    for track in batch:
                        results[int(track["id"])] = _batch_result(status)
                    continue
                if response.status_code == 404:
                    for track in batch:
                        results[int(track["id"])] = _batch_result("miss")
                    continue
                if response.status_code != 200:
                    for track in batch:
                        results[int(track["id"])] = _batch_result("unavailable")
                    continue

                try:
                    body = response.json()
                except (TypeError, ValueError):
                    body = None
                rows = body.get("results") if isinstance(body, dict) else None
                if not isinstance(rows, list):
                    for track in batch:
                        results[int(track["id"])] = _batch_result("unavailable")
                    continue

                for index, track in enumerate(batch):
                    row = rows[index] if index < len(rows) else None
                    results[int(track["id"])] = _status_for_bulk_row(row)
    except httpx.HTTPError as exc:
        logger.warning("FreqBlog batch client failed: %s", exc)
        for track in tracks:
            results[int(track["id"])] = _batch_result("unavailable")
    except Exception as exc:
        logger.warning("Unexpected FreqBlog batch error: %s", exc)
        for track in tracks:
            results[int(track["id"])] = _batch_result("unavailable")

    return results
