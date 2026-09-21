# TIDAL Metadata Enrichment and Refinement Design

**Date:** 2026-09-21  
**Status:** Design and written spec approved; implementation plan ready
**Scope:** First phase of FreqBlog-backed refinement for existing TIDAL catalog flows

## Goal

Improve BPM, key, and genre refinement for tracks already found in TIDAL without making FreqBlog a second download catalog. TIDAL remains the primary catalog and metadata source; FreqBlog fills gaps when TIDAL does not provide enough DJ metadata.

## User-facing outcome

When a user searches, opens an artist page, or opens an album:

- TIDAL-provided BPM and key continue to appear immediately when present.
- Missing BPM or key values can be filled from FreqBlog.
- FreqBlog genre data can appear as optional track metadata.
- BPM and key filters use the merged metadata where available.
- The existing genre-prefix search remains the fast first-pass genre filter.
- A FreqBlog outage, quota response, queued lookup, or missing API key never removes an otherwise valid TIDAL result or blocks preview/download actions.

The first phase does not add global FreqBlog catalog browsing, standalone genre pages, or global key discovery. Those endpoints return FreqBlog catalog records that require a separate TIDAL availability and ID-resolution workflow.

## Product decisions

### Metadata precedence

TIDAL values are authoritative when non-null. FreqBlog fills missing fields and contributes fields TIDAL does not expose, especially genre, confidence, alternate BPM, and source information. The merge must not silently overwrite a TIDAL BPM or key with a FreqBlog value.

Each enriched track exposes enough provenance for the UI and future diagnostics:

- `bpm_source`: `tidal`, `freqblog`, or `null`
- `key_source`: `tidal`, `freqblog`, or `null`
- `genre_source`: `freqblog` or `null`
- `bpm_confidence`: numeric value when provided
- `key_confidence`: numeric value when provided
- `bpm_alt`: alternate/half-time/double-time BPM when provided
- `metadata_status`: `complete`, `partial`, `miss`, `queued`, `rate_limited`, or `unavailable`

### Enrichment timing

The backend enriches visible track pages automatically. When BPM/key filters are active, it enriches the candidate pool before filtering so filtered results use the same merged metadata model. The candidate pool is bounded to the existing TIDAL search cap and FreqBlog bulk-request limits; the API response reports partial/unavailable metadata rather than pretending that an external outage is a definitive no-match.

Album and artist track endpoints use the same enrichment service for the tracks they return. Search, artist, and album rows therefore share one metadata contract.

### Genre behavior

The current TIDAL `genre:<value>` prefix remains the first-pass search behavior and its current curated choices remain intact. FreqBlog genre is displayed as metadata and is available to the merge layer, but this phase does not reinterpret the entire TIDAL result set through FreqBlog’s catalog taxonomy. This avoids false “no results” states caused by cross-catalog matching and taxonomy differences.

### Failure behavior

FreqBlog is an optional fallback. The service must:

- skip calls when `FREQBLOG_API_KEY` is absent;
- use ISRC for exact lookups when available, then title/artist fallback;
- send requests in documented batches of at most 50 tracks;
- treat not-found and incomplete analysis as metadata misses;
- recognize queued/on-demand responses without blocking the request indefinitely;
- recognize rate limiting and preserve TIDAL values;
- apply bounded timeouts;
- return partial results when only some tracks are enriched;
- avoid logging the API key or full request headers.

## Architecture

### Existing boundaries

- `backend/search.py` formats TIDAL objects into the shared track response shape.
- `backend/freqblog.py` currently performs one title/artist lookup and drops partial results.
- `backend/models.py` owns the SQLite connection and existing application caches.
- `backend/main.py` owns search and catalog detail endpoints plus local BPM/key filtering.
- `frontend/src/api.ts` defines the typed HTTP contract.
- `frontend/src/components/TrackRow.tsx` owns the shared track metadata badges.
- `frontend/src/components/SearchView.tsx` owns search refinement controls and result states.

### New boundary

Add a catalog metadata enrichment service, preferably in `backend/catalog_metadata.py`, with three responsibilities:

