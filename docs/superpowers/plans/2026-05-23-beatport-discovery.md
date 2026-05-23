# Beatport Discovery Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Beatport" tab showing Top 10 tracks per genre with preview playback and precise Tidal matching with user confirmation.

**Architecture:** New `backend/beatport.py` module handles Beatport API auth, genre/track/stream fetching, and the 4-layer Tidal matching pipeline. Four new REST endpoints in `main.py` expose this to the frontend. New `BeatportView.tsx` component with genre selector, track cards, preview audio, and a confirmation dialog for medium-confidence matches.

**Tech Stack:** Python 3.12+ (httpx for API calls), FastAPI, React 18 + TypeScript + Tailwind CSS

---

### Task 1: Beatport API client — auth and genres

**Files:**
- Create: `backend/beatport.py`

- [ ] **Step 1: Create the Beatport client module with auth and genre listing**

```python
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BEATPORT_INTERNAL = "https://api-internal.beatportprod.com/v4"
BEATPORT_PUBLIC = "https://api.beatport.com/v4"


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
            self._client = httpx.Client(timeout=httpx.Timeout(15.0))
        return self._client

    @property
    def authenticated(self) -> bool:
        return self._access_token is not None

    def login(self, username: str, password: str) -> bool:
        try:
            resp = self.client.post(
                f"{BEATPORT_PUBLIC}/auth/login/",
                json={"username": username, "password": password},
            )
            if resp.status_code != 200:
                logger.error("Beatport login failed: %s", resp.status_code)
                return False
            data = resp.json()
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in - 60
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
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data["access_token"]
                    self._refresh_token = data["refresh_token"]
                    self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
            except Exception:
                pass

    def _auth_headers(self) -> dict:
        self._ensure_auth()
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    def get_genres(self) -> list[dict]:
        if self._genres_cache:
            return self._genres_cache

        try:
            resp = self.client.get(f"{BEATPORT_INTERNAL}/catalog/genres/")
            if resp.status_code != 200:
                logger.error("Failed to fetch genres: %s", resp.status_code)
                return []
            results = resp.json().get("results", [])
            genres = [
                {"id": g["id"], "name": g["name"], "slug": g.get("slug", "")}
                for g in results
            ]
            self._genres_cache = genres
            return genres
        except Exception as e:
            logger.error("Error fetching genres: %s", e)
            return []

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


beatport_client = BeatportClient()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "from backend.beatport import BeatportClient, beatport_client; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/beatport.py
git commit -m "feat: Beatport API client with auth and genre listing"
```

---

### Task 2: Beatport API client — top tracks and stream URL

**Files:**
- Modify: `backend/beatport.py` (append to class)

- [ ] **Step 1: Add get_top_tracks and get_stream_url methods**

Add these methods inside the `BeatportClient` class, after `get_genres()`:

```python
    def get_top_tracks(self, genre_id: int, per_page: int = 10) -> list[dict]:
        try:
            resp = self.client.get(
                f"{BEATPORT_INTERNAL}/catalog/genres/{genre_id}/top-10-tracks/",
                params={"per_page": per_page},
                headers=self._auth_headers(),
            )
            if resp.status_code != 200:
                logger.error("Failed to fetch top tracks for genre %s: %s", genre_id, resp.status_code)
                return []
            results = resp.json().get("results", [])
            tracks = []
            for t in results:
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
        except Exception as e:
            logger.error("Error fetching top tracks: %s", e)
            return []

    def get_stream_url(self, track_id: int) -> Optional[str]:
        try:
            resp = self.client.get(
                f"{BEATPORT_PUBLIC}/catalog/tracks/{track_id}/",
                params={"fields": "stream"},
                headers=self._auth_headers(),
            )
            if resp.status_code != 200:
                logger.error("Failed to fetch stream for track %s: %s", track_id, resp.status_code)
                return None
            data = resp.json()
            stream = data.get("stream", {})
            return stream.get("stream_url") or stream.get("url")
        except Exception as e:
            logger.error("Error fetching stream URL: %s", e)
            return None
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "from backend.beatport import beatport_client; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/beatport.py
git commit -m "feat: Beatport top tracks and stream URL fetching"
```

