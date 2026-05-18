import aiosqlite
from typing import Optional


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
            CREATE TABLE IF NOT EXISTS quality_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                preset TEXT NOT NULL,
                bitrate INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def add_to_queue(self, tidal_id, item_type, title, artist, album, quality, format):
        cursor = await self._conn.execute(
            """INSERT INTO queue (tidal_id, item_type, title, artist, album, quality, format)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tidal_id, item_type, title, artist, album, quality, format),
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

    async def update_queue_status(self, item_id: int, status: str, error: str = None, progress: float = None):
        parts = ["status = ?"]
        values = [status]
        if error is not None:
            parts.append("error = ?")
            values.append(error)
        if progress is not None:
            parts.append("progress = ?")
            values.append(progress)
        values.append(item_id)
        await self._conn.execute(
            f"UPDATE queue SET {', '.join(parts)} WHERE id = ?", values
        )
        await self._conn.commit()

    async def remove_from_queue(self, item_id: int):
        await self._conn.execute("DELETE FROM queue WHERE id = ?", (item_id,))
        await self._conn.commit()

    async def add_to_history(self, tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate):
        await self._conn.execute(
            """INSERT INTO history (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tidal_id, item_type, title, artist, album, quality, format, file_path, file_size, actual_bitrate),
        )
        await self._conn.commit()

    async def get_history(self, limit: int = 100):
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM history ORDER BY downloaded_at DESC LIMIT ?", (limit,)
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
