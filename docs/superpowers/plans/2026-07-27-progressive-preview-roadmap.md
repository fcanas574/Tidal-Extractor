# Progressive Full-Track Preview Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this roadmap task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver instant full-track preview playback, progressive waveform analysis, selectable 3Band/RGB colors, and a separate quality-preserving download-speed investigation.

**Architecture:** Execute three independent implementation plans in order: instant stream startup first, streaming waveform analysis second, and color preferences third. Keep the existing combined preview endpoint as a fallback throughout. Run the download-speed plan separately as research and measurement only until quality-preserving optimizations are proven.

**Tech Stack:** FastAPI, asyncio, ffmpeg, NumPy, SciPy, wavypy, React, TypeScript, Vite, SQLite-backed settings, existing REST API.

## Global Constraints

- Full-track previews must retain the current low-quality preview selection; do not reduce download quality further.
- Audio playback must not wait for waveform, key, or BPM analysis.
- The existing `GET /preview/{track_id}` endpoint remains available as a fallback.
- Streaming waveform processing must preserve filter state and waveform-pixel carry-over across chunks.
- 3Band colors are low blue, mid orange, high white; RGB colors are low red, mid green, high blue.
- Color changes are presentation-only and must not trigger audio analysis.
- Download-speed work must not skip ffprobe verification, weaken quality fallback, or lower selected download quality.

## Execution Order

1. Execute [instant full-track preview plan](2026-07-27-instant-full-track-preview-plan.md). This creates the fast stream/metadata API and frontend lifecycle without changing wavypy.
2. Execute [streaming waveform plan](2026-07-27-streaming-waveform-processing-plan.md). This replaces the metadata worker’s full-file analysis with stateful PCM chunk processing and one temporary WAV artifact.
3. Execute [waveform color modes plan](2026-07-27-waveform-color-modes-plan.md). This adds persisted 3Band/RGB selection and canvas palettes using existing low/mid/high data.
4. Execute [download-speed research plan](2026-07-27-quality-preserving-download-speed-research-plan.md) separately. It produces measurements and a recommendation; it does not alter download behavior by itself.

## Shared Verification Gate

- Backend: `python3 -m pytest backend/tests/ -q`
- Frontend: `cd frontend && npm run build`
- Manual full-track preview: click a multi-minute track, verify audio begins before metadata completes, seek while analysis runs, and verify the final waveform replaces the provisional waveform.
- Manual fallback: force metadata failure and verify audio still plays or the old combined endpoint can be used.

