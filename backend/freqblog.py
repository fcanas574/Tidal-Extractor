"""FreqBlog API integration for musical key and BPM metadata."""
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

FREQBLOG_BASE = "https://api.freqblog.com"
FREQBLOG_API_KEY = os.getenv("FREQBLOG_API_KEY")


async def lookup_track_metadata(track_title: str, artist: str) -> Optional[dict]:
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{FREQBLOG_BASE}/lookup",
                params={"track": track_title, "artist": artist},
                headers={
                    "User-Agent": "TidalExtractor/0.1.0",
                    "X-API-Key": FREQBLOG_API_KEY
                }
            )

            logger.debug(f"FreqBlog response status: {resp.status_code}")

            if resp.status_code == 404:
                logger.info(f"Track not found in FreqBlog: '{track_title}' by {artist}")
                return None

            resp.raise_for_status()
            data = resp.json()

            logger.debug(f"FreqBlog response: bpm={data.get('bpm')}, key={data.get('key')}")

            # Check if audio features are available
            if data.get("bpm") is None or data.get("key") is None:
                logger.info(
                    f"Track found but not yet analyzed: '{track_title}' by {artist} "
                    f"(source={data.get('source')}, backfill={data.get('backfill_status')})"
                )
                return None

            return {
                "bpm": data.get("bpm"),
                "bpm_confidence": data.get("bpm_confidence"),
                "key": data.get("key"),
                "key_int": data.get("key_int"),
                "mode": data.get("mode"),
                "camelot": data.get("camelot"),
                "open_key": data.get("open_key"),
                "key_confidence": data.get("key_confidence"),
                "source": data.get("source"),
            }

    except httpx.HTTPError as e:
        logger.warning(f"FreqBlog API error for '{track_title}' by {artist}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error looking up '{track_title}' by {artist}: {e}")
        return None