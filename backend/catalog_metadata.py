"""Cache-backed, TIDAL-first catalog metadata enrichment."""

from __future__ import annotations

import time
from typing import Iterable

from backend.freqblog import lookup_tracks_metadata
from backend.models import Database

DEFAULT_REQUIRED_FIELDS = {"bpm", "key", "genre"}
FOUND_TTL_SECONDS = 30 * 24 * 60 * 60
MISS_TTL_SECONDS = 24 * 60 * 60
TEMPORARY_TTL_SECONDS = 5 * 60


def _has_value(value) -> bool:
    return value is not None and value != ""


def _field_present(track: dict, field: str) -> bool:
    if field == "key":
        # A direct Camelot value is a valid key result even when TIDAL did not
        # provide a pitch/scale pair that can be converted locally.
        return _has_value(track.get("key")) or _has_value(track.get("camelot"))
    return _has_value(track.get(field))


def _initialize_sources(track: dict) -> dict:
    result = dict(track)
    result["bpm_source"] = "tidal" if _has_value(result.get("bpm")) else None
    result["key_source"] = "tidal" if _has_value(result.get("key")) else None
    result.setdefault("genre_source", None)
    return result


def merge_catalog_metadata(track: dict, lookup: dict | None) -> dict:
    """Merge one provider/cache result without replacing non-null TIDAL BPM/key."""
    result = _initialize_sources(track)
    if not lookup:
        return result

    data = lookup.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    provider_bpm = data.get("bpm")
    if not _has_value(result.get("bpm")) and _has_value(provider_bpm):
        result["bpm"] = provider_bpm
        result["bpm_source"] = "freqblog"

    provider_key = data.get("key")
    if _has_value(provider_key):
        result["key_label"] = provider_key
        if not _has_value(result.get("key")):
            result["key"] = provider_key
            result["key_source"] = "freqblog"
    elif _has_value(data.get("camelot")) and not _has_value(result.get("key")):
        result["key_source"] = "freqblog"

    if not _has_value(result.get("genre")) and _has_value(data.get("genre")):
        result["genre"] = data["genre"]
        result["genre_source"] = "freqblog"

    for field in (
        "bpm_alt",
        "bpm_confidence",
        "key_int",
        "mode",
        "key_confidence",
        "camelot",
        "open_key",
        "source",
    ):
        if _has_value(data.get(field)):
            result[field] = data[field]

    return result


def _metadata_status(track: dict, lookup: dict | None, required_fields: set[str]) -> str:
    provider_status = lookup.get("status") if lookup else None
    if provider_status in {"queued", "rate_limited", "unavailable"}:
        return provider_status
    if provider_status == "miss":
        return "partial"
    if all(_field_present(track, field) for field in required_fields):
        return "complete"
    return "partial"


def _cache_expiry(status: str, checked_at: float) -> float:
    if status == "found":
        return checked_at + FOUND_TTL_SECONDS
    if status == "miss":
        return checked_at + MISS_TTL_SECONDS
    return checked_at + TEMPORARY_TTL_SECONDS


async def enrich_catalog_tracks(
    db: Database,
    tracks: Iterable[dict],
    required_fields: set[str] | None = None,
    lookup_limit: int | None = None,
) -> list[dict]:
    """Apply cached/provider metadata while preserving the input order and length."""
    required = set(DEFAULT_REQUIRED_FIELDS if required_fields is None else required_fields)
    enriched = [_initialize_sources(track) for track in tracks]
    if not enriched:
        return []

    tidal_ids = [int(track["id"]) for track in enriched]
    cached = await db.get_catalog_metadata(tidal_ids)
    lookups: dict[int, dict] = {}
    provider_candidates = []

    for track in enriched:
        tidal_id = int(track["id"])
        cache_entry = cached.get(tidal_id)
        if cache_entry is not None:
            lookups[tidal_id] = {
                "status": cache_entry.get("status"),
                "data": cache_entry.get("data") or {},
            }
        elif not all(_field_present(track, field) for field in required):
            provider_candidates.append(track)

    if lookup_limit is not None:
        provider_candidates = provider_candidates[:max(0, lookup_limit)]

    if provider_candidates:
        provider_results = await lookup_tracks_metadata(provider_candidates)
        cache_entries = []
        checked_at = time.time()
        for track in provider_candidates:
            tidal_id = int(track["id"])
            lookup = provider_results.get(tidal_id) or provider_results.get(str(tidal_id))
            if not lookup:
                lookup = {"status": "unavailable", "data": None}
            lookups[tidal_id] = lookup
            status = lookup.get("status", "unavailable")
            cache_entries.append({
                "tidal_id": tidal_id,
                "isrc": track.get("isrc"),
                "data": lookup.get("data") or {},
                "status": status,
                "checked_at": checked_at,
                "expires_at": _cache_expiry(status, checked_at),
            })
        await db.set_catalog_metadata(cache_entries)

    result = []
    for track in enriched:
        tidal_id = int(track["id"])
        lookup = lookups.get(tidal_id)
        merged = merge_catalog_metadata(track, lookup)
        merged["metadata_status"] = _metadata_status(merged, lookup, required)
        result.append(merged)
    return result
