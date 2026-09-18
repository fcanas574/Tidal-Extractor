# TidalExtractor frontend UI/UX rework

**Date:** 2026-09-13  
**Status:** Validated design  
**Scope:** Frontend experience and the realtime feedback required to make it reliable

## Goal

Give TidalExtractor a polished, music-first experience with the clarity, rhythm,
spacing, and accessibility expected from a high-quality music product. Apple
Music is the quality reference for hierarchy and presentation; TidalExtractor
keeps its own identity and remains focused on verified downloads and DJ
discovery.

## Understanding summary

- TidalExtractor is a local-first, single-user React SPA for downloading Tidal
  tracks, albums, and playlists.
- Its primary users are DJs and audiophiles who care about verified quality,
  format, BPM, Camelot key, metadata, and preview playback.
- The current frontend includes authentication, Search, Queue, History, Stats,
  Settings, stacked toasts, WebSocket progress, and a fixed waveform player.
- SearchView and QueueView carry the most functional density and need the
  clearest hierarchy.
- Active download toasts can remain visible indefinitely, lose context during
  connection gaps, and cannot always be dismissed manually.
- The rework includes responsive behavior, purposeful motion, accessible
  feedback, and the realtime fixes required to prevent stale UI state.
- Existing download APIs and backend behavior remain the product foundation.

## Assumptions and constraints

- The interface remains in English for this pass.
- Desktop and mobile layouts are both first-class targets.
- The app remains single-user and local-first; no multi-tenant or analytics
  work is included.
- Existing React, Tailwind, and CSS infrastructure will be reused. No component
  library or animation dependency will be added.
- A small additive integer `revision` field may be added to queue responses and
  the SQLite queue schema so REST reconciliation can order snapshots safely.
- The queue migration must distinguish an already-present column from an
  unexpected database error; unexpected migration failures must surface during
  startup instead of being silently ignored.
- The UI must remain responsive with at least 50 visible search or queue items.
- Motion must respect `prefers-reduced-motion`.
- Tidal credentials, local session data, and download paths must not be exposed
  through new client-side services.
- Core download, quality verification, tagging, preview, and DJ filter behavior
  must remain available.

## Non-goals

- Redesigning the download engine, quality fallback algorithm, metadata tagging,
  or Tidal authentication protocol.
- Adding another music provider.
- Introducing speculative features such as recommendations, accounts, cloud
  sync, or social sharing.
- Replacing the existing state library or adding a design-system dependency.

## Decision log

| ID | Decision | Alternatives considered | Reason |
|---|---|---|---|
| D1 | Rework the entire frontend, prioritizing Search, Queue, and notifications. | Limit the work to visual polish on one screen. | The reported quality problem spans the whole shell, while Search and Queue carry the highest risk and density. |
| D2 | Use an editorial music workspace as the visual direction. | DJ control room; immersive listening canvas. | It balances music-first polish with fast downloader workflows and existing DJ features. |
| D3 | Use a refined dark palette with selective surfaces and a mint accent. | Keep the current neon glass treatment everywhere. | Fewer glows and stronger contrast make hierarchy calmer and more legible. |
| D4 | Make the queue the single source of truth for download state. | Let WebSocket events drive independent toast state. | A persistent activity surface can reconcile REST and WebSocket updates without stuck notifications. |
| D5 | Use persistent activity for active work and toasts for discrete events. | Keep one toast per download visible throughout its lifecycle. | Progress needs context and actions; success and error messages can remain brief. |
| D6 | Mark an item stale after 20 seconds without progress as an initial threshold. | Hide the item or wait indefinitely. | The user needs an actionable state during connection gaps; the threshold can be tuned after observing real progress cadence. |
| D7 | Keep motion short, purposeful, and reduced-motion aware. | Add broad hover and entrance animation across every element. | Motion should explain state changes without making a technical workflow noisy. |
| D8 | Validate the rework with focused frontend tests, build checks, and visual review. | Rely on manual inspection only. | The current frontend has coverage mainly for the player and lacks tests for the notification and realtime paths. |
| D9 | Treat the database queue `id` as work-item identity. | Deduplicate by `tidal_id`. | A deliberate re-download of the same track is a new queue job and must remain visible. |
| D10 | Add a per-item integer `revision` plus a monotonic progress guard for reconciliation. | Trust whichever REST or WebSocket update arrives last; use second-precision timestamps. | REST polling can be older than a WebSocket event; an integer revision gives exact ordering without clock precision issues. |
| D11 | Derive `reconnecting` and `stale` as presentation states. | Add them to the persisted `QueueItem.status` union. | They describe client observation, not backend download lifecycle, so existing API status contracts stay stable. |
| D12 | Poll while active work exists, regardless of WebSocket connection state. | Poll only while `wsConnected` is true. | Reconciliation matters most during a connection gap. |
| D13 | Preserve current pagination semantics: track results support Load More; album and playlist result sets remain as returned. | Redesign pagination for every content type in this pass. | The rework improves presentation without expanding the search API contract. |
| D14 | Make queue polling single-flight. | Start a new request every five seconds unconditionally. | A slow response must not overlap a later response and reintroduce stale ordering races. |
| D15 | Keep the existing sequential WebSocket broadcast for this single-user scope. | Redesign fan-out with per-client queues. | Local single-user scale does not justify a new transport layer; revisit only after measured multi-tab latency. |
| D16 | Keep full queue rendering for the current scale and document a 500-item ceiling. | Add virtualization or queue pagination now. | Completed items are collapsed and the product is local-first; add a windowing strategy only if measured queue size causes jank. |
| D17 | Render progress in the persistent activity surface only; progress events do not create toasts. | Keep one persistent progress toast per download. | One source of progress reduces duplicated state and cognitive load. |
| D18 | Preserve edited Settings values and show an inline save error with retry. | Reset the form or silently return to Save. | A failed save must not make the user guess whether quality or output changes took effect. |
| D19 | Require a short inline confirmation before cancelling an active download. | Delete immediately on one click. | Cancellation changes work in progress and must remain reversible until confirmed. |
| D20 | Use explicit mobile stacking rules and safe-area spacing. | Let fixed player, drawers, and navigation overlap naturally. | Small screens need predictable access to both activity and playback controls. |
| D21 | Distinguish empty search, filter-empty, partial, and request-error states. | Reuse one generic “No results” message. | DJs need to know whether to change the query, clear filters, retry, or wait. |