---

### Task 3: Beatport API client — Tidal matching pipeline

**Files:**
- Modify: `backend/beatport.py` (append to class)

- [ ] **Step 1: Add normalize_mix_name helper and match_to_tidal method**

Add these methods inside the `BeatportClient` class, after `get_stream_url()`:

```python

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

    # Layer 2: Score ISRC candidates by mix name
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
            # Artist scoring
            t_artist = formatted["artist"].lower()
            if artist.lower() in t_artist or t_artist in artist.lower():
                score += 40
                details["artist_match"] = True
            # Remixer bonus
            for r in remixers:
                if r.lower() in t_artist or r.lower() in formatted["title"].lower():
                    score += 10
                    break
            # Mix name scoring
            if mix_name and self._normalize_mix(mix_name):
                t_title = formatted["title"].lower()
                if self._normalize_mix(mix_name) in t_title:
                    score += 30
                    details["mix_match"] = True
                elif any(w in t_title for w in self._normalize_mix(mix_name).split()):
                    score += 15
                    details["mix_match"] = "partial"
            # Duration scoring
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

    # Layer 4: If no results, try broader search
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
```

Note: This method imports `format_track` from `backend.search`. Add this import at the top of `beatport.py`:
```python
from backend.search import format_track
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "from backend.beatport import beatport_client; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/beatport.py
git commit -m "feat: 4-layer Beatport-to-Tidal matching pipeline"
```

---

### Task 4: Backend REST endpoints

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add import and four Beatport endpoints**

Add this import near the top of `main.py`, after the existing `from backend.search import ...` line:
```python
from backend.beatport import beatport_client
```

Add these four endpoints after the existing `/resolve` endpoint (around line 104):

```python

# --- Beatport Endpoints ---

@app.get("/beatport/genres")
async def beatport_genres():
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    genres = await asyncio.to_thread(beatport_client.get_genres)
    return {"genres": genres}


@app.get("/beatport/tracks/{genre_id}")
async def beatport_tracks(genre_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    tracks = await asyncio.to_thread(beatport_client.get_top_tracks, genre_id)
    return {"tracks": tracks}


@app.get("/beatport/preview/{track_id}")
async def beatport_preview(track_id: int):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    stream_url = await asyncio.to_thread(beatport_client.get_stream_url, track_id)
    if not stream_url:
        raise HTTPException(status_code=404, detail="No preview available")
    return {"stream_url": stream_url}


class MatchRequest(BaseModel):
    id: int
    name: str
    mix_name: str = ""
    artists: list[str] = []
    remixers: list[str] = []
    isrc: str = ""
    length_ms: int = 0


@app.post("/beatport/match")
async def beatport_match(req: MatchRequest):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not auth_manager.session:
        raise HTTPException(status_code=503, detail="Tidal session not available")
    track = {
        "id": req.id,
        "name": req.name,
        "mix_name": req.mix_name,
        "artists": req.artists,
        "remixers": req.remixers,
        "isrc": req.isrc,
        "length_ms": req.length_ms,
    }
    result = await asyncio.to_thread(
        beatport_client.match_to_tidal, track, auth_manager.session
    )
    return result
```

- [ ] **Step 2: Verify syntax and imports**

Run: `python3 -c "from backend.main import app; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: Beatport REST endpoints (genres, tracks, preview, match)"
```

---

### Task 5: Beatport auth endpoint and config

**Files:**
- Modify: `backend/main.py` (add Beatport auth endpoint)
- Modify: `config.yaml` (add optional beatport credentials section — manual edit by user)

- [ ] **Step 1: Add Beatport login endpoint**

Add this endpoint in the Beatport section of `main.py`:

