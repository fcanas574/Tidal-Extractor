# 🎵 TidalExtractor — Memory Vault

> Single source of truth for project knowledge. Last refreshed **2026-06-27**.
> Repo: `/Users/felipecanas/Projects/TidalExtractor` · Branch: `master`

A web-based Tidal music downloader with verified audio quality, DJ-oriented harmonic mixing tools, Camelot key detection, and tri-band waveform previews.

---

## 🚀 Start Here

- [[Project Overview]] — What it is, who it's for, the value proposition
- [[Tech Stack]] — Languages, frameworks, libraries, tooling
- [[File Tree]] — Every source file and what it owns
- [[System Design]] — How the pieces fit together (diagrams)

## 🧠 Architecture & Patterns

- [[Request Lifecycle]] — How a download flows end-to-end
- [[State Management]] — Frontend reducer + WebSocket sync model
- [[Realtime Updates]] — WebSocket broadcast + reconnection
- [[Auth Flow]] — Tidal OAuth device-link & session persistence

## ⚙️ Subsystems (the deep stuff)

- [[Download Pipeline]] — Quality probe → fallback → convert → tag
- [[Search Subsystem]] — Query, score, enrich, paginate, DJ-filter
- [[Key Detection]] — Chroma analysis + Camelot mapping + FreqBlog
- [[Waveform Engine]] — wavypy tri-band analysis pipeline
- [[Quality Verification]] — ffprobe bitrate thresholds & presets
- [[DJ Filters]] — BPM, Camelot, harmonic compatibility, genre

## 📦 Backend Modules

[[Backend main|main]] · [[Backend downloader|downloader]] · [[Backend search|search]] · [[Backend models|models]] · [[Backend auth|auth]] · [[Backend config|config]] · [[Backend quality|quality]] · [[Backend converter|converter]] · [[Backend tagger|tagger]] · [[Backend waveform|waveform]] · [[Backend key_detection|key_detection]] · [[Backend freqblog|freqblog]] · [[Backend ws|ws]] · [[Backend audioop_stub|audioop_stub]]

## 🎛 Frontend Modules

[[Frontend api|api.ts]] · [[Frontend AppContext|AppContext]] · [[Frontend useWebSocket|useWebSocket]] · [[Components]] · [[Frontend Vite Config|vite.config]]

## 📚 Reference

- [[API Reference]] — Every REST + WebSocket endpoint
- [[Data Model]] — SQLite schema, tables, columns
- [[Configuration]] — config.yaml, env vars, settings panel
- [[Development Setup]] — How to run, build, test
- [[Glossary]] — Camelot, PKCE, BTS manifest, etc.

## 📝 Project Memory

- [[Work Log]] — Chronological feature history
- [[Active Work]] — Current branch state & recent commits
- [[Roadmap]] — Planned features & deferred items
- [[Gotchas & Traps]] — Quirks, footguns, and lessons learned
- [[Design Specs]] — Specs & plans in `docs/`

---

*This vault is generated from the source tree. Keep it current as the project evolves.*
