import json
import logging
import time
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

from backend.search import format_track

logger = logging.getLogger(__name__)

BEATPORT_PUBLIC = "https://api.beatport.com/v4"
BEATPORT_CLIENT_ID = "ryZ8LuyQVPqbK2mBX2Hwt4qSMtnWuTYSqBPO92yQ"
BEATPORT_SESSION_FILE = Path("beatport-session.json")


class BeatportClient:
    def __init__(self):
        self._client: Optional[httpx.Client] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._genres_cache: Optional[list] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(15.0),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
        return self._client

    @property
    def authenticated(self) -> bool:
        return self._access_token is not None

    def _save_session(self):
        if self._access_token:
            data = {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._token_expires_at,
            }
            BEATPORT_SESSION_FILE.write_text(json.dumps(data))
            logger.info("Beatport session saved")

    def load_saved_session(self) -> bool:
        try:
            if not BEATPORT_SESSION_FILE.exists():
                return False
            data = json.loads(BEATPORT_SESSION_FILE.read_text())
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            self._token_expires_at = data.get("expires_at", 0)
            if self._access_token and self._token_expires_at > time.time():
                logger.info("Loaded saved Beatport session")
                return True
            elif self._access_token and self._refresh_token:
                # Token expired but we have a refresh token — try to refresh
                logger.info("Saved Beatport token expired, attempting refresh...")
                self._ensure_auth()
                return self._access_token is not None
        except Exception as e:
            logger.warning("Failed to load Beatport session: %s", e)
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = 0
        return False

    def logout(self):
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = 0
        self._genres_cache = None
        if BEATPORT_SESSION_FILE.exists():
            BEATPORT_SESSION_FILE.unlink()
        if self._client:
            self._client.close()
            self._client = None

    def login(self, username: str, password: str) -> bool:
        try:
            # Step 1: Get session cookie
            login_resp = self.client.post(
                f"{BEATPORT_PUBLIC}/auth/login/",
                json={"username": username, "password": password},
            )
            if login_resp.status_code != 200:
                logger.error("Beatport login step 1 failed: HTTP %s", login_resp.status_code)
                return False

            sessionid = login_resp.cookies.get("sessionid")
            if not sessionid:
                logger.error("Beatport login step 1 failed: no sessionid cookie in response")
                return False

            # Step 2: Exchange session cookie for authorization code
            auth_resp = self.client.get(
                f"{BEATPORT_PUBLIC}/auth/o/authorize/",
                params={
                    "client_id": BEATPORT_CLIENT_ID,
                    "response_type": "code",
                },
                cookies={"sessionid": sessionid},
                follow_redirects=False,
            )
            if auth_resp.status_code not in (301, 302, 303, 307, 308):
                logger.error(
                    "Beatport login step 2 failed: expected redirect, got HTTP %s",
                    auth_resp.status_code,
                )
                return False

            location = auth_resp.headers.get("Location", "")
            code_match = re.search(r"[?&]code=([^&]+)", location)
            if not code_match:
                logger.error("Beatport login step 2 failed: no code in redirect URL")
                return False
            code = code_match.group(1)

            # Step 3: Exchange code for tokens
            token_resp = self.client.post(
                f"{BEATPORT_PUBLIC}/auth/o/token/",
                data={
                    "client_id": BEATPORT_CLIENT_ID,
                    "grant_type": "authorization_code",
                    "code": code,
                },
            )
            if token_resp.status_code != 200:
                logger.error("Beatport login step 3 failed: HTTP %s", token_resp.status_code)
                return False

            data = token_resp.json()
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            if not self._access_token:
                logger.error("Beatport login step 3 failed: no access_token in response")
                return False
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in - 60
            self._save_session()
            logger.info("Beatport login successful")
            return True
        except Exception as e:
            logger.error("Beatport login error: %s", e)
            return False

    def _ensure_auth(self):
        if not self._access_token:
            return
        if time.time() > self._token_expires_at and self._refresh_token:
            try:
                resp = self.client.post(
                    f"{BEATPORT_PUBLIC}/auth/o/token/",
                    data={
                        "client_id": BEATPORT_CLIENT_ID,
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token")
                    self._refresh_token = data.get("refresh_token")
                    expires_in = data.get("expires_in", 3600)
                    self._token_expires_at = time.time() + expires_in - 60
                    self._save_session()
                    logger.info("Beatport token refreshed")
            except Exception as e:
                logger.error("Beatport token refresh error: %s", e)

    def _auth_headers(self) -> dict:
        self._ensure_auth()
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    def get_genres(self) -> list[dict]:
        if self._genres_cache:
            return self._genres_cache
        try:
            logger.info("Fetching Beatport genres...")
            resp = self.client.get(
                f"{BEATPORT_PUBLIC}/catalog/genres/",
                headers=self._auth_headers(),
            )
            if resp.status_code != 200:
                logger.error(
                    "Failed to fetch genres: HTTP %s, body: %s",
                    resp.status_code,
                    resp.text[:500] if resp.text else "(empty)",
                )
                return []
            results = resp.json().get("results", [])
            logger.info("Fetched %d Beatport genres", len(results))
            if results:
                logger.info("Sample genre keys: %s, first genre: %s",
                            list(results[0].keys()),
                            str(results[0])[:300])
            genres = [
                {"id": g["id"], "name": g["name"], "slug": g.get("slug", "")}
                for g in results
            ]
            self._genres_cache = genres
            return genres
        except Exception as e:
            logger.error("Error fetching genres: %s", e)
            return []

    def get_top_tracks(self, genre_id: int, genre_name: str = "", per_page: int = 10) -> list[dict]:
        """Get Top 10 tracks for a genre by searching for its Top 100 chart."""
        auth_headers = self._auth_headers()
        results = []

        try:
            # Strategy 1: Search for the genre's Top 100 chart
            if genre_name:
                search_query = f"{genre_name} top 100"
                logger.info("Searching charts for '%s'", search_query)
                search_resp = self.client.get(
                    f"{BEATPORT_PUBLIC}/catalog/search/",
                    params={"q": search_query, "type": "charts", "per_page": 3},
                    headers=auth_headers,
                )
                # Log raw response to see if type=charts works
                logger.info("Chart search HTTP %s", search_resp.status_code)
                chart_id = None
                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    logger.info("Chart search keys: %s, count=%s",
                               list(search_data.keys()),
                               search_data.get("count", "?"))
                    search_results = search_data.get("results", [])
                    if search_results:
                        logger.info("Chart search results: %s",
                                   [(r.get("id"), r.get("name")) for r in search_results[:5]])
                        # Pick chart with "Top 100" in name
                        for r in search_results:
                            if "top 100" in r.get("name", "").lower():
                                chart_id = r.get("id")
                                logger.info("Found Top-100 chart via search: %s (id=%s)", r.get("name"), chart_id)
                                break

                if chart_id:
                    resp = self.client.get(
                        f"{BEATPORT_PUBLIC}/catalog/charts/{chart_id}/tracks/",
                        params={"page": 1, "per_page": per_page},
                        headers=auth_headers,
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        logger.info("Chart tracks: %d results", len(results))

            # Strategy 2: /catalog/tracks/top/{genre_id}/ (IDs 1-100 only)
            if not results and genre_id <= 100:
                logger.info("Fallback /catalog/tracks/top/%s/", genre_id)
                resp = self.client.get(
                    f"{BEATPORT_PUBLIC}/catalog/tracks/top/{genre_id}/",
                    params={"per_page": per_page},
                    headers=auth_headers,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
        except Exception as e:
            logger.error("Error fetching top tracks: %s", e)
            return []

        # Format track objects
        tracks = []
        for item in results:
            t = item.get("track", item)  # unwrap chart entry if present
            artists = [a["name"] for a in t.get("artists", [])]
            remixers = [a["name"] for a in t.get("remixers", [])]
            release = t.get("release", {})
            cover_url = None
            if release and release.get("image"):
                cover_url = release["image"].get("uri", None)
            tracks.append({
                "id": t["id"],
                "name": t.get("name", ""),
                "mix_name": t.get("mix_name", "") or "",
                "artists": artists,
                "remixers": remixers,
                "bpm": t.get("bpm") or 0,
                "key": (t.get("key") or {}).get("name", "") if t.get("key") else "",
                "genre": (t.get("genre") or {}).get("name", "") if t.get("genre") else "",
                "length": t.get("length", ""),
                "length_ms": t.get("length_ms", 0),
                "isrc": t.get("isrc", "") or "",
                "cover_url": cover_url,
                "beatport_url": t.get("url", ""),
            })
        return tracks

    def get_stream_url(self, track_id: int) -> Optional[str]:
        """Try the /stream/ endpoint first, then fall back to track detail sample_url."""
        auth_headers = self._auth_headers()
        try:
            # Primary: /catalog/tracks/{id}/stream/ (returns {stream_url, sample_start_ms, sample_end_ms})
            resp = self.client.get(
                f"{BEATPORT_PUBLIC}/catalog/tracks/{track_id}/stream/",
                headers=auth_headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                url = data.get("stream_url")
                if url:
                    return url
                logger.info("Track %s /stream/ response keys: %s", track_id, list(data.keys()))

            # Fallback: track detail's sample_url field
            resp2 = self.client.get(
                f"{BEATPORT_PUBLIC}/catalog/tracks/{track_id}/",
                headers=auth_headers,
            )
            if resp2.status_code == 200:
                data = resp2.json()
                sample_url = data.get("sample_url")
                if sample_url:
                    return sample_url
                # Log all keys on first failure to help debug
                logger.info("Track %s detail keys: %s, sample_url present: %s",
                           track_id, list(data.keys()), "sample_url" in data)

            return None
        except Exception as e:
            logger.error("Error fetching stream URL: %s", e)
            return None

    def _normalize_mix(self, mix_name: str) -> str:
        if not mix_name:
            return ""
        n = mix_name.lower().strip()
        n = n.replace("(", "").replace(")", "")
        n = n.replace("extended mix", "extended")
        n = n.replace("original mix", "original")
        n = n.replace("radio edit", "radio")
        n = n.replace("radio version", "radio")
        n = n.replace("club mix", "club")
        n = n.replace("ext mix", "extended")
        n = n.replace("  ", " ").strip()
        return n

    def match_to_tidal(self, track: dict, tidal_session) -> dict:
        """4-layer matching pipeline. Returns {confidence, auto_matched, candidates}."""
        isrc = track.get("isrc", "")
        name = track.get("name", "")
        mix_name = track.get("mix_name", "")
        artist = track["artists"][0] if track.get("artists") else ""
        length_ms = track.get("length_ms", 0)
        remixers = track.get("remixers", [])

        all_candidates = []
        seen_ids = set()

        def add_candidate(tidal_track, score, match_details):
            tid = tidal_track.get("id")
            if tid in seen_ids:
                return
            seen_ids.add(tid)
            all_candidates.append({
                "score": score,
                "tidal_track": tidal_track,
                "match_details": match_details,
            })

        # Layer 1: ISRC exact match
        if isrc:
            try:
                isrc_results = tidal_session.search("track", query=isrc, limit=20)
                for t in isrc_results.get("tracks", []):
                    t_isrc = getattr(t, "isrc", None) or ""
                    if t_isrc.upper() == isrc.upper():
                        formatted = format_track(t)
                        add_candidate(formatted, 60, {
                            "isrc_match": True,
                            "mix_match": False,
                            "duration_match": "unknown",
                            "artist_match": True,
                        })
            except Exception:
                pass

        # Layer 2: Score ISRC candidates by mix name + duration
        for c in all_candidates[:]:
            if not c["match_details"]["isrc_match"]:
                continue
            if mix_name and self._normalize_mix(mix_name):
                tidal_title = c["tidal_track"]["title"].lower()
                if self._normalize_mix(mix_name) in tidal_title:
                    c["score"] += 30
                    c["match_details"]["mix_match"] = True
            if length_ms and c["tidal_track"]["duration"]:
                tidal_ms = c["tidal_track"]["duration"] * 1000
                diff = abs(length_ms - tidal_ms) / length_ms
                if diff <= 0.05:
                    c["score"] += 20
                    c["match_details"]["duration_match"] = "within_5pct"
                elif diff <= 0.10:
                    c["score"] += 10
                    c["match_details"]["duration_match"] = "within_10pct"
                else:
                    c["match_details"]["duration_match"] = "off"

        # Layer 3: Artist + Title + Mix search
        query = f"{artist} {name}"
        if mix_name:
            query += f" {mix_name}"
        try:
            title_results = tidal_session.search("track", query=query, limit=30)
            for t in title_results.get("tracks", []):
                formatted = format_track(t)
                score = 0
                details = {
                    "isrc_match": False,
                    "mix_match": False,
                    "duration_match": "unknown",
                    "artist_match": False,
                }
                t_artist = formatted["artist"].lower()
                if artist.lower() in t_artist or t_artist in artist.lower():
                    score += 40
                    details["artist_match"] = True
                for r in remixers:
                    if r.lower() in t_artist or r.lower() in formatted["title"].lower():
                        score += 10
                        break
                if mix_name and self._normalize_mix(mix_name):
                    t_title = formatted["title"].lower()
                    if self._normalize_mix(mix_name) in t_title:
                        score += 30
                        details["mix_match"] = True
                    elif any(w in t_title for w in self._normalize_mix(mix_name).split()):
                        score += 15
                        details["mix_match"] = "partial"
                if length_ms and formatted["duration"]:
                    t_ms = formatted["duration"] * 1000
                    diff = abs(length_ms - t_ms) / length_ms
                    if diff <= 0.05:
                        score += 20
                        details["duration_match"] = "within_5pct"
                    elif diff <= 0.10:
                        score += 10
                        details["duration_match"] = "within_10pct"
                    else:
                        details["duration_match"] = "off"
                add_candidate(formatted, score, details)
        except Exception:
            pass

        # Layer 4: Artist + Title (no mix filter)
        if not all_candidates and artist and name:
            try:
                broad_results = tidal_session.search("track", query=f"{artist} {name}", limit=30)
                for t in broad_results.get("tracks", []):
                    formatted = format_track(t)
                    score = 0
                    details = {
                        "isrc_match": False,
                        "mix_match": "unchecked",
                        "duration_match": "unknown",
                        "artist_match": formatted["artist"].lower() in artist.lower() or artist.lower() in formatted["artist"].lower(),
                    }
                    if details["artist_match"]:
                        score += 30
                    if length_ms and formatted["duration"]:
                        t_ms = formatted["duration"] * 1000
                        diff = abs(length_ms - t_ms) / length_ms
                        if diff <= 0.10:
                            score += 10
                            details["duration_match"] = "within_10pct"
                    add_candidate(formatted, score, details)
            except Exception:
                pass

        all_candidates.sort(key=lambda c: c["score"], reverse=True)
        top = all_candidates[:5] if all_candidates else []
        confidence = top[0]["score"] if top else 0

        return {
            "confidence": confidence,
            "auto_matched": confidence >= 95,
            "candidates": top,
        }

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


beatport_client = BeatportClient()
