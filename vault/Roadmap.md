# Roadmap

Planned and deferred features, drawn from handoff docs and design specs.

**See:** [[Work Log]] · [[Design Specs]] · [[DJ Filters]]

## Deferred: DJ Export (Phase C)

User explicitly deferred this during the DJ Filters session ("A and B first, if possible we'll tackle C"):

- [ ] **M3U playlist export** — standard playlist format
- [ ] **Rekordbox XML export** — for Pioneer DJ hardware/software
- [ ] **Serato export format** — for Serato DJ
- [ ] **Export only filtered tracks** — pipe DJ filter results into an export

Source: `handoff/Session-2026-06-23-dj-filters-complete.md`

## Optional Enhancements (DJ Filters)

From the DJ filters handoff — polish ideas not yet prioritized:

- [ ] Dual-handle range slider for BPM (visual polish over two number inputs)
- [ ] Camelot Wheel modal visualization (per spec §5.3)
- [ ] BPM pulse preview (metronome while browsing)
- [ ] Smart crates (auto-populate by BPM/key rules)
- [ ] Key history (remember last-used key filter)

## Search Pagination — Potential Follow-ups

The "Load More" feature shipped with several `fix:` commits, suggesting edge cases remain. Potential improvements:

- [ ] Eviction policy for `_search_results_cache` (currently unbounded in-memory dict)
- [ ] Include filters in cache key if fresh results are desired on filter change
- [ ] Persist cache across restarts (currently lost on reboot)

## Known Limitations to Address

From [[DJ Filters]] and [[Gotchas & Traps]]:

- [ ] Genre search `genre:` prefix doesn't support subgenres ("Tech House")
- [ ] Tidal BPM/Key coverage ~87% on electronic — consider fallback enrichment
- [ ] No client-side caching of BPM/Key (re-fetched each search)
- [ ] `test_detect_key_mocked` test failing (librosa mock issue)

## Architecture / Tech Debt

- [ ] Commit untracked `backend/freqblog.py` (currently imported but untracked — see [[Active Work]])
- [ ] Investigate/remove `tidal.db` (unused empty file) and nested `TidalExtractor/` dir
- [ ] Consider formal migration versioning (schema is currently implicit ALTER-with-try/except)
- [ ] Logging is DEBUG at root — may want INFO for production
- [ ] `wsConnected` flag provenance (see [[Frontend useWebSocket]] — hook doesn't dispatch it)

## Future Feature Ideas (speculative)

- [ ] Concurrent downloads (currently strictly sequential — `_running` flag)
- [ ] Per-track quality fallback (currently session-wide probe only)
- [ ] Playlist/album batch download with progress aggregation
- [ ] Cover art embedding from local files (currently URL fetch only)
- [ ] Lyrics support
- [ ] Multi-account support (currently single-user by design)

## Design Specs Available

Implementation-ready specs exist in `docs/superpowers/specs/` for features already built (see [[Design Specs]]). Future work should follow the same spec → plan → execute pattern.

## See Also

- [[Work Log]] · [[Active Work]] · [[Design Specs]] · [[Gotchas & Traps]]
