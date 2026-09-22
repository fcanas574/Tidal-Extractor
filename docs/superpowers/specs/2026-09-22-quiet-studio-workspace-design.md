# TidalExtractor Quiet Studio Workspace

**Date:** 2026-09-22  
**Status:** Draft for user review  
**Scope:** Frontend visual and layout redesign; existing download behavior remains authoritative

## Understanding summary

TidalExtractor is a local-first React/Vite application for finding and downloading TIDAL music. Its users care about reliable extraction, audio quality, preview playback, BPM, Camelot key, and download progress. The current UI is functional but makes users move through a long vertical stack of controls, filters, results, and detail content.

The approved direction is a **quiet studio workspace**: use the Stitch project as a visual reference for a compact music workstation, but remove its dense monitoring widgets, duplicated metrics, decorative engine panels, and unnecessary navigation. The redesign must preserve every existing capability, including catalog search, TIDAL-link resolution, artist/album/playlist navigation, DJ filters, queue management, realtime progress, retry/cancellation, history, stats, settings, waveform preview, BPM, key, format, and quality metadata.

Assumptions for this pass:

- The product remains English-first and single-user/local-first.
- React, TypeScript, Vite, Tailwind, and the current Context/API/WebSocket model remain in place.
- No new UI component library, router, backend provider, or download behavior is introduced.
- Desktop and mobile are both first-class layouts.
- The existing dark tokens in `Design.md` remain the visual foundation; only layout and component expression are being reorganized.

## Reference evidence

The exact requested Stitch exports are already stored in the repository:

- Explorer: `docs/stitch-reference/screens/264b9ec10e414e16b9f87e1c8bac4425/`
- Queue: `docs/stitch-reference/screens/025db632fb8f4a80bf15db6e172518c2/`
- Library: `docs/stitch-reference/screens/848d3a7140934cb09de39f361645e0e8/`
- Settings: `docs/stitch-reference/screens/03872f07754d42d7994f5ffe6bb88948/`

The HTML exports are reference material only. They contain static data, Tailwind CDN usage, remote fonts, and decorative controls that do not exist in the product contract. The current project’s strongest evidence is the existing React components, tests, `Design.md`, and the queue/realtime design specification from 2026-09-13.

## Goals and non-goals

### Goals

1. Reduce vertical travel by keeping the primary workflow inside a stable workspace frame.
2. Make the next action obvious on Search, Queue, History, Stats, and Settings.
3. Keep technical metadata visible without making every row look like a dashboard.
4. Use contextual inspectors and sheets so detail does not push the main workflow below the fold.
5. Preserve accessible keyboard, focus, loading, empty, partial, error, retry, reconnecting, and reduced-motion behavior.
6. Make the fixed preview player feel like a useful instrument rather than a competing page.

### Non-goals

- Rewriting the backend, download engine, quality fallback, tagging pipeline, or TIDAL auth flow.
- Adding recommendations, social features, cloud sync, multi-user accounts, or another provider.
- Adding unsupported “quick download,” folder scanning, profile, or storage-management actions merely because they appear in Stitch.
- Hiding or removing BPM, Camelot key, waveform, preview, quality, format, or queue controls to make the interface shorter.

## Information architecture and shell

### Desktop shell

At widths of approximately 1100px and above, the app uses three stable regions:

```text
┌────────────── compact studio rail ─────────────┬──────── command bar ────────┐
│ TidalExtractor                                 │ Search context · Activity · ⚙ │
│ Search                                         ├───────────────────────────────┤
│ Queue  3                                       │                               │
│ History                                         │        active workspace       │
│ Stats                                           │                               │
│                                                 │                               │
│ Activity                                        └───────────────────────────────┘
│ Settings                         fixed waveform/player bar                   │
└───────────────────────────────────────────────────────────────────────────────┘
```

