"""Test FreqBlog API integration for BPM and key metadata."""
import asyncio
import os

import httpx
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
FREQBLOG_API_KEY = os.getenv("FREQBLOG_API_KEY")
FREQBLOG_BASE = "https://api.freqblog.com"


async def lookup_track(track: str, artist: str) -> dict:
    """Lookup track metadata from FreqBlog API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{FREQBLOG_BASE}/lookup",
            params={"track": track, "artist": artist},
            headers={
                "User-Agent": "TidalExtractor/0.1.0",
                "X-API-Key": FREQBLOG_API_KEY
            }
        )
        resp.raise_for_status()
        return resp.json()


async def test_freqblog_api():
    """Test FreqBlog API with 5 real tracks."""
    # 5 test tracks - mix of popular and niche
    test_tracks = [
        ("One More Time", "Daft Punk"),
        ("Midnight City", "MVMES"),
        ("Strobe", "deadmau5"),
        ("&ME", "Rampa"),
        ("What To Do", "&ME"),
    ]

    results = []
    for track, artist in test_tracks:
        try:
            print(f"🔍 Looking up: '{track}' by {artist}")
            data = await lookup_track(track, artist)

            # Check if track exists but has no audio features
            has_audio_features = data.get("bpm") is not None and data.get("key") is not None
            status = "✅" if has_audio_features else "⚠️ (in DB, not analyzed)"

            result = {
                "track": track,
                "artist": artist,
                "success": True,
                "has_audio_features": has_audio_features,
                "bpm": data.get("bpm"),
                "key": data.get("key"),
                "camelot": data.get("camelot"),
                "open_key": data.get("open_key"),
                "key_int": data.get("key_int"),
                "mode": data.get("mode"),
                "source": data.get("source"),
                "backfill_status": data.get("backfill_status"),
            }
            results.append(result)

            if has_audio_features:
                print(f"  ✅ BPM: {data.get('bpm')} | Key: {data.get('key')} | Camelot: {data.get('camelot')}")
                if data.get("open_key"):
                    print(f"     Open Key: {data.get('open_key')}")
            else:
                print(f"  ⚠️ Track found, but audio features not yet analyzed")
                print(f"     Source: {data.get('source')}, Backfill: {data.get('backfill_status')}")
        except httpx.HTTPError as e:
            print(f"  ❌ API Error: {e}")
            results.append({
                "track": track,
                "artist": artist,
                "success": False,
                "error": str(e),
            })
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            results.append({
                "track": track,
                "artist": artist,
                "success": False,
                "error": str(e),
            })

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    success_count = sum(1 for r in results if r.get("success") and r.get("has_audio_features"))
    in_db_count = sum(1 for r in results if r.get("success"))
    print(f"With audio features: {success_count}/{len(test_tracks)}")
    print(f"In database (any status): {in_db_count}/{len(test_tracks)}")
    print()

    for r in results:
        if r.get("has_audio_features"):
            print(f"✅ {r['track']} - {r['artist']}: {r.get('bpm')} BPM, {r.get('camelot')} ({r.get('key')})")
        else:
            print(f"⚠️ {r['track']} - {r['artist']}: in DB, awaiting analysis")

    return results


if __name__ == "__main__":
    asyncio.run(test_freqblog_api())