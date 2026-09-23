# Quiet Studio Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign TidalExtractor as a compact, responsive music workspace while preserving its current catalog, download, DJ, settings, history, and preview behavior.

**Architecture:** Keep React Context as the source of truth and reorganize the existing Vite UI around a compact desktop rail, contextual command area, bounded search and queue panes, and the existing fixed preview player. Extract only the repeated shell and inspector behavior into shared components; retain current API, reducer, WebSocket, queue, and preview ownership.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, shared CSS variables, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-22-quiet-studio-workspace-design.md`

## Global Constraints

- Preserve all existing catalog, link-resolution, artist/album/playlist navigation, DJ-filter, queue, retry, cancellation, history, stats, settings, waveform, BPM, key, quality, and format behavior.
- Use the existing Context/API/WebSocket model; do not add a UI library, router, backend provider, or second download store.
- Keep the existing Obsidian, Graphite, Slate, Porcelain, Silver, and Mint token roles in `Design.md`.
- Desktop shell breakpoint: approximately 1100px; below it use horizontal top navigation and document scrolling.
- The Search and Queue bounded list panes are enabled only at 1100px and above after their full flex/min-height chain is established.
- At narrower widths, the document remains the scroll owner; preserve 16px mobile gutters and safe-area spacing.
- The fixed player retains artwork, title, artist, play/pause, seek, waveform, volume, BPM, and Camelot key.
- Use an app-owned panel/sheet with Escape, focus placement, focus containment when modal, and focus restoration.
- Search keeps explicit Load more pagination; completed queue items remain collapsed by default.
- Progress stays in canonical queue/activity state and does not create progress toasts.
- Use native selects for existing settings choices; do not add a screen-local authored select.
- Keep all labels, keyboard access, visible focus, reduced-motion behavior, missing-artwork handling, and loading/empty/partial/error/retry states.
- Do not add mock data for API fields the product does not return.

## Review Focus

- Narrow viewport plus fixed player: the final row, search actions, and sheet controls remain reachable; exercise at 390px with long titles and safe-area padding.
- Search detail plus preserved results: opening/closing album or artist detail must not lose the query, filters, results, pending metadata, or request-cancellation behavior.
- Queue reconnect and stale state: REST and WebSocket updates continue to reconcile by queue id/revision, with monotonic progress and no progress toasts.
- Missing/partial history metadata: rows and inspector show only returned values and an honest neutral artwork fallback.
- Dirty settings plus save failure: retain all edited values, keep retry available, and restore focus correctly after dismissing the panel.

## File map

- `frontend/src/App.tsx` — app shell layout, responsive main region, and view composition.
- `frontend/src/components/NavBar.tsx` — desktop studio rail and compact horizontal mobile navigation; queue and connection status.
- `frontend/src/components/WorkspaceInspector.tsx` — shared inspector frame for Search detail and selected history metadata, with responsive sheet behavior only if the same component can own those two use cases cleanly.
- `frontend/src/components/SearchView.tsx` — search command area, result panes, detail placement, filters, pagination, and state treatment.
- `frontend/src/components/TrackRow.tsx` and `frontend/src/components/AlbumCard.tsx` — compact result density and stable technical metadata/action rows.
- `frontend/src/components/AlbumView.tsx` and `frontend/src/components/ArtistView.tsx` — render existing detail content in an inspector-sized column without changing API or reducer behavior.
- `frontend/src/components/QueueView.tsx` — compact summary, grouped queue, selection, retry, cancellation, and completed disclosure.
- `frontend/src/components/DownloadActivityPanel.tsx` — same queue-derived data in the existing Activity drawer/sheet; no duplicate store.
- `frontend/src/components/HistoryView.tsx` — history list and selected-row details using only `HistoryItem` fields returned by the API.
- `frontend/src/components/StatsView.tsx` — restrained summary and quality distribution.
- `frontend/src/components/SettingsPanel.tsx` — grouped settings panel and stable save footer.
- `frontend/src/components/AudioPlayerFooter.tsx` — compact fixed player and technical metadata presentation; keep audio lifecycle and waveform drawing intact.
- `frontend/src/index.css` — shell geometry, component surfaces, responsive behavior, global scrollbar tokens, focus, safe-area, and reduced motion.
- `frontend/src/components/*.test.tsx` — update component coverage for any changed observable UI contracts; add `HistoryView.test.tsx` if History selection behavior is implemented.
- `Design.md` — reconcile the documented shell, responsive behavior, player signature, and token mapping with the approved design.
- `UX-CONTRACT.md` — establish durable owners for navigation, search/detail, list scrolling, queue/activity, panels, settings save/recovery, player, and status feedback from the canonical template.

## Task 1: Establish shared workspace shell and canonical contracts

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/components/NavBar.test.tsx`
- Modify: `frontend/src/index.css`
- Modify: `Design.md`
- Create: `UX-CONTRACT.md` from the premium skill's `assets/UX-CONTRACT.template.md`

**Interfaces:**
- `NavBar` continues to consume `useApp()` and dispatches the existing `SET_TAB`, `TOGGLE_ACTIVITY_PANEL`, and `TOGGLE_SETTINGS_PANEL` actions.
- `AppContent` continues to render the same four active tabs and mounts Activity, Settings, Toast, and Audio Player once.
- `UX-CONTRACT.md` records existing state/action owners; it does not redefine API lifecycle or queue status.

- [x] **Step 1: Extend navigation tests for rail semantics**

Add assertions in `NavBar.test.tsx` for the four current tabs, `aria-current="page"`, queue count, connection status, and accessible Activity/Settings triggers. Preserve existing state fixture and test style.

- [x] **Step 2: Run the focused navigation test and confirm the new layout expectation fails**

Run from `frontend`: `rtk npm test -- --run src/components/NavBar.test.tsx`.

Expected: the existing top-only shell does not satisfy the desktop rail assertions added in Step 1.

- [x] **Step 3: Add the responsive shell structure**

In `App.tsx`, create a semantic app shell with the navigation rail, workspace column, main content, and one global mount for Activity, Settings, Toast, and Player. Use a shell class and CSS grid/flex chain with `min-width: 0` and `min-height: 0`; do not set document-level `overflow: hidden`.

In `NavBar.tsx`, retain the same buttons and state actions while rendering the brand, four tabs, queue count, connection status, Activity, and Settings in a compact desktop rail. At widths below 1100px render the same navigation as a horizontally scrollable top bar with labels. Do not hide scrollbar chrome; keep all focus targets visible.

- [x] **Step 4: Define shared shell and scrollbar tokens**

In `index.css`, add named shell dimensions and semantic scrollbar colors. Apply `scrollbar-width` and `scrollbar-color` globally, plus WebKit thumb/track/hover/active rules and forced-colors behavior. Remove the mobile rule that sets `nav::-webkit-scrollbar { display: none; }`. Add desktop rail, workspace, mobile top bar, and safe-area geometry without making the document unscrollable.

- [x] **Step 5: Reconcile durable documentation**

Update `Design.md` shell and motion sections to describe the approved desktop rail/mobile top navigation and waveform instrument. Keep its existing palette and type values. Create `UX-CONTRACT.md` from the exact template and record canonical owners for tabs, page/document scroll, search detail, queue/activity, settings panel/save, toast, and player. Link verification evidence to existing component tests and the build command.

- [x] **Step 6: Run focused navigation coverage and build**

Run `rtk npm test -- --run src/components/NavBar.test.tsx` and `rtk npm run build` from `frontend`.

Expected: both pass with the shell rendered at desktop and mobile CSS breakpoints.

## Task 2: Reflow Search into a compact command area and result inspector

**Files:**
- Modify: `frontend/src/components/SearchView.tsx`
- Modify: `frontend/src/components/TrackRow.tsx`
- Modify: `frontend/src/components/TrackRow.test.tsx`
- Modify: `frontend/src/components/AlbumCard.tsx`
- Modify: `frontend/src/components/AlbumCard.test.tsx`
- Modify: `frontend/src/components/AlbumView.tsx`
- Modify: `frontend/src/components/ArtistView.tsx`
- Create or modify: `frontend/src/components/WorkspaceInspector.tsx`
- Modify: `frontend/src/components/SearchView.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Continue using `useApp()` search session and existing actions (`SEARCH_STARTED`, `SEARCH_SUCCEEDED`, `SEARCH_FAILED`, `SET_SEARCH_FILTERS`, `DETAIL_*`, and `CLOSE_DETAIL`).
- Continue using `search`, `resolve`, and `queue` API methods with existing abort signals and generation guards.
- `WorkspaceInspector` accepts a title, close callback, and existing React detail content; it does not own fetch, preview, or queue state.

- [x] **Step 1: Pin compact row information and actions in tests**

Extend `TrackRow.test.tsx` to assert title/context, duration, BPM, Camelot key, quality, Preview, and Download remain accessible. Extend `AlbumCard.test.tsx` to keep album metadata, open, and download actions available with long text.

- [x] **Step 2: Run focused row tests and confirm the compact-row contract fails**

Run from `frontend`: `rtk npm test -- --run src/components/TrackRow.test.tsx src/components/AlbumCard.test.tsx`.

Expected: new layout-specific action and metadata assertions fail until the rows are reorganized.

- [x] **Step 3: Create the shared inspector frame**

Add `WorkspaceInspector.tsx` with a semantic complementary region, heading, explicit close button, and responsive class hooks. Keep focus on the close button only when opening the surface is modal; desktop complementary content remains non-modal. The mobile presentation uses natural document flow or a modal sheet with the documented focus contract.

- [x] **Step 4: Compact Search controls without changing search behavior**

In `SearchView.tsx`, place the labeled search field, clear action, submit button, result-type segment, and Refine trigger in a compact command region. Keep active chips adjacent to it. Keep genre-only query, URL detection, filter removal, retries, and Load more handlers unchanged. Retain the current `AbortController` and generation checks.

- [x] **Step 5: Use the inspector for existing artist/album detail**

Keep results mounted when details are open. On desktop at 1100px and above, place `AlbumView` or `ArtistView` into `WorkspaceInspector` and constrain only the detail column; on mobile render the same detail content in the page flow with a visible Back to search action. Existing `DETAIL_*` actions and request handling remain the only detail state source.

- [x] **Step 6: Reduce result row chrome and keep DJ data legible**

In `TrackRow.tsx`, use one row surface/separator, a fixed cover box, a compact title/context line, one monospaced metadata line, and stable Preview/Download targets. Use a static Camelot badge instead of rainbow styling. Retain actual values and omit absent fields without inventing placeholders. Apply similar compact spacing to `AlbumCard.tsx` without changing its props or click behavior.

- [x] **Step 7: Add the bounded two-pane scroll chain**

Add Search workspace CSS: at 1100px and above, constrain the results pane with `min-height: 0` and visible vertical scrollbar; inspector scrolls independently only if its content exceeds available height. At smaller breakpoints, remove fixed pane heights and let the document scroll. Keep bottom padding above the player.

- [x] **Step 8: Run Search, row, and build checks**

Run `rtk npm test -- --run src/components/SearchView.test.tsx src/components/TrackRow.test.tsx src/components/AlbumCard.test.tsx src/components/AlbumView.test.tsx src/components/ArtistView.test.tsx` and `rtk npm run build` from `frontend`.

Expected: all search/detail/row coverage passes and TypeScript/Vite builds.

## Task 3: Simplify Queue while retaining canonical Activity behavior

**Files:**
- Modify: `frontend/src/components/QueueView.tsx`
- Modify: `frontend/src/components/QueueView.test.tsx`
- Modify: `frontend/src/components/DownloadActivityPanel.tsx`
- Modify: `frontend/src/components/DownloadActivityPanel.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Queue screen and Activity panel read `state.queue`, `state.queueMeta`, and `state.wsConnected`; reducer/API actions remain canonical.
- Keep existing `queue.remove`, `queue.add`, bulk-removal, retry, and activity cancellation calls.
- Do not add a second queue store, new persisted queue statuses, or progress toasts.

- [x] **Step 1: Pin Queue status and action states in component tests**

Extend `QueueView.test.tsx` to cover compact summary counts, active item progress, failed retry, completed disclosure, selection actions, and active-cancel confirmation. Extend `DownloadActivityPanel.test.tsx` to retain reconnecting/stale status and the existing queue-derived progress behavior.

- [x] **Step 2: Run focused Queue and Activity tests to verify the expected failures**

Run from `frontend`: `rtk npm test -- --run src/components/QueueView.test.tsx src/components/DownloadActivityPanel.test.tsx`.

Expected: summary and condensed layout assertions fail before the Queue view update.

- [x] **Step 3: Add a compact Queue summary and grouping**

In `QueueView.tsx`, keep the existing derived active/failed/completed groups and action handlers. Render a concise status summary at the top, active and failed items first, and completed items in the existing collapsed disclosure. Keep selection controls hidden until select mode is active.

- [x] **Step 4: Tighten queue item surfaces and cancellation feedback**

Reduce padding and decorative borders while keeping title, artist/album, status, quality/format, progress, error, Retry, and cancellation. Preserve inline cancellation confirmation with the exact `Cancel download` and `Keep downloading` labels. Preserve explicit success/error feedback.

- [x] **Step 5: Align Activity panel with the shell and responsive panel contract**

Keep Activity data sourced from the same queue and freshness metadata. Update existing panel classes to align with the desktop rail/player geometry and mobile safe-area sheet. Ensure overlay dismissal, Escape, focus containment/restoration, and active cancellation behavior remain available. Do not display a second Activity copy inside QueueView.

- [x] **Step 6: Bound Queue scrolling only on wide desktop**

Use the same 1100px flex/min-height chain as Search; Queue’s list owns its overflow only on wide desktop. Tablet/mobile use document scrolling and reserve space above the player/sheet.

- [x] **Step 7: Run Queue, Activity, Context, and build checks**

Run `rtk npm test -- --run src/components/QueueView.test.tsx src/components/DownloadActivityPanel.test.tsx src/context/AppContext.test.tsx` and `rtk npm run build` from `frontend`.

Expected: queue ordering/revision semantics, actions, and view states pass without changes to reducer ownership.

## Task 4: Make History and Stats compact and truthful

**Files:**
- Modify: `frontend/src/components/HistoryView.tsx`
- Create: `frontend/src/components/HistoryView.test.tsx`
- Modify: `frontend/src/components/StatsView.tsx`
- Modify: `frontend/src/index.css`
- Reuse: `frontend/src/components/WorkspaceInspector.tsx`

**Interfaces:**
- History rows use the existing `HistoryItem` shape and `history.list`/`history.reDownload` APIs.
- Stats uses the existing `stats.get` API and current Context store.
- No artwork, path, or metadata values are synthesized when absent from API responses.

- [x] **Step 1: Add History success, missing-data, selection, and failure coverage**

Create `HistoryView.test.tsx` with mocked `history.list` and `history.reDownload`. Cover loading, empty, failed load/Retry, populated list, absent optional album, metadata inspector open/close, long title, and re-download pending/success/error.

- [x] **Step 2: Run the new History test and confirm current layout lacks inspector behavior**

Run from `frontend`: `rtk npm test -- --run src/components/HistoryView.test.tsx`.

Expected: the selection and inspector assertions fail before HistoryView is changed.

- [x] **Step 3: Implement compact History rows and selected-item inspector**

Keep the current fetch lifecycle and re-download handler. Use a compact list with title, artist, album, quality, format, size, date, and explicit Re-download. Row selection opens the shared inspector; missing cover/metadata use a neutral fallback or are omitted. Use a non-clickable semantic row container with real selection and action buttons.

- [x] **Step 4: Simplify Stats hierarchy**

Keep the same API, metric values, quality breakdown, progress semantics, and loading/error/Retry states. Present tracks and storage together in one calm summary, then a compact quality distribution with text labels and accessible values. Remove only visual duplication, not actual data.

- [x] **Step 5: Run History, Stats, API, and build checks**

Run `rtk npm test -- --run src/components/HistoryView.test.tsx src/api.test.ts` and `rtk npm run build` from `frontend`. Stats component behavior is checked with the project’s existing test coverage if present; do not add a new Stats test harness unless the redesign changes an untested API interaction.

Expected: History’s API-derived information and Stats values remain intact.

## Task 5: Reorganize Settings into grouped audio preferences

**Files:**
- Modify: `frontend/src/components/SettingsPanel.tsx`
- Modify: `frontend/src/components/SettingsPanel.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Continue to use existing `settings.get`, `settings.update`, `quality.cache`, `quality.probe`, and `auth.logout` API methods.
- Retain `Settings`, current draft state, save state, error state, and Context updates.
- Keep native selects/choice controls already used by the component; do not add new dependencies.

- [x] **Step 1: Add tests for all preserved settings and save recovery states**

Extend `SettingsPanel.test.tsx` for grouped Account/Download/Preview/Output sections, quality and format choices, waveform 3Band/RGB choices, output directory, dirty state, busy save, success, failed save retaining values, Retry, Escape close, and restored trigger focus.

- [x] **Step 2: Run the focused Settings test and identify missing expectations**

Run from `frontend`: `rtk npm test -- --run src/components/SettingsPanel.test.tsx`.

Expected: the current ungrouped drawer does not satisfy the grouped-panel layout assertions.

- [x] **Step 3: Recompose settings content into section navigation and one pane**

Retain current field controls and state update functions. Add a short section rail on desktop that jumps to labeled Account, Download, Preview, and Output sections. At mobile width, render sections in one natural-flow column without nested scroll traps. Keep the panel title and close action stable.

- [x] **Step 4: Make save feedback stable and responsive**

Use a sticky footer inside the desktop panel and normal flow on mobile. Keep button dimensions stable in busy state; show inline saved/error feedback and Retry while preserving draft values. Keep Discard conditional on dirty state and keep Disconnect account visually separated from Save.

- [x] **Step 5: Verify dialog interaction and native select behavior**

Confirm labels remain associated with current controls, focus remains inside the modal while open, Escape and click-away close it, focus returns to the triggering control, and existing option popups remain native. Keep `novalidate` on any existing product forms and use no browser-native alert/confirm/prompt.

- [x] **Step 6: Run Settings and build checks**

Run `rtk npm test -- --run src/components/SettingsPanel.test.tsx` and `rtk npm run build` from `frontend`.

Expected: the full current Settings behavior remains usable in both wide and narrow panels.

## Task 6: Refine the fixed preview player without changing audio lifecycle

**Files:**
- Modify: `frontend/src/components/AudioPlayerFooter.tsx`
- Modify: `frontend/src/components/AudioPlayerFooter.test.tsx`
- Modify: `frontend/src/components/AudioPlayerFooterVolume.test.tsx`
- Modify: `frontend/src/components/VolumeControl.tsx` only if the responsive layout needs a wrapper, not for volume logic
- Modify: `frontend/src/index.css`

**Interfaces:**
- Keep the current `preview.getStream`/`preview.getMetadata` flow, abort handling, active-preview token checks, canvas renderer, palette settings, `VolumeControl`, and Context actions.
- Keep BPM and Camelot values sourced from preview metadata.
- Keep seek and playback behavior unchanged while reorganizing visual grouping.

- [x] **Step 1: Pin player controls and metadata in tests**

Update player component tests to assert artwork/title/artist, play/pause, seek, volume, waveform canvas/loading/unavailable states, BPM, and Camelot key remain available. Assert key presentation is static when playing and honors reduced motion for nonessential animation.

- [x] **Step 2: Run focused player tests before changing layout**

Run from `frontend`: `rtk npm test -- --run src/components/AudioPlayerFooter.test.tsx src/components/AudioPlayerFooterVolume.test.tsx src/components/VolumeControl.test.tsx`.

Expected: newly added static badge/layout assertions fail while existing audio lifecycle checks pass.

- [x] **Step 3: Recompose the desktop player as one restrained instrument bar**

Keep audio element lifecycle, canvas drawing, event handlers, and API calls. Put track identity, playback/seek, waveform, time, volume, BPM, and Camelot key into a stable compact layout. Remove the animated rainbow key badge and looping BPM beat wash while leaving the values and waveform color modes intact.

- [x] **Step 4: Add narrow-screen player arrangement**

At mobile widths keep artwork, title/artist, play/pause, and an accessible seek/waveform action in the visible compact strip. Move secondary controls into the existing details disclosure/sheet, preserve 44px targets, and account for safe-area bottom space.

- [x] **Step 5: Protect motion and scrollbar behavior**

Use the global reduced-motion baseline for player transitions; ensure playback and progress still update. Keep waveform and seek controls keyboard-operable and provide visible focus. Do not hide scrollbars in the new player sheet.

- [x] **Step 6: Run player and build checks**

Run `rtk npm test -- --run src/components/AudioPlayerFooter.test.tsx src/components/AudioPlayerFooterVolume.test.tsx src/components/VolumeControl.test.tsx` and `rtk npm run build` from `frontend`.

Expected: preview transport, metadata, color selection, and volume behavior remain unchanged.

## Task 7: Integrate, audit, and visually review the redesigned workspace

**Files:**
- Modify as needed: all files listed above
- Verify: `Design.md`, `UX-CONTRACT.md`, `frontend/src/index.css`, and Stitch exports under `docs/stitch-reference/screens/`
- Evidence: `premium-audit.json` generated at the project root by the premium UI audit command

**Interfaces:**
- All views remain reachable through the existing `activeTab` state.
- Activity and Settings remain mutually exclusive app-owned panels.
- Player, queue, and toast status remain derived from current Context/API state.

- [x] **Step 1: Run the complete frontend suite and production build**

Run `rtk npm test -- --run` and `rtk npm run build` from `frontend`.

Expected: all existing and changed frontend tests pass; Vite and TypeScript produce a production build.

- [x] **Step 2: Run the premium static audit**

Run `rtk proxy python3 /Users/felipecanas/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py /Users/felipecanas/Projects/TidalExtractor --mode strict --output /Users/felipecanas/Projects/TidalExtractor/premium-audit.json`.

Expected: no blocking ownership/contract findings. Treat findings about untouched legacy controls separately from findings introduced by changed files; fix any changed-surface violations.

- [x] **Step 3: Review the UI at the three agreed viewport widths**

Run the Vite dev server and inspect at 1440px, 1024px, and 390px. Exercise Search and Queue scroll ownership, inspector/panel opening, player reservation, narrow Settings, reduced motion, keyboard focus, empty results, failures, and long titles. Compare hierarchy to the four local Stitch images; record any unresolved issue instead of claiming it was visually checked if browser access is unavailable.

Visual-review note: Search, History, Queue, Stats, and Settings were reviewed at the agreed desktop/tablet/mobile widths. The final Activity-panel visual spot-check was blocked when browser security denied access to the authenticated localhost origin; Activity behavior/focus is covered by component tests. The live-preview player state was not triggered against the user's connected TIDAL session.

- [x] **Step 4: Search changed frontend code for forbidden interaction patterns**

Review changed paths for `alert(`, `confirm(`, `prompt(`, non-semantic clickable containers, hidden scrollbars, missing accessible names, screen-local queue state, and animated technical metadata. Fix newly introduced matches and confirm existing flows retain visible focus.

- [x] **Step 5: Reconcile final documentation and token mapping**

Confirm `Design.md` shell and player direction matches CSS and components; `UX-CONTRACT.md` names the canonical behavior owners; scrollbar colors trace to one global stylesheet; and all shared panel/search/row components consume those tokens instead of duplicating values.

- [x] **Step 6: Inspect diff and final workspace state**

Run `rtk git diff --check`, `rtk git diff --stat`, and `rtk git status --short`. Confirm unrelated pre-existing changes in `.DS_Store`, `.claude/worktrees/agent-a9ffac2fda3444603`, `backend/downloader.py`, `backend/tests/test_downloader.py`, and the existing clickable-artists plan are not staged or overwritten.

Expected: the implementation diff contains only the UI redesign, its owned documentation/evidence, and directly related frontend tests.