- The left rail is compact and quiet: brand, four existing tabs, queue count, connection state, Activity, and Settings. It does not reproduce Stitch’s category headings or engine-status widget.
- The command bar is one row high and contains the active page context plus the controls that need to remain easy to reach. On Search it hosts the catalog search form; on other tabs it shows the page title and relevant contextual actions.
- The fixed player spans the app width at the bottom and reserves content space. It retains artwork, title, artist, play/pause, seek, waveform, volume, BPM, and Camelot key.
- The existing `activeTab` state remains the navigation source of truth. No router is required for this redesign.

At widths below the desktop threshold, the rail becomes a horizontally scrollable top navigation. The 768–1099px layout keeps visible labels and moves secondary shell actions into the existing Activity/Settings surfaces; below 768px it keeps the same top navigation pattern with 16px page gutters so it does not compete with the fixed player. Labels remain available to keyboard and assistive technology even when visual text is reduced.

### Surface ownership

- The document remains naturally scrollable on mobile and for long Settings content.
- At 1100px and above, the Search and Queue two-pane workspace uses bounded internal result/list scrolling after a complete flex/min-height chain is established. At narrower widths, the document remains the scroll owner. The app root and shared page shell must not hide scrollbars to achieve the effect.
- Activity and Settings remain app-owned overlays: a right-side panel on desktop and a bottom sheet/full-height surface on mobile. Only one is open at a time.
- The player’s reserved bottom spacing is calculated from its current compact/expanded state and safe-area inset so the final actionable row is never obscured.

## Search: explorer and extractor

Search remains the landing surface and keeps the current query, result type, filter, pagination, URL resolution, artist navigation, and album navigation behavior.

### Layout

```text
┌─ command search: [ query / TIDAL URL                         ] [Search] ┐
│ [Tracks] [Artists] [Albums] [Playlists] [Refine · 2]                    │
├───────────────────────────────────────┬─────────────────────────────────┤
│ results list                           │ contextual inspector            │
│ cover · title                          │ album/artist detail when open   │
│ artist · album · duration              │ close/back restores search       │
│ BPM · key · quality   Preview Download │ otherwise results use full width │
└───────────────────────────────────────┴─────────────────────────────────┘
```

- Use one calm list surface with separators instead of a separate raised card for every result.
- Keep rows compact but readable: cover, title, artist/album/duration, then a single technical metadata line containing BPM, Camelot key, genre/metadata source when present, and quality.
- `Download` remains the primary row action; `Preview` remains secondary. Artist and album names remain real buttons/links with the existing detail behavior.
- `Refine` opens an anchored, keyboard-accessible surface containing BPM range, Camelot key, compatible-key toggle, and genre. Active filters remain removable chips in the command area. Filter-empty states offer `Clear filters`.
- TIDAL-link detection remains explicit without adding a second search mode.
- `Load more` remains an explicit control at the end of track results. It does not become infinite scroll.
- When an album or artist detail is open on desktop, it occupies the inspector rather than pushing all results down. On mobile it becomes a full-height sheet or natural detail surface with a clear back action.
- Loading geometry, no-results, partial-result, request-error, and retry states keep their existing semantics and use stable list dimensions.

### Technical metadata

BPM, Camelot key, genre, quality, format, and duration use the project’s monospaced technical treatment. Color supports meaning but never carries it alone; text and accessible labels remain present. The animated rainbow key treatment is removed in favor of a stable, high-contrast key badge.

## Queue and download monitoring

Queue remains the canonical source of download state. The current reducer, REST reconciliation, WebSocket events, revision/progress guards, and persistent activity behavior are not replaced by visual state local to a component.

### Layout