## Review resolutions

### Skeptic / Challenger

- **Accepted:** exact queue ordering, client-derived stale/reconnecting states,
  polling during WebSocket loss, cancellable reconnect cleanup, always-visible
  toast dismissal, mobile stacking, and explicit pagination semantics were
  added to the design.
- **Resolved:** queue database `id` remains work identity, so a deliberate
  re-download is not incorrectly merged with an older job. Reducer tests use
  an `AppProvider` harness and do not require exporting private implementation
  details.

### Constraint Guardian

- **Accepted:** second-precision timestamps were replaced by an integer
  per-item `revision`; migrations must fail loudly on unexpected errors; polling
  is single-flight; and the 500-item rendering ceiling is documented.
- **Rejected with rationale:** per-client WebSocket buffering is outside the
  single-user/local scope and remains a measured upgrade path if multi-tab
  latency appears. Queue virtualization is deferred until the documented
  ceiling causes measurable jank.

### User Advocate

- **Accepted:** progress no longer creates competing toasts; Settings retains
  dirty values on save failure; active cancellation has confirmation; mobile
  safe-area rules are explicit; controls receive semantic labels; search copy
  is shorter; and empty states distinguish query, filter, partial, and error
  outcomes.

## Final design

### Visual system

The core palette is:

| Token | Value | Role |
|---|---|---|
| Obsidian | `#0B0D12` | Page background |
| Graphite | `#161A23` | Primary surfaces |
| Slate | `#2A3040` | Borders and separators |
| Porcelain | `#F5F7FA` | Primary text |
| Silver | `#9BA5B5` | Secondary text |
| Mint | `#8DE7D5` | Primary action and active state |

Glass and blur are reserved for the preview player, activity panel, and other
  surfaces that need separation from the content beneath them. Results and
queue rows use solid surfaces for readability and predictable contrast.

The main UI uses a local system sans-serif stack. `JetBrains Mono` remains a
secondary face for quality, format, BPM, Camelot, percentages, and other
technical values. Album art, title, and artist carry more visual weight than
technical metadata.