1. Select tracks that are missing fallback metadata.
2. Read/write normalized FreqBlog results through the database cache.
3. Merge cached/provider metadata into formatted TIDAL track dictionaries using the precedence rules above.

The FreqBlog client remains responsible only for HTTP transport, response normalization, and provider status handling. Endpoint code should call the enrichment service rather than implement provider logic inline.

### Data flow

```text
TIDAL objects
    ↓ format_track()
formatted TIDAL tracks
    ↓ metadata service: cache lookup by TIDAL id / ISRC
cache hits + missing tracks
    ↓ FreqBlog /bulk (≤ 50 items per request)
normalized provider results and statuses
    ↓ merge without overwriting non-null TIDAL BPM/key
enriched track response
    ↓ optional BPM/key filtering
search / artist / album API response
```

### Cache

Add a SQLite table for catalog metadata rather than using the short-lived in-memory search response cache. The cache record is keyed by TIDAL track ID and retains the ISRC, normalized metadata JSON, provider status, and timestamps/expiry. Store misses and temporary statuses with shorter expiries than successful metadata so a transient provider state can recover without repeated calls on every request.

The cache must be safe when the application starts with an existing database: initialization creates the table if absent and does not require a destructive migration.

### API contract

Extend the existing track response with optional metadata fields listed in the metadata precedence section. Keep existing fields and endpoint shapes backward compatible.

The frontend must not call FreqBlog directly. The API key remains server-side.

## UI behavior

Use the existing dark audiophile design language in `Design.md`:

- Keep BPM/key badges compact and technical.
- Add genre as a secondary badge only when present.
- Make provider status supplemental text or an accessible label, not a color-only signal.
- Preserve current search loading, empty, error, retry, and pagination states.
- Do not add a second search/refine surface or duplicate filter controls.
- Do not make missing metadata look like an error when the provider was simply unavailable.

The UI should continue to work with old API responses that omit the new optional fields.

## Testing requirements

### Backend unit tests

- FreqBlog requests prefer ISRC and fall back to title/artist.
- Bulk payloads are capped at 50 tracks.
- Provider response normalization preserves genre, confidence, alternate BPM, and status information.
- `202`, `404`, `429`, timeouts, malformed responses, and missing API keys degrade to explicit statuses without raising through search.
- TIDAL BPM/key values win over FreqBlog values.
- FreqBlog fills missing BPM/key and adds genre.
- Cache hits skip provider calls; expired records are refreshed.
- Partial cache/provider results preserve all TIDAL tracks.
- Search filtering uses merged fallback BPM/key values.
- Artist and album endpoints use the same enrichment contract.

### Frontend tests

- API types and query encoding remain compatible.
- Track rows render optional genre/source metadata without requiring it.
- Existing filter controls still work and display active chips.
- Search results remain downloadable and previewable when metadata is missing or unavailable.
- Loading, partial metadata, no-results, and retry states remain accessible.

### Verification

Run the backend test suite, frontend tests, frontend typecheck/build, and the project’s UI audit if available. Exercise search, a filtered search, an album detail, an artist detail, a missing-provider case, and a narrow viewport manually before declaring completion.

## Out of scope

- FreqBlog global genre catalog browsing and cross-catalog TIDAL resolution.
- FreqBlog global `/key` or `/bpm` discovery pages.
- Replacing TIDAL search or its curated genre taxonomy.
- Changing download tagging behavior beyond preserving existing DJ metadata fallback behavior.
- Queue filtering or a new queue metadata screen.

## Acceptance criteria

1. A track with TIDAL BPM/key keeps those values even when FreqBlog returns different values.
2. A track missing TIDAL BPM/key can display FreqBlog fallback values when the provider responds successfully.
3. Genre can be returned and displayed without making genre a required field.
4. Search BPM/key filters can match tracks using fallback values.
5. Provider failures do not turn a successful TIDAL search, artist page, or album page into an error.
6. Repeated requests use cached provider results and do not call FreqBlog once per track when a batch is possible.
7. The existing remix/version title behavior remains unchanged.
8. Existing unrelated working-tree changes are not modified.