```python

class BeatportLoginRequest(BaseModel):
    username: str
    password: str


@app.post("/beatport/auth")
async def beatport_auth(req: BeatportLoginRequest):
    if not auth_manager.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated to Tidal")
    success = await asyncio.to_thread(beatport_client.login, req.username, req.password)
    if not success:
        raise HTTPException(status_code=401, detail="Beatport login failed")
    return {"authenticated": True}


@app.get("/beatport/auth/status")
async def beatport_auth_status():
    return {"authenticated": beatport_client.authenticated}
```

Note: Place these after the existing Beatport endpoints from Task 4.

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "from backend.main import app; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: Beatport auth endpoints (login, status)"
```

---

### Task 6: Frontend API types and functions

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add Beatport types and API functions**

Add these types after the existing interface definitions in `api.ts` (after `WsMessage`, around line 103):

```typescript

export interface BeatportGenre {
  id: number;
  name: string;
  slug: string;
}

export interface BeatportTrack {
  id: number;
  name: string;
  mix_name: string;
  artists: string[];
  remixers: string[];
  bpm: number;
  key: string;
  genre: string;
  length: string;
  length_ms: number;
  isrc: string;
  cover_url: string | null;
  beatport_url: string;
}

export interface MatchCandidate {
  score: number;
  tidal_track: TrackResult;
  match_details: {
    isrc_match: boolean;
    mix_match: boolean | string;
    duration_match: string;
    artist_match: boolean;
  };
}

export interface MatchResult {
  confidence: number;
  auto_matched: boolean;
  candidates: MatchCandidate[];
}
```

Add these API functions after the existing `resolve` export (around line 151):

```typescript