The visual reference follows Apple Music's use of focused sections and clear
content roles while preserving TidalExtractor's waveform and verified-quality
identity: [Apple Music](https://www.apple.com/apple-music/).

### App shell and responsive layout

The desktop shell has a compact top navigation with brand, Search, Queue,
History, Stats, connection state, and Settings. The content area is centered at
approximately 1280px.

Search and Queue use a 12-column layout when space allows:

```text
┌─ Brand ─ Search ─ Queue ─ History ─ Stats ───────── Connection · Settings ┐
│                                                                          │
│  Main workflow content                                  Activity panel   │
│  Search, results, queue, history, or stats                Download state   │
│                                                                          │
└──────────────────── compact preview player ──────────────────────────────┘
```

The activity panel is contextual on desktop and becomes a bottom sheet on
mobile. At widths below 768px, the primary navigation becomes horizontally
scrollable, Settings uses the full viewport width, and the activity sheet is
limited to `min(78vh, 560px)`. Only one bottom sheet is open at a time. When
the activity sheet is open, the player collapses to its compact bar and the
sheet sits above that bar and `env(safe-area-inset-bottom)`. The preview player
becomes a one-line compact bar on mobile and can expand to show waveform
details. Content receives bottom spacing for the player, open sheet, and safe
area so fixed surfaces never hide the last actionable row.

Each surface has one primary action. Navigation uses visible labels, active
state, queue count, and a small connection indicator without turning status
into decorative noise.

### Search and results

Search is the landing surface. One labeled input accepts either text or a Tidal
URL and shows a restrained detected-link state. Its short placeholder is
“Search tracks, artists, albums, or paste a Tidal link”; the existing
`track - artist` syntax is described as helper text instead of being embedded
in the placeholder. Tracks, Albums, and Playlists use a segmented control. DJ
filters open through `Refine`, with active filters shown as removable chips;
genre-only search remains supported.

Results use consistent music rows:

```text
[ cover ]  Title
           Artist · Album · Duration
           BPM · Camelot                         Quality · Preview · Download
```

Download is the primary action and preview is secondary. Quality remains
visible because it is central to the product promise. Album and playlist
results retain their existing download actions. Artist resolution becomes a
detail surface with a clear return path, artist artwork, top tracks, and album
grid.

Loading states use skeleton rows with the same geometry as loaded results.
Empty, partial, failed, and retry states explain the next action instead of
leaving a blank area. A query with no matches offers a new search path; active
filters with no matches offer `Clear filters`; a partial response explains
what loaded and keeps the available results; and a request error offers retry
without clearing the query.

The existing pagination contract remains explicit: `Load More` appends track
results using the current offset and limit; album and playlist results are
rendered from the response returned by the API and are not given a new
pagination model in this rework.

### Queue and download activity

QueueView groups items into active, pending/failed, and completed sections.
Active work appears first, with the current download receiving slightly more
visual emphasis. Completed items are collapsed by default. Bulk actions appear
only after selection mode is entered.

The persistent activity surface shows each active item's title, progress,
current status, and available action. Statuses are queued, downloading,
reconnecting, stale, complete, or failed. Retry remains a direct action. A
queued item can be removed immediately; an active download first shows an
inline confirmation with explicit `Cancel download` and `Keep downloading`
actions. Completion moves the item into the completed group with a short,
understandable transition.

The queue remains the canonical state. WebSocket progress updates and REST
polling reconcile into that state; the activity surface and toasts render from
the resulting queue state. The backend queue response gains an additive integer
`revision` value, backed by a backward-compatible SQLite column migration. The
revision increments on every queue mutation and is included in queue REST
items and progress/terminal WebSocket messages. The frontend records the
newest revision per queue id and ignores an older snapshot. Progress also moves
monotonically for a known queue id, so a late response cannot reduce visible
progress. A new queue database id is a new work item even when its `tidal_id`
matches an older item.

`reconnecting` and `stale` are derived activity labels. They do not change the
persisted `QueueItem.status`, which remains `queued`, `downloading`, `complete`,
or `failed`. The client records the last observed progress time for active
items; an item is stale only after progress has been observed and then remains
quiet for 20 seconds.

### Notification and realtime behavior

Toasts are limited to discrete events such as an item being added, a download
completing, a failure, settings being saved, or quality being detected. A
progress WebSocket event updates the queue and activity surface only; it never
creates or updates a progress toast. Toasts have a visible close action,
bounded stacking of at most three visible items, a timer for non-critical
events, and a timer that pauses while focused or hovered.

Active downloads do not rely on toasts. If no progress arrives for 20 seconds,
the activity item becomes stale and offers a clear recovery action. A WebSocket
disconnect changes the connection indicator and activity status to
reconnecting; it does not create a noisy stream of repeated toasts.

The WebSocket reconnect timer is cancellable on unmount. Queue polling remains
available while active work exists, whether or not WebSocket is connected, and
reconciles missed messages after reconnection. Queue reconciliation compares
`revision` and applies a monotonic progress guard for local events. Polling is
single-flight: a new request is skipped while the previous request is pending.
It must preserve the newest known item state and avoid unnecessary full-list
visual jumps.

The existing sequential WebSocket fan-out remains in scope for the local
single-user product. A slow-client queue is a known ceiling; it is not replaced
with per-client buffering unless real multi-tab latency demonstrates a need.

The reducer remains the coordination point for auth, queue, settings, preview,
history, stats, connection, notification state, and client freshness metadata.
No independent download state is introduced inside `ToastContainer`.

### Secondary surfaces

- **History:** clean download list with title, artist, quality, format, size,
  date, and re-download as the primary action.
- **Stats:** a calm summary of tracks, storage, and quality distribution;
  avoid a grid of interchangeable cards.
- **Settings:** grouped drawer sections for account, download defaults, preview,
  and output. Keep Save changes visible when dirty. On save failure, retain all
  edited values, show an inline error beside the save action, and keep Retry
  available. Support close button, Escape, click-away, and focus management.
- **Auth:** one clear connect action. Reveal device URL and code progressively,
  with explicit waiting, success, and failure states.
- **Player:** keep artwork, title, artist, play/pause, seek, waveform, and
  key/Camelot available without covering content.

### Motion and accessibility

Motion is limited to short view transitions, drawer movement, interpolated
progress, row insertion, and meaningful status changes. Shimmer, pulse, and
transform-heavy effects are disabled under `prefers-reduced-motion`.

Interactive elements have visible focus, keyboard access, appropriate labels,
and comfortable touch targets. Navigation exposes current state with
`aria-current`; Settings exposes `aria-expanded`, `aria-controls`, and dialog
semantics; icon-only controls have explicit `aria-label` values. Progress uses
a polite status region; important failures use an alert region. Close actions
remain available even when an item has an automatic dismiss time. Status uses
text, icon, and shape in addition to color. Existing encoding errors in text
icons are replaced with inline SVG or safe text.

### Error handling and edge cases

| Case | Expected UI behavior |
|---|---|
| WebSocket disconnects during download | Show reconnecting state; keep the item visible; continue reconciliation. |
| No progress for 20 seconds | Mark item stale and offer recovery; do not delete it or leave an unexplained toast. |
| WebSocket reconnects after missed events | Poll and reconcile the queue before clearing stale presentation. |
| REST returns an older queue snapshot | Compare `revision` and progress before applying it; keep the newer local item. |
| Same track is deliberately re-downloaded | Keep the new database queue id as a separate work item. |
| Download completes or fails | Remove active progress state, update queue, and show one terminal toast. |
| User dismisses a toast | Remove only the toast; never alter queue state. |
| Search returns no items | Explain that there are no matches and preserve the search/refinement path. |
| Filters eliminate all matches | Say the filters caused the empty state and offer Clear filters. |
| Search request fails | Preserve the query and offer Retry. |
| Settings save fails | Keep edited values visible, show the error, and allow retry. |
| User cancels an active download | Require inline confirmation with explicit keep/cancel choices. |
| Drawer opens on mobile | Use a bottom sheet or full-height panel with controlled focus. |
| Player and activity sheet are both requested on mobile | Keep the player compact, place the sheet above it, and reserve safe-area spacing. |
| Reduced motion enabled | Preserve all state changes while removing movement effects. |

### Validation strategy

Add focused tests for queue reconciliation with newer and older `revision`
values, monotonic progress, client-derived stale/reconnecting labels,
completion, error, and work-item identity. Test that polling is single-flight,
that progress events do not create toasts, and that failed Settings saves retain
dirty values. Exercise reducer behavior through a
small `AppProvider` test harness; keep the reducer private unless an extraction
is required by the implementation. Test WebSocket reconnect cleanup and
connection state, plus manual/automatic toast dismissal. Add component coverage
for the activity surface, cancellation confirmation, settings save errors,
keyboard drawer behavior, mobile stacking, and accessible status messages where
the implementation introduces those paths.

Run `npm test`, `npm run build`, targeted lint for modified frontend files, and
`git diff --check`. Review the UI at desktop and mobile widths, with an active
queue, empty states, failure states, a lost connection, and reduced motion.

## Implementation boundaries

Implementation should extend the current components and Context/reducer flow in
small, reviewable slices. The likely touch points are:

- `frontend/src/index.css` for tokens, shared surfaces, motion, focus, and
  reduced-motion rules.
- `frontend/src/App.tsx` and `frontend/src/context/AppContext.tsx` for shell
  composition and canonical state reconciliation.
- `frontend/src/hooks/useWebSocket.ts` for cancellable reconnect behavior.
- `backend/models.py`, the queue response path, and the downloader progress
  broadcaster for the additive `revision` value and backward-compatible
  migration needed by safe reconciliation.
- `frontend/src/components/NavBar.tsx`, `SearchView.tsx`, `QueueView.tsx`,
  `ToastContainer.tsx`, `SettingsPanel.tsx`, `AuthGate.tsx`,
  `HistoryView.tsx`, `StatsView.tsx`, and `AudioPlayerFooter.tsx` for surface
  implementation.
- New small components only where repeated row, status, activity, or surface
  behavior cannot remain clear inside the existing files.

The next artifact should be an implementation plan that orders the work around
the canonical queue/realtime model first, then the shared visual primitives,
then the high-density views and the secondary surfaces.
