import aiosqlite
import json
import math
import re
import time
from datetime import datetime, timezone
from typing import Optional

from backend.analysis.types import (
    HybridAnalysisResult,
    deserialize_result,
    serialize_result,
)


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return value.lower()


def _utc_timestamp(value: datetime, field_name: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime")
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be a timezone-aware UTC datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _require_duration(value: float) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_seconds must be finite and non-negative") from exc
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("duration_seconds must be finite and non-negative")
    return duration


class Database:
    def __init__(self, db_path: str = "tidal_extractor.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tidal_id TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'track',
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                quality TEXT NOT NULL DEFAULT 'high_lossless',
                format TEXT NOT NULL DEFAULT 'FLAC',
                status TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0.0,
                error TEXT,
                from_collection INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tidal_id TEXT NOT NULL,
                item_type TEXT NOT NULL DEFAULT 'track',
                title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                quality TEXT NOT NULL,
                format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                actual_bitrate INTEGER NOT NULL DEFAULT 0,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS device_stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS quality_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                preset TEXT NOT NULL,
                bitrate INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS key_cache (
                file_hash TEXT PRIMARY KEY,
                key TEXT,
                camelot TEXT,
                confidence REAL,
                bpm REAL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS waveform_cache (
                tidal_id TEXT PRIMARY KEY,
                bands_json TEXT NOT NULL,
                duration REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS catalog_metadata_cache (
                tidal_id TEXT PRIMARY KEY,
                isrc TEXT,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_result_cache (
                audio_fingerprint TEXT NOT NULL,
                engine_key TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (audio_fingerprint, engine_key)
            );
            CREATE TABLE IF NOT EXISTS preview_analysis_aliases (
                track_id INTEGER NOT NULL,
                profile TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                decoder_version TEXT NOT NULL,
                engine_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                PRIMARY KEY (
                    track_id, profile, duration_seconds, decoder_version, engine_key
                )
            );
        """)
        await self._conn.commit()
        queue_columns = await self._conn.execute_fetchall("PRAGMA table_info(queue)")
        queue_column_names = {column["name"] for column in queue_columns}
        if "from_collection" not in queue_column_names:
            await self._conn.execute(
                "ALTER TABLE queue ADD COLUMN from_collection INTEGER NOT NULL DEFAULT 0"
            )
        if "revision" not in queue_column_names:
            await self._conn.execute(
                "ALTER TABLE queue ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"
            )

        key_cache_columns = await self._conn.execute_fetchall("PRAGMA table_info(key_cache)")
        if "bpm" not in {column["name"] for column in key_cache_columns}:
            await self._conn.execute("ALTER TABLE key_cache ADD COLUMN bpm REAL")
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def get_analysis_result(
        self, fingerprint: str, engine_key: str
    ) -> HybridAnalysisResult | None:
        fingerprint = _require_sha256(fingerprint, "fingerprint")
        engine_key = _require_sha256(engine_key, "engine_key")
        rows = await self._conn.execute_fetchall(
            """SELECT result_json FROM analysis_result_cache
               WHERE audio_fingerprint = ? AND engine_key = ?""",
            (fingerprint, engine_key),
        )
        if not rows:
            return None
        try:
            result = deserialize_result(json.loads(rows[0]["result_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if result.audio_fingerprint.lower() != fingerprint:
            return None
        return result

    async def set_analysis_result(
        self, result: HybridAnalysisResult, engine_key: str
    ) -> None:
        fingerprint = _require_sha256(result.audio_fingerprint, "audio_fingerprint")
        engine_key = _require_sha256(engine_key, "engine_key")
        _require_sha256(result.model_sha256, "model_sha256")
        _require_sha256(result.settings_sha256, "settings_sha256")
        result_json = json.dumps(
            serialize_result(result),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        await self._conn.execute(
            """INSERT INTO analysis_result_cache
                   (audio_fingerprint, engine_key, schema_version, result_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(audio_fingerprint, engine_key) DO UPDATE SET
                   schema_version = excluded.schema_version,
                   result_json = excluded.result_json,
                   created_at = CURRENT_TIMESTAMP""",
            (fingerprint, engine_key, result.schema_version, result_json),
        )
        await self._conn.commit()

    async def get_preview_analysis_alias(
        self,
        track_id: int,
        profile: str,
        duration_seconds: float,
        decoder_version: str,
        engine_key: str,
        now_utc: datetime,
    ) -> str | None:
        duration_seconds = _require_duration(duration_seconds)
        engine_key = _require_sha256(engine_key, "engine_key")
        now = _utc_timestamp(now_utc, "now_utc")
        rows = await self._conn.execute_fetchall(
            """SELECT fingerprint FROM preview_analysis_aliases
               WHERE track_id = ? AND profile = ? AND duration_seconds = ?
                 AND decoder_version = ? AND engine_key = ? AND expires_at_utc > ?""",
            (track_id, profile, duration_seconds, decoder_version, engine_key, now),
        )
        if not rows:
            return None
        try:
            return _require_sha256(rows[0]["fingerprint"], "fingerprint")
        except ValueError:
            return None

    async def set_preview_analysis_alias(
        self,
        track_id: int,
        profile: str,
        duration_seconds: float,
        decoder_version: str,
        engine_key: str,
        fingerprint: str,
        expires_at_utc: datetime,
    ) -> None:
        duration_seconds = _require_duration(duration_seconds)
        engine_key = _require_sha256(engine_key, "engine_key")
        fingerprint = _require_sha256(fingerprint, "fingerprint")
        expires_at = _utc_timestamp(expires_at_utc, "expires_at_utc")
        await self._conn.execute(
            """INSERT INTO preview_analysis_aliases
                   (track_id, profile, duration_seconds, decoder_version,
                    engine_key, fingerprint, expires_at_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(track_id, profile, duration_seconds, decoder_version, engine_key)
               DO UPDATE SET fingerprint = excluded.fingerprint,
                             expires_at_utc = excluded.expires_at_utc""",
            (
                track_id,
                profile,
                duration_seconds,
                decoder_version,
                engine_key,
                fingerprint,
                expires_at,
            ),
        )
        await self._conn.commit()

    async def add_to_queue(self, tidal_id, item_type, title, artist, album, quality, format, from_collection: bool = False):
        cursor = await self._conn.execute(
            """INSERT INTO queue
               (tidal_id, item_type, title, artist, album, quality, format, from_collection, revision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (tidal_id, item_type, title, artist, album, quality, format, int(from_collection)),
        )
        await self._conn.commit()
        row = await self._conn.execute_fetchall(
            "SELECT * FROM queue WHERE id = ?", (cursor.lastrowid,)
        )
        return dict(row[0])

    async def get_queue(self):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM queue ORDER BY created_at ASC"
        )
        return [dict(r) for r in rows]

    async def get_queue_item(self, item_id: int):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM queue WHERE id = ?", (item_id,)
        )
        return dict(rows[0]) if rows else None

    async def update_queue_status(self, item_id: int, status: str, error: str = None, progress: float = None):
        parts = ["status = ?"]
        values = [status]
        if error is not None:
            parts.append("error = ?")
            values.append(error)
        if progress is not None:
            parts.append("progress = ?")
            values.append(progress)
        parts.append("revision = revision + 1")
        values.append(item_id)
        await self._conn.execute(
            f"UPDATE queue SET {', '.join(parts)} WHERE id = ?", values
        )
        await self._conn.commit()
        return await self.get_queue_item(item_id)

    async def remove_from_queue(self, item_id: int):
        await self._conn.execute("DELETE FROM queue WHERE id = ?", (item_id,))
        await self._conn.commit()

    async def remove_completed(self) -> int:
        cursor = await self._conn.execute("DELETE FROM queue WHERE status = 'complete'")
        await self._conn.commit()
        return cursor.rowcount

    async def remove_batch(self, ids: list[int]) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._conn.execute(
            f"DELETE FROM queue WHERE id IN ({placeholders})", ids
        )
        await self._conn.commit()
        return cursor.rowcount

    async def remove_all(self) -> int:
        cursor = await self._conn.execute("DELETE FROM queue")
        await self._conn.commit()
        return cursor.rowcount

    async def add_to_history(self, tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate):
        await self._conn.execute(
            """INSERT INTO history (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate),
        )
        await self._conn.commit()

    async def get_history(self, limit: int = 100, offset: int = 0):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM history ORDER BY downloaded_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in rows]

    async def set_quality_cache(self, preset: str, bitrate: int):
        await self._conn.execute("DELETE FROM quality_cache")
        await self._conn.execute(
            "INSERT INTO quality_cache (id, preset, bitrate) VALUES (1, ?, ?)",
            (preset, bitrate),
        )
        await self._conn.commit()

    async def get_quality_cache(self):
        rows = await self._conn.execute_fetchall("SELECT * FROM quality_cache WHERE id = 1")
        if not rows:
            return None
        return {"preset": rows[0]["preset"], "bitrate": rows[0]["bitrate"]}

    async def clear_quality_cache(self):
        await self._conn.execute("DELETE FROM quality_cache")
        await self._conn.commit()

    async def get_catalog_metadata(self, tidal_ids, now=None):
        """Return non-expired catalog metadata keyed by integer TIDAL ID."""
        if not tidal_ids:
            return {}

        lookup_ids = [int(tidal_id) for tidal_id in tidal_ids]
        placeholders = ",".join("?" for _ in lookup_ids)
        current_time = time.time() if now is None else float(now)
        rows = await self._conn.execute_fetchall(
            f"""SELECT tidal_id, isrc, metadata_json, status, checked_at, expires_at
                FROM catalog_metadata_cache
                WHERE tidal_id IN ({placeholders}) AND expires_at > ?""",
            [str(tidal_id) for tidal_id in lookup_ids] + [current_time],
        )

        metadata = {}
        for row in rows:
            try:
                data = json.loads(row["metadata_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            metadata[int(row["tidal_id"])] = {
                "isrc": row["isrc"],
                "data": data,
                "status": row["status"],
                "checked_at": row["checked_at"],
                "expires_at": row["expires_at"],
            }
        return metadata

    async def set_catalog_metadata(self, entries):
        """Upsert a batch of normalized catalog metadata records in one transaction."""
        if not entries:
            return

        rows = [
            (
                str(int(entry["tidal_id"])),
                entry.get("isrc"),
                json.dumps(entry.get("data") or {}),
                entry.get("status", "unavailable"),
                float(entry["checked_at"]),
                float(entry["expires_at"]),
            )
            for entry in entries
        ]
        await self._conn.executemany(
            """INSERT INTO catalog_metadata_cache
                   (tidal_id, isrc, metadata_json, status, checked_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tidal_id) DO UPDATE SET
                    isrc = excluded.isrc,
                    metadata_json = excluded.metadata_json,
                    status = excluded.status,
                    checked_at = excluded.checked_at,
                    expires_at = excluded.expires_at""",
            rows,
        )
        await self._conn.commit()

    async def increment_stat(self, key: str, amount: int = 1):
        await self._conn.execute(
            """INSERT INTO device_stats (key, value)
               VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = value + excluded.value,
                   updated_at = CURRENT_TIMESTAMP""",
            (key, amount),
        )
        await self._conn.commit()

    async def get_stat(self, key: str) -> int:
        row = await self._conn.execute_fetchall(
            "SELECT value FROM device_stats WHERE key = ?", (key,)
        )
        return row[0]["value"] if row else 0

    async def get_all_stats(self) -> dict[str, int]:
        rows = await self._conn.execute_fetchall("SELECT key, value FROM device_stats")
        return {r["key"]: r["value"] for r in rows}

    async def get_key_cache(self, file_hash: str):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM key_cache WHERE file_hash = ?", (file_hash,)
        )
        return dict(rows[0]) if rows else None

    async def set_key_cache(self, file_hash: str, key: str, camelot: str, confidence: float, bpm: float | None = None):
        await self._conn.execute(
            """INSERT INTO key_cache (file_hash, key, camelot, confidence, bpm)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(file_hash) DO UPDATE SET
                   key = excluded.key,
                   camelot = excluded.camelot,
                   confidence = excluded.confidence,
                   bpm = excluded.bpm,
                   detected_at = CURRENT_TIMESTAMP""",
            (file_hash, key, camelot, confidence, bpm),
        )
        await self._conn.commit()

    async def get_waveform_cache(self, tidal_id: str):
        rows = await self._conn.execute_fetchall(
            "SELECT bands_json, duration FROM waveform_cache WHERE tidal_id = ?", (tidal_id,))
        if not rows:
            return None
        return {"bands": json.loads(rows[0]["bands_json"]), "duration": rows[0]["duration"]}

    async def set_waveform_cache(self, tidal_id: str, bands: dict, duration: float):
        await self._conn.execute(
            """INSERT INTO waveform_cache (tidal_id, bands_json, duration)
               VALUES (?, ?, ?)
               ON CONFLICT(tidal_id) DO UPDATE SET
                   bands_json = excluded.bands_json,
                   duration = excluded.duration,
                   created_at = CURRENT_TIMESTAMP""",
            (tidal_id, json.dumps(bands), duration),
        )
        await self._conn.commit()