export const beatport = {
  genres: () => request<{ genres: BeatportGenre[] }>('/beatport/genres'),
  tracks: (genreId: number) =>
    request<{ tracks: BeatportTrack[] }>(`/beatport/tracks/${genreId}`),
  preview: (trackId: number) =>
    request<{ stream_url: string }>(`/beatport/preview/${trackId}`),
  match: (track: {
    id: number;
    name: string;
    mix_name: string;
    artists: string[];
    remixers: string[];
    isrc: string;
    length_ms: number;
  }) =>
    request<MatchResult>('/beatport/match', {
      method: 'POST',
      body: JSON.stringify(track),
    }),
  login: (username: string, password: string) =>
    request<{ authenticated: boolean }>('/beatport/auth', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  authStatus: () => request<{ authenticated: boolean }>('/beatport/auth/status'),
};
```

- [ ] **Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: Beatport API types and functions on frontend"
```

---

### Task 7: MatchConfirmDialog component

**Files:**
- Create: `frontend/src/components/MatchConfirmDialog.tsx`

- [ ] **Step 1: Create the confirmation dialog component**

```tsx
import type { BeatportTrack, MatchCandidate } from '../api';
import { useApp } from '../context/AppContext';

interface Props {
  beatportTrack: BeatportTrack;
  candidates: MatchCandidate[];
  onSelect: (candidate: MatchCandidate) => void;
  onCancel: () => void;
}

export default function MatchConfirmDialog({ beatportTrack, candidates, onSelect, onCancel }: Props) {
  const { state } = useApp();

  const diffColor = (detail: string) => {
    if (detail === 'within_5pct') return 'var(--accent-primary)';
    if (detail === 'within_10pct') return 'var(--warning)';
    return 'var(--danger)';
  };

  const artistStr = beatportTrack.artists.join(', ');

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center"
      style={{ background: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)' }}
      onClick={onCancel}
    >
      <div
        className="mx-4 p-6 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        style={{
          background: 'var(--bg-mid)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius)',
          boxShadow: '0 16px 64px rgba(0, 0, 0, 0.5)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-1" style={{ color: 'var(--text-bright)' }}>
          Confirm Match
        </h2>
        <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
          Multiple versions found on Tidal. Select the correct one.
        </p>

        {/* Beatport reference */}
        <div
          className="flex items-center gap-3 p-3 rounded-md mb-4"
          style={{
            background: 'var(--accent-dim)',
            border: '1px solid rgba(0, 229, 199, 0.2)',
          }}
        >
          {beatportTrack.cover_url ? (
            <img
              src={beatportTrack.cover_url}
              alt=""
              className="w-10 h-10 rounded object-cover shrink-0"
            />
          ) : (
            <div
              className="w-10 h-10 rounded shrink-0 flex items-center justify-center text-xs"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
            >
              BP
            </div>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
              {beatportTrack.name}
              {beatportTrack.mix_name ? ` (${beatportTrack.mix_name})` : ''}
            </p>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
              {artistStr} · {beatportTrack.length} · {beatportTrack.bpm} BPM · {beatportTrack.key}
            </p>
          </div>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded shrink-0 mono"
            style={{ background: 'rgba(0, 229, 199, 0.15)', color: 'var(--accent-primary)' }}
          >
            Beatport
          </span>
        </div>

        {/* Tidal candidates */}
        <div className="space-y-2 mb-4">
          {candidates.map((c, i) => {
            const t = c.tidal_track;
            const qMap: Record<string, { bg: string; color: string }> = {
              HI_RES: { bg: 'rgba(0, 229, 199, 0.12)', color: 'var(--accent-primary)' },
              LOSSLESS: { bg: 'rgba(0, 184, 212, 0.1)', color: 'var(--accent-secondary)' },
            };
            const qStyle = qMap[t.quality] || { bg: 'var(--bg-surface)', color: 'var(--text-dim)' };

            return (
              <div
                key={i}
                className="glass p-3 flex items-center gap-3"
                style={{ border: '1px solid var(--glass-border)' }}
              >
                {t.cover_url ? (
                  <img
                    src={t.cover_url}
                    alt=""
                    className="w-10 h-10 rounded object-cover shrink-0"
                  />
                ) : (
                  <div
                    className="w-10 h-10 rounded shrink-0 flex items-center justify-center text-xs"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                  >
                    &#9834;
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                    {t.title}
                  </p>
                  <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                    {t.artist} · {t.album}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    {t.duration > 0 && (
                      <span
                        className="text-[10px] mono"
                        style={{ color: diffColor(c.match_details.duration_match) }}
                      >
                        {Math.floor(t.duration / 60)}:{String(t.duration % 60).padStart(2, '0')}
                      </span>
                    )}
                    <span
                      className="text-[10px] px-1 py-0.5 rounded mono"
                      style={{ background: qStyle.bg, color: qStyle.color }}
                    >
                      {t.quality}
                    </span>
                    <span
                      className="text-[10px] mono"
                      style={{ color: 'var(--text-dim)' }}
                    >
                      Score: {c.score}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => onSelect(c)}
                  className="btn-primary text-xs px-3 py-1.5 shrink-0"
                >
                  Select
                </button>
              </div>
            );
          })}
        </div>

        <div className="flex justify-end">
          <button
            onClick={onCancel}
            className="text-sm px-4 py-1.5 rounded"
            style={{ color: 'var(--text-dim)', border: '1px solid var(--glass-border)' }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MatchConfirmDialog.tsx
git commit -m "feat: MatchConfirmDialog for medium-confidence Beatport matches"
```

---

### Task 8: BeatportView component

**Files:**
- Create: `frontend/src/components/BeatportView.tsx`

- [ ] **Step 1: Create the BeatportView component**

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { beatport, queue } from '../api';
import { useApp } from '../context/AppContext';
import type { BeatportGenre, BeatportTrack, MatchResult, MatchCandidate } from '../api';
import MatchConfirmDialog from './MatchConfirmDialog';

export default function BeatportView() {
  const { state, dispatch } = useApp();
  const [genres, setGenres] = useState<BeatportGenre[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<number | null>(null);
  const [tracks, setTracks] = useState<BeatportTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [beatportAuth, setBeatportAuth] = useState<boolean | null>(null);
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [previewTrackId, setPreviewTrackId] = useState<number | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [matchingTrackId, setMatchingTrackId] = useState<number | null>(null);
  const [confirmTrack, setConfirmTrack] = useState<BeatportTrack | null>(null);
  const [confirmCandidates, setConfirmCandidates] = useState<MatchCandidate[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Check Beatport auth on mount
  useEffect(() => {
    beatport.authStatus().then((r) => setBeatportAuth(r.authenticated));
  }, []);

  // Load genres
  useEffect(() => {
    beatport
      .genres()
      .then((r) => {
        setGenres(r.genres);
        if (r.genres.length > 0) setSelectedGenre(r.genres[0].id);
        setLoading(false);
      })
      .catch(() => {
        setError('Failed to load genres');
        setLoading(false);
      });
  }, []);

  // Load tracks when genre changes
  useEffect(() => {
    if (selectedGenre === null) return;
    setLoading(true);
    setError(null);
    beatport
      .tracks(selectedGenre)
      .then((r) => {
        setTracks(r.tracks);
        setLoading(false);
      })
      .catch(() => {
        setError('Failed to load tracks');
        setLoading(false);
      });
  }, [selectedGenre]);

  const handlePreview = useCallback(async (track: BeatportTrack) => {
    if (previewTrackId === track.id) {
      audioRef.current?.pause();
      setPreviewTrackId(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewTrackId(track.id);
    try {
      const r = await beatport.preview(track.id);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(r.stream_url);
      audioRef.current = audio;
      audio.play();
      audio.onended = () => setPreviewTrackId(null);
      audio.onerror = () => {
        setPreviewTrackId(null);
        dispatch({
          type: 'ADD_TOAST',
          payload: { id: `prev-err-${Date.now()}`, type: 'error', title: 'Preview failed' },
        });
      };
      setPreviewLoading(false);
    } catch {
      setPreviewTrackId(null);
      setPreviewLoading(false);
      dispatch({
        type: 'ADD_TOAST',
        payload: { id: `prev-err-${Date.now()}`, type: 'error', title: 'Preview unavailable' },
      });
    }
  }, [previewTrackId, dispatch]);

  const handleDownload = useCallback(async (track: BeatportTrack) => {
    setMatchingTrackId(track.id);
    try {
      const result: MatchResult = await beatport.match({
        id: track.id,
        name: track.name,
        mix_name: track.mix_name,
        artists: track.artists,
        remixers: track.remixers,
        isrc: track.isrc,
        length_ms: track.length_ms,
      });

      if (result.auto_matched && result.candidates.length > 0) {
        const t = result.candidates[0].tidal_track;
        await queue.add({
          tidal_id: String(t.id),
          item_type: 'track',
          title: t.title,
          artist: t.artist,
          album: t.album,
          quality: state.settings.default_quality,
          format: state.settings.default_format,
        });
        dispatch({
          type: 'ADD_TOAST',
          payload: {
            id: `add-${Date.now()}-${t.id}`,
            type: 'info',
            title: 'Added to queue',
            detail: t.title,
          },
        });
      } else if (result.candidates.length > 0) {
        setConfirmTrack(track);
        setConfirmCandidates(result.candidates);
      } else {
        dispatch({
          type: 'ADD_TOAST',
          payload: {
            id: `nomatch-${Date.now()}`,
            type: 'error',
            title: 'Not on Tidal',
            detail: track.name,
          },
        });
      }
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `match-err-${Date.now()}`,
          type: 'error',
          title: 'Match failed',
          detail: track.name,
        },
      });
    } finally {
      setMatchingTrackId(null);
    }
  }, [state.settings, dispatch]);

  const handleConfirmSelect = useCallback(async (candidate: MatchCandidate) => {
    if (!confirmTrack) return;
    const t = candidate.tidal_track;
    try {
      await queue.add({
        tidal_id: String(t.id),
        item_type: 'track',
        title: t.title,
        artist: t.artist,
        album: t.album,
        quality: state.settings.default_quality,
        format: state.settings.default_format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-${Date.now()}-${t.id}`,
          type: 'info',
          title: 'Added to queue',
          detail: t.title,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to add to queue',
          detail: t.title,
        },
      });
    }
    setConfirmTrack(null);
    setConfirmCandidates([]);
  }, [confirmTrack, state.settings, dispatch]);

  const handleBeatportLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    try {
      await beatport.login(authUsername, authPassword);
      setBeatportAuth(true);
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: { id: `bplogin-${Date.now()}`, type: 'error', title: 'Beatport login failed' },
      });
    } finally {
      setAuthLoading(false);
    }
  };

  // Auth gate
  if (beatportAuth === false) {
    return (
      <div className="max-w-md mx-auto px-6 py-16 animate-fade-in">
        <div
          className="p-6 rounded-lg"
          style={{
            background: 'var(--bg-mid)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius)',
          }}
        >
          <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-bright)' }}>
            Beatport Login
          </h2>
          <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
            Enter your Beatport account credentials to access genre charts and previews.
          </p>
          <form onSubmit={handleBeatportLogin} className="space-y-3">
            <input
              type="text"
              value={authUsername}
              onChange={(e) => setAuthUsername(e.target.value)}
              placeholder="Username or email"
              required
              className="w-full bg-transparent border rounded-md px-3 py-2 text-sm"
              style={{
                borderColor: 'var(--glass-border)',
                color: 'var(--text-bright)',
              }}
            />
            <input
              type="password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              placeholder="Password"
              required
              className="w-full bg-transparent border rounded-md px-3 py-2 text-sm"
              style={{
                borderColor: 'var(--glass-border)',
                color: 'var(--text-bright)',
              }}
            />
            <button type="submit" disabled={authLoading} className="btn-primary w-full text-sm py-2">
              {authLoading ? 'Logging in...' : 'Login'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (beatportAuth === null) {
    return (
      <div className="text-center py-24">
        <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto" />
      </div>
    );
  }

  // Genres loading
  if (loading && genres.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
        <div className="mb-8 flex gap-2 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-8 rounded-full shrink-0"
              style={{
                width: `${60 + Math.random() * 40}px`,
                background: 'var(--bg-surface)',
              }}
            />
          ))}
        </div>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-16 rounded-lg"
              style={{
                background: 'var(--bg-surface)',
                opacity: 1 - i * 0.15,
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      {/* Genre selector */}
      <div className="mb-6 flex gap-1.5 overflow-x-auto pb-2 scrollbar-thin">
        {genres.map((g) => (
          <button
            key={g.id}
            onClick={() => setSelectedGenre(g.id)}
            className="shrink-0 px-3.5 py-1.5 rounded-full text-sm transition-all duration-200"
            style={{
              color: selectedGenre === g.id ? 'var(--accent-primary)' : 'var(--text-dim)',
              background: selectedGenre === g.id ? 'var(--accent-dim)' : 'var(--bg-surface)',
              border: selectedGenre === g.id
                ? '1px solid rgba(0, 229, 199, 0.3)'
                : '1px solid transparent',
            }}
          >
            {g.name}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-16">
          <p className="text-sm mb-3" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
          <button
            onClick={() => {
              setError(null);
              setLoading(true);
              beatport
                .tracks(selectedGenre!)
                .then((r) => { setTracks(r.tracks); setLoading(false); })
                .catch(() => { setError('Failed to load tracks'); setLoading(false); });
            }}
            className="btn-primary text-sm px-4 py-1.5"
          >
            Retry
          </button>
        </div>
      )}

      {/* Track list */}
      {!error && !loading && (
        <div className="space-y-2">
          {tracks.map((track, i) => {
            const artistStr = track.artists.join(', ');
            const isPreviewing = previewTrackId === track.id;
            const isMatching = matchingTrackId === track.id;

            return (
              <div
                key={track.id}
                className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {track.cover_url ? (
                    <img
                      src={track.cover_url}
                      alt=""
                      className="w-10 h-10 rounded-md object-cover shrink-0"
                      style={{ border: '1px solid var(--glass-border)' }}
                    />
                  ) : (
                    <div
                      className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                    >
                      &#9835;
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {track.name}
                      {track.mix_name ? (
                        <span style={{ color: 'var(--text-muted)' }}> ({track.mix_name})</span>
                      ) : null}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {artistStr}
                      {track.bpm > 0 ? ` · ${track.bpm} BPM` : ''}
                      {track.key ? ` · ${track.key}` : ''}
                      {track.length ? ` · ${track.length}` : ''}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <button
                    onClick={() => handlePreview(track)}
                    disabled={previewLoading && isPreviewing}
                    className="text-xs px-2.5 py-1.5 rounded-md transition-all duration-200 shrink-0 flex items-center gap-1"
                    style={{
                      color: isPreviewing ? 'var(--accent-primary)' : 'var(--text-dim)',
                      background: isPreviewing ? 'var(--accent-dim)' : 'var(--bg-surface)',
                      border: `1px solid ${isPreviewing ? 'rgba(0, 229, 199, 0.3)' : 'var(--glass-border)'}`,
                    }}
                  >
                    {previewLoading && isPreviewing ? (
                      <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : isPreviewing ? (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <rect x="1" y="0" width="3" height="10" rx="0.5" />
                        <rect x="6" y="0" width="3" height="10" rx="0.5" />
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <polygon points="1,0 9,5 1,10" />
                      </svg>
                    )}
                  </button>
                  <button
                    onClick={() => handleDownload(track)}
                    disabled={isMatching}
                    className="btn-primary text-xs px-3 py-1.5 shrink-0"
                  >
                    {isMatching ? (
                      <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin inline-block" />
                    ) : (
                      <>&#8595; Download</>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
          {tracks.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm" style={{ color: 'var(--text-dim)' }}>No tracks found for this genre</p>
            </div>
          )}
        </div>
      )}

      {/* Confirmation dialog */}
      {confirmTrack && (
        <MatchConfirmDialog
          beatportTrack={confirmTrack}
          candidates={confirmCandidates}
          onSelect={handleConfirmSelect}
          onCancel={() => { setConfirmTrack(null); setConfirmCandidates([]); }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BeatportView.tsx
git commit -m "feat: BeatportView with genre selector, preview, and download"
```

---

### Task 9: NavBar Beatport tab

**Files:**
- Modify: `frontend/src/components/NavBar.tsx`

- [ ] **Step 1: Read the current NavBar to find the tab list**

Read `frontend/src/components/NavBar.tsx` to understand the current tab structure.

- [ ] **Step 2: Add the Beatport tab**

Add a third tab between "Search" and "Queue". Look for the tab buttons rendered in the NavBar — there should be two buttons for "search" and "queue". Add a third:

```tsx
<button
  onClick={() => dispatch({ type: 'SET_TAB', payload: 'beatport' as AppState['activeTab'] })}
  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-all duration-200"
  style={{
    color: state.activeTab === 'beatport' ? 'var(--accent-primary)' : 'var(--text-dim)',
    background: state.activeTab === 'beatport' ? 'var(--accent-dim)' : 'transparent',
  }}
>
  <span className="text-xs">&#9835;</span>
  Beatport
</button>
```

- [ ] **Step 3: Update App.tsx to render BeatportView for the new tab**

In `App.tsx`, add the import:
```tsx
import BeatportView from './components/BeatportView';
```

And add a case in `renderView()`:
```tsx
case 'beatport':
  return <BeatportView />;
```

- [ ] **Step 4: Update AppState type to include 'beatport' tab**

In `frontend/src/context/AppContext.tsx`, update the `activeTab` type:
```tsx
activeTab: 'search' | 'queue' | 'beatport';
```

- [ ] **Step 5: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/NavBar.tsx frontend/src/App.tsx frontend/src/context/AppContext.tsx
git commit -m "feat: add Beatport tab to navigation"
```

---

### Task 10: Integration verification

- [ ] **Step 1: Run backend tests**

```bash
python3 -m pytest /Users/felipecanas/Projects/TidalExtractor/backend/tests/ -q
```
Expected: all existing tests pass

- [ ] **Step 2: Frontend type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 3: Backend import check**

```bash
python3 -c "from backend.main import app; from backend.beatport import beatport_client; print('All imports OK')"
```
Expected: All imports OK

- [ ] **Step 4: Commit if no changes needed**

No changes to commit (verification only).