```text
┌─ Download Queue ─────────────── active 2 · queued 1 · attention 1 ──────┐
│ [Select] [Retry failed] [Clear completed]                              │
├────────────────────────────────────────────┬─────────────────────────────┤
│ Active and attention items                  │ optional activity inspector │
│ title · context · status · progress         │ same canonical queue state  │
│ retry / inline cancel confirmation          │ reconnecting / stale        │
├────────────────────────────────────────────┴─────────────────────────────┤
│ Completed (collapsed by default)                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

- A compact summary strip answers “what is happening?” before the list begins.
- Active downloads appear first; failed items are visually distinct and offer Retry; completed items are collapsed by default.
- Selection mode and bulk actions appear only after the user enters selection mode.
- Active cancellation keeps the existing inline confirmation with explicit `Cancel download` and `Keep downloading` actions.
- Progress events update the queue/activity surface only. They do not create progress toasts.
- Reconnecting and stale are presentation states derived from connection/progress metadata, not new persisted queue statuses.
- The Activity control in the rail opens the same canonical activity panel already used by the app; on desktop it is the queue inspector surface, and on mobile it is the existing bottom sheet. It must not introduce a second download store or duplicate terminal feedback.

## History and library

The existing History tab becomes a library-like workspace without pretending that the current history API provides local folder scanning or complete album artwork.

- Use a compact header with item count and future-safe filter affordance space, without adding inactive controls.
- Render history as a dense, readable list/table-like surface with title, artist, album, quality, format, file size, date, and `Re-download` as the primary action.
- If artwork is already available from the API, use it; otherwise use a neutral SVG fallback rather than emoji or fabricated content.
- On wide screens, selecting a history row opens a metadata inspector; on mobile, the same information is shown in a sheet or stacked detail view. `Re-download` remains a separate explicit action.
- Empty and error states retain a direct explanation and Retry where appropriate.

## Stats

Stats remains intentionally calm rather than becoming a generic dashboard:

- one primary summary surface for downloaded tracks and storage;
- a compact quality-distribution view with explicit labels and accessible progress values;
- no decorative metric grid, invented time series, or unsupported storage controls;
- honest empty/error/loading states with the existing API as the source of truth.

## Settings and audio preferences

Settings remains an app-owned dialog/panel and keeps account, quality, format, waveform color, output path, quality probing, save, discard, logout, and error behavior.

- Desktop: a short section rail (`Account`, `Download`, `Preview`, `Output`) beside one content pane.
- Mobile: one-column sections or an accessible disclosure pattern; no nested scroll traps.
- The save footer remains visually stable and sticky within the desktop panel; on mobile it remains in normal flow after the fields. It shows `Save changes`, `Discard` when dirty, busy state, inline error, and success status.
- A failed save retains all edited values and leaves Retry available.
- Keep native selects for the existing settings choices; no screen-local authored select variant is added.

## Preview player

The player is the product’s visual signature: a restrained, technical waveform instrument anchored to the bottom edge.

- Desktop keeps artwork, title/artist, play/pause, seek, waveform, time, volume, BPM, and key in one compact bar.
- The waveform remains visible at all times while a preview is active, but its height is restrained. An expanded waveform mode is not required for this pass and must not cover the main action if retained.
- Mobile collapses secondary controls into a sheet or disclosure while retaining artwork, title, play/pause, and an accessible waveform/seek control.
- Waveform color preferences continue to control the existing 3-band/RGB renderer.
- `prefers-reduced-motion` removes looping rainbow/beat decoration and nonessential waveform animation while preserving playback and progress semantics.

## Visual system

The redesign retains the established tokens and intent from `Design.md`:

- Obsidian canvas, Graphite surfaces, Slate separators/hover surfaces, Porcelain primary text, Silver secondary text, and Mint success/connection accent.
- Geist/system sans fallback for UI; JetBrains Mono/system mono for technical metadata.
- 8px control radius, 12px large-surface radius, subtle 1px borders, shallow elevation, and no permanent glass or glow.
- Gradients are not used for shell, cards, buttons, or branding. The waveform may use controlled color blending because it communicates audio structure.
- Focus rings, contrast, touch targets, explicit text labels, and reduced-motion behavior are part of the visual system.

The single memorable element is the waveform/player instrument line. Everything around it should be quiet enough that cover art, title, download action, and progress are immediately legible.

The current `Design.md` describes the existing top-navigation adaptation of the Stitch reference. During implementation, its shell section must be reconciled to this approved compact-rail/command-bar direction, together with the runtime CSS/component changes, so it does not remain a competing source of truth.

## Shared behavior and accessibility contract

- Use semantic buttons for actions and links for navigation. Icon-only actions have accessible names and visible focus.
- Search fields have visible labels or an equivalent accessible name, an explicit clear action when non-empty, IME-safe behavior, stale-request protection, and preserved query state on errors.
- Panels and sheets use app-owned dialog/drawer semantics, Escape, click-away where appropriate, focus placement, focus containment for modal surfaces, and focus restoration.
- Every changed interactive control has idle, hover, focus, pressed, disabled, busy, success, warning, and error treatment where applicable.
- Use one shared toast system with at most three visible toasts, explicit close actions, correct live-region roles, and progress excluded from toasts.
- Preserve the existing queue behavior contract for reconnecting, stale, retry, cancellation, terminal events, and re-download identity.
- Do not introduce browser `alert`, `confirm`, or `prompt` UI.
- Long titles, missing artwork, empty results, partial data, network failures, narrow widths, 200% zoom, keyboard navigation, and reduced motion must not make the primary action unavailable.

## Implementation boundaries

Likely implementation touch points:

- `frontend/src/App.tsx` and `frontend/src/components/NavBar.tsx` for shell composition and navigation;
- `frontend/src/index.css` for layout tokens, surfaces, scrollbar baseline, focus, responsive geometry, and motion;
- `frontend/src/components/SearchView.tsx`, `TrackRow.tsx`, `AlbumCard.tsx`, `AlbumView.tsx`, and `ArtistView.tsx` for the explorer and inspector layout;
- `frontend/src/components/QueueView.tsx` and `DownloadActivityPanel.tsx` for monitoring surfaces;
- `frontend/src/components/HistoryView.tsx`, `StatsView.tsx`, `SettingsPanel.tsx`, and `AudioPlayerFooter.tsx` for secondary surfaces and playback;
- existing `AppContext`, API clients, and WebSocket hooks only where layout wiring or current behavior tests prove necessary.

Small shared components are appropriate for the rail, command bar, inspector frame, surface header, and status/metadata primitives if they are reused across at least two screens. Avoid a parallel UI state store or screen-local copies of queue/toast behavior.

No backend changes are expected for the visual redesign. If implementation discovers a missing API field required to display an existing feature, stop and document that contract gap rather than inventing client data.

## Validation plan and acceptance criteria

Before declaring the implementation complete:

1. Run the frontend test suite and build: `rtk npm test -- --run` and `rtk npm run build`.
2. Run `rtk git diff --check` and the frontend design audit/verification required by the premium UI skill.
3. Review at least 1440px desktop, 1024px tablet, and 390px mobile layouts.
4. Exercise Search with text, TIDAL URL, empty query, active DJ filters, no results, partial results, request error, Retry, Load more, artist detail, and album detail.
5. Exercise Queue with active progress, reconnecting, stale, failed/retry, inline cancellation, completed collapse, selection mode, and terminal feedback.
6. Exercise Settings with dirty state, save success, save failure/Retry, Escape, click-away, keyboard focus, and reduced motion.
7. Exercise the player with waveform data, unavailable BPM/key, play/pause, seek, volume, 3-band/RGB modes, and mobile controls.
8. Verify that History and Stats preserve API-driven content, loading, empty, and error behavior.
9. Compare the redesigned screens against the Stitch exports for hierarchy and tone while confirming that density is materially lower than the references.

The redesign is successful when the primary action is apparent within one viewport, common Search/Queue tasks do not require repeated page-length scrolling on desktop, all existing technical audio features remain visible or one deliberate interaction away, and no shell or overlay obscures the last actionable content.

## Open implementation risks

- The existing history API may not contain enough artwork or filesystem metadata for a true album-grid library; the implementation must not fake those fields.
- Moving Search detail into an inspector changes layout ownership but must preserve the existing reducer and request-cancellation behavior.
- Internal list scrolling can improve desktop density but must be verified at narrow widths, zoom, keyboard focus, and with long content before becoming canonical.
- `Design.md` currently documents the top navigation as the adaptation choice; it must be reconciled during implementation rather than left stale.
