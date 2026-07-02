# Project Overview

**TidalExtractor** is a web-based music downloader for [Tidal](https://tidal.com) that emphasizes *verified* audio quality and DJ-oriented track discovery. It is a personal, single-user tool (one Tidal account at a time).

## The Value Proposition

Most downloaders trust whatever stream Tidal hands you. TidalExtractor **probes actual bitrate with ffprobe** before committing to a download, falling back down a quality ladder (HiRes Lossless → Lossless → High → Normal) until it finds a preset that genuinely delivers. This protects against FakinTheFunk-style misreporting and ensures you get what you pay for.

## Core Capabilities

| Capability | Detail |
|------------|--------|
| **Quality-first downloads** | Two-phase fetch with top-down preset fallback + ffprobe verification |
| **Track / Album / Playlist** | Search and download any content type |
| **Format conversion** | FLAC (native), MP3 320k, M4A/AAC 320k via ffmpeg |
| **Full metadata tagging** | Title, artist, album, genre, year, label, ISRC, BPM, key, cover art — via mutagen |
| **DJ search filters** | BPM range (60–200), Camelot key (1A–12B), harmonic compatibility, curated genres |
| **Tri-band waveform preview** | Rekordbox-style lows/mids/highs waveform via wavypy, click-to-preview |
| **Camelot key detection** | Local audio analysis (librosa chroma) + FreqBlog API hybrid |
| **Real-time progress** | WebSocket-powered download progress with toast notifications |
| **Download history** | Browse, re-download, open-folder actions |
| **Device-wide stats** | Total tracks, storage used, quality breakdown |
| **Session persistence** | Tidal OAuth session saved locally (no re-auth on launch) |
| **Quality cache** | Probed quality preset cached per session |

## Who It's For

- **Audiophiles** who want to verify they're actually getting lossless/HiRes
- **DJs** preparing harmonic sets (BPM + key filtering, waveform preview, Camelot embedding)

## Design Constraints

- **Single-user** — one Tidal account, no multi-tenant concerns
- **Local-first** — runs on `localhost`, downloads to a configurable output dir
- **HiRes requires PKCE** — LOSSLESS and below use the standard BTS manifest; HiRes uses a different manifest type requiring PKCE-enabled OAuth

## See Also

- [[System Design]] · [[Tech Stack]] · [[Download Pipeline]] · [[DJ Filters]]
