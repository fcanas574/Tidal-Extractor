# TidalExtractor frontend UI/UX rework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rework the TidalExtractor frontend into a responsive, music-first editorial workspace while making queue progress and notifications reliable during WebSocket interruptions.

**Architecture:** Keep the existing React Context + reducer and REST/WebSocket APIs as the foundation. Add an integer per-queue-item revision and client freshness metadata so REST snapshots and realtime events reconcile deterministically. Render persistent download activity from queue state, and reserve bounded toasts for discrete events. Apply the approved visual system through shared CSS primitives and incremental component updates.

**Tech Stack:** React 18, TypeScript, Context + `useReducer`, Vite, Tailwind CSS, CSS custom properties, native WebSocket, Vitest, Testing Library, FastAPI, aiosqlite, SQLite.

---

## Global constraints

- Follow the approved design in `docs/superpowers/specs/2026-09-13-frontend-ui-ux-rework-design.md`.
- The design passed the required `multi-agent-brainstorming` review with disposition `APPROVED`.
- Use `@subagent-driven-development` when executing this plan in the current session: one implementer per task, then spec review and code-quality review before the next task.
- Preserve `.graphifyignore`, `graphify-out/`, `.env`, runtime databases, and unrelated local changes. Never reset or clean the worktree broadly.
- Keep the current English interface and all existing download, quality, metadata, DJ filter, preview, history, and stats capabilities.
- Do not add a component library, animation package, analytics service, or second state library.
- Use `rtk` before shell commands in this repository.
- Each task ends with focused verification and a bounded commit containing only its owned files.

## Task 1: Add an exact queue revision contract

**Files:**

- Modify: `backend/models.py` — queue schema, migration, `add_to_queue`, `get_queue`, and queue update methods.
- Modify: `backend/downloader.py` — progress, completion, and failure WebSocket payloads.
- Modify: `frontend/src/api.ts` — `QueueItem.revision` and typed WebSocket revision field.
- Create: `backend/tests/test_queue_revision.py`.
- Extend: `backend/tests/test_models.py` only if an existing fixture is the clearest place for migration coverage.

**Step 1: Write failing revision tests**

Create tests that prove:

```python
@pytest.mark.asyncio
async def test_new_queue_item_starts_with_revision(db):
    item = await db.add_to_queue("123", "track", "Song", "Artist", "Album", "high_lossless", "FLAC")
    assert item["revision"] == 1


@pytest.mark.asyncio
async def test_queue_mutation_increments_revision(db):
    item = await db.add_to_queue("123", "track", "Song", "Artist", "Album", "high_lossless", "FLAC")
    changed = await db.update_queue_status(item["id"], "downloading", progress=25.0)
    assert changed["revision"] == 2
    assert changed["progress"] == 25.0


@pytest.mark.asyncio
async def test_existing_queue_schema_gets_revision_column(tmp_path):
    # Create a legacy queue table without revision, initialize Database, and
    # assert existing rows remain readable with revision 0.
    ...
```

The migration test must use the same database fixture pattern already present
in `backend/tests/test_models.py`. Add a test for an unexpected migration
failure only if the current database wrapper allows deterministic injection;
the implementation must not silently swallow that failure.

**Step 2: Run the focused tests and verify failure**

Run:

```text
rtk python -m pytest backend/tests/test_queue_revision.py -q
```

Expected: FAIL because queue rows do not expose `revision` yet.

**Step 3: Implement the additive schema and migration**

In `backend/models.py`:

- Add `revision INTEGER NOT NULL DEFAULT 0` to the queue `CREATE TABLE` block.
- During `init()`, inspect `PRAGMA table_info(queue)` and add the column only
  when it is absent. Do not catch every exception; only the already-present
  column case is non-fatal. Let unexpected schema errors stop initialization.
- Insert new queue rows with `revision = 1`.
- Add `get_queue_item(item_id)` returning one dict or `None`.
- Change `update_queue_status(...)` to set `revision = revision + 1`, commit,
  and return the updated row. Existing callers that ignore the return value stay
  compatible.

The resulting update contract is:

```python
async def update_queue_status(item_id, status, error=None, progress=None) -> dict | None:
    # update status/error/progress and increment revision atomically
    # return the row after commit
```

**Step 4: Include revisions in realtime messages and TypeScript types**

In `backend/downloader.py`, capture the returned row after each progress,
completion, and failure mutation and include `revision` in the corresponding
WebSocket payload. Preserve the existing payload fields and the return type of
`download_track()` so current downloader tests remain valid.

In `frontend/src/api.ts`, add:

```ts
export interface QueueItem {
  // existing fields...
  revision: number;
}

export interface WsMessage {
  type: 'progress' | 'quality' | 'complete' | 'error' | 'queue_update';
  id: string;
  revision?: number;
  [key: string]: unknown;
}
```

**Step 5: Run backend regression tests**

Run:

```text
rtk python -m pytest backend/tests/test_queue_revision.py backend/tests/test_models.py backend/tests/test_downloader.py -q
```

Expected: PASS.

**Step 6: Commit the queue contract**

```text
rtk git add backend/models.py backend/downloader.py frontend/src/api.ts backend/tests/test_queue_revision.py backend/tests/test_models.py backend/tests/test_downloader.py
rtk git commit -m "fix: order queue updates with item revisions"
```

## Task 2: Reconcile queue state and polling without regressions

**Files:**

- Modify: `frontend/src/context/AppContext.tsx` — canonical queue merge, freshness metadata, activity panel state, and progress/toast behavior.
- Modify: `frontend/src/App.tsx` — active-work polling and single-flight guard.
- Create: `frontend/src/context/AppContext.test.tsx`.
- Create: `frontend/src/App.test.tsx` only if the polling effect cannot be covered cleanly through a small test harness.

**Step 1: Write failing reducer/provider tests**

Use a small `AppProvider` harness with a test component that dispatches actions
and exposes selected state. Keep the reducer private. Cover:

- A REST item with a lower revision cannot replace a newer item.
- A higher revision replaces the older item.
- A progress event cannot reduce visible progress.
- A progress event updates `lastProgressAt` and does not add a toast.
- Completion and failure create one terminal toast after removing active state.
- A second terminal event for the same revision does not duplicate the toast.
- A new database queue id for the same `tidal_id` remains a separate work item.

**Step 2: Run the focused frontend test and verify failure**

Run:

```text
rtk npm test -- --run src/context/AppContext.test.tsx
```

Expected: FAIL because queue freshness metadata and merge behavior do not exist.

**Step 3: Add client freshness state and merge rules**

Extend `AppState` with the minimum metadata required by the design:

```ts
interface QueueMeta {
  revision: number;
  lastProgressAt: number | null;
}

queueMeta: Record<number, QueueMeta>;
activityPanelOpen: boolean;
```

Implement the merge inside `AppContext.tsx`:

- `SET_QUEUE` merges by database `id` instead of replacing blindly.
- Compare `revision` before applying a server item; use the current item when
  the incoming revision is older.
- For legacy revision `0`, preserve the greater progress and terminal state
  rather than trusting arrival order.
- Seed `lastProgressAt` when a downloading item is first observed and update it
  only when progress advances.
- `UPDATE_QUEUE_ITEM` uses the same merge rule as `SET_QUEUE`.
- `WS_MESSAGE.progress` updates the queue and freshness metadata only. It never
  creates or updates a progress toast.
- `WS_MESSAGE.complete` and `WS_MESSAGE.error` apply only when their revision is
  current, then create one terminal toast keyed by queue id and event type.
- Add `TOGGLE_ACTIVITY_PANEL` or equivalent action without creating a second
  download state store.

**Step 4: Make queue polling active-work based and single-flight**

In `App.tsx`:

- Keep the initial settings and queue fetch.
- Replace the `state.wsConnected` polling condition with a check for queued or
  downloading items.
- Use a `useRef<boolean>` in-flight guard. A five-second tick returns while a
  prior `queue.list()` request is pending; clear the guard in `finally`.
- Poll during WebSocket disconnection while active work exists.
- Dispatch the merged `SET_QUEUE` response and do not clear optimistic state
  through unconditional replacement.

**Step 5: Run focused tests and build**

Run:

```text
rtk npm test -- --run src/context/AppContext.test.tsx
rtk npm run build
```

Expected: PASS and a clean TypeScript/Vite build.

**Step 6: Commit canonical queue reconciliation**

```text
rtk git add frontend/src/context/AppContext.tsx frontend/src/App.tsx frontend/src/context/AppContext.test.tsx frontend/src/App.test.tsx
rtk git commit -m "fix: reconcile queue state across realtime updates"
```

## Task 3: Make WebSocket reconnect lifecycle safe

**Files:**

- Modify: `frontend/src/hooks/useWebSocket.ts`.
- Create: `frontend/src/hooks/useWebSocket.test.ts`.

**Step 1: Write failing lifecycle tests**

Mock `global.WebSocket` with controllable `onopen`, `onclose`, `onerror`, and
`onmessage` handlers. Test that:

- `onopen` dispatches connected.
- `onclose` dispatches disconnected and schedules one reconnect.
- Unmounting before the delay prevents the reconnect callback from creating a
  new socket.
- Replacing a socket does not leave two active reconnect timers.

**Step 2: Run the focused test and verify failure**

```text
rtk npm test -- --run src/hooks/useWebSocket.test.ts
```

Expected: FAIL because the reconnect timeout is not retained or cancelled.

**Step 3: Implement cancellable reconnect**

Keep a `reconnectTimerRef` and a `disposedRef`. On cleanup, mark the hook
disposed, clear the timer, and close the current socket. `connect()` must return
without opening a socket after disposal. Clear a pending timer before scheduling
another one. Preserve the existing callback ref so message handlers do not
reconnect on every render.

**Step 4: Run the test and commit**

```text
rtk npm test -- --run src/hooks/useWebSocket.test.ts
rtk git add frontend/src/hooks/useWebSocket.ts frontend/src/hooks/useWebSocket.test.ts
rtk git commit -m "fix: clean up websocket reconnect timers"
```

Expected: PASS.

## Task 4: Add persistent download activity and bounded toasts

**Files:**

- Create: `frontend/src/components/DownloadActivityPanel.tsx`.
- Create: `frontend/src/components/DownloadActivityPanel.test.tsx`.
- Modify: `frontend/src/components/ToastContainer.tsx`.
- Create: `frontend/src/components/ToastContainer.test.tsx`.
- Modify: `frontend/src/components/NavBar.tsx` — activity trigger and count.
- Modify: `frontend/src/App.tsx` — mount the activity panel.
- Modify: `frontend/src/components/QueueView.tsx` — reuse activity status and cancellation semantics.
- Modify: `frontend/src/index.css` — activity panel, sheet, focus, and safe-area rules if not already covered by Task 5.

**Step 1: Write failing activity/toast tests**

Cover:

- Active queue items render in the activity panel with progress and status.
- `reconnecting` appears when active work exists and WebSocket is disconnected.
- `stale` appears only after an observed progress timestamp is older than 20
  seconds.
- An active download shows inline `Cancel download` and `Keep downloading`
  choices before calling `queue.remove`.
- Toasts show at most three visible items, always expose a close button, pause
  their timer on hover/focus, and use the correct live-region semantics.
- Progress events are absent from the toast list.

**Step 2: Run focused tests and verify failure**

```text
rtk npm test -- --run src/components/DownloadActivityPanel.test.tsx src/components/ToastContainer.test.tsx
```

Expected: FAIL because the panel and bounded behavior do not exist.

**Step 3: Implement the activity panel**

The panel reads only `state.queue`, `state.queueMeta`, `state.wsConnected`, and
the activity-open state. Derive display status without changing
`QueueItem.status`:

```ts
type ActivityStatus =
  | 'queued'
  | 'downloading'
  | 'reconnecting'
  | 'stale'
  | 'complete'
  | 'failed';
```

Use a one-second local refresh only while active work exists so stale status can
appear without changing the queue reducer. Keep completed work collapsed and
surface failed items with retry. Use the existing `queue.remove` endpoint for
confirmed cancellation and update local state after success.

**Step 4: Implement toast lifecycle**

In `ToastContainer.tsx`:

- Keep terminal and discrete toasts only; do not add a new progress path.
- Render the latest three visible toasts and keep terminal errors ahead of
  informational messages when capacity is reached.
- Always render a close button for auto-dismissable items.
- Pause and resume the timer on pointer enter/leave and focus/blur.
- Apply the real exit transition before dispatching removal, or use a short
  local exiting state so removal is not an abrupt unmount.
- Use `role="status"` for routine updates and `role="alert"` for failures.

**Step 5: Integrate desktop and mobile behavior**

Add an activity button to `NavBar` with `aria-expanded` and `aria-controls`.
Mount the panel beside main content on desktop. Below 768px, use the approved
bottom-sheet rules, keep the player compact while the sheet is open, reserve
the safe area, and prevent both sheets from opening at once.

**Step 6: Run focused tests and commit**

```text
rtk npm test -- --run src/components/DownloadActivityPanel.test.tsx src/components/ToastContainer.test.tsx
rtk npm run build
rtk git add frontend/src/components/DownloadActivityPanel.tsx frontend/src/components/DownloadActivityPanel.test.tsx frontend/src/components/ToastContainer.tsx frontend/src/components/ToastContainer.test.tsx frontend/src/components/NavBar.tsx frontend/src/App.tsx frontend/src/components/QueueView.tsx frontend/src/index.css
rtk git commit -m "feat: add persistent download activity feedback"
```

Expected: PASS and a clean build.

## Task 5: Establish the visual system and app shell

**Files:**

- Modify: `frontend/src/index.css` — tokens, system fonts, surfaces, controls, focus, motion, responsive rules, and safe-area spacing.
- Modify: `frontend/src/App.tsx` — shell layout and content offsets.
- Modify: `frontend/src/components/NavBar.tsx` — semantic navigation and responsive controls.
- Create: `frontend/src/components/NavBar.test.tsx`.

**Step 1: Write the shell semantics test**

Assert that the navigation exposes visible labels, `aria-current` for the
active tab, an accessible Settings control, and an accessible activity control.

**Step 2: Run it and verify the current implementation exposes gaps**

```text
rtk npm test -- --run src/components/NavBar.test.tsx
```

Expected: FAIL for missing semantic attributes or controls.

**Step 3: Replace global styling with the approved minimum token system**

In `index.css`:

- Replace the remote Google font import with local system UI and monospaced
  fallback stacks to keep the local app usable offline.
- Add Obsidian, Graphite, Slate, Porcelain, Silver, and Mint tokens from the
  spec, plus readable success, warning, and danger state colors.
- Make glass selective; use solid surfaces for result and queue rows.
- Consolidate shared input, button, badge, progress, focus, and surface rules.
- Add `@media (prefers-reduced-motion: reduce)` to remove transform-heavy
  animation, shimmer, pulse, and decorative movement.
- Add the 768px mobile rules, `env(safe-area-inset-bottom)`, sheet stacking,
  and player/content spacing.
- Replace or stop using malformed text glyph icons in favor of inline SVG or
  safe text.

**Step 4: Update shell behavior**

Keep the four existing areas and Settings, but use the new hierarchy. At mobile
width, allow primary navigation to scroll horizontally, make the Settings
surface full width, and ensure fixed elements do not hide the final actionable
row.

**Step 5: Run tests/build and commit**

```text
rtk npm test -- --run src/components/NavBar.test.tsx
rtk npm run build
rtk git add frontend/src/index.css frontend/src/App.tsx frontend/src/components/NavBar.tsx frontend/src/components/NavBar.test.tsx
rtk git commit -m "style: establish editorial workspace visual system"
```

Expected: PASS and a clean build.

## Task 6: Rework SearchView and ArtistView

**Files:**

- Modify: `frontend/src/components/SearchView.tsx`.
- Modify: `frontend/src/components/ArtistView.tsx`.
- Create: `frontend/src/components/SearchView.test.tsx`.
- Modify: `frontend/src/index.css` only for shared result/filter rules that do not belong in Task 5.

**Step 1: Write focused behavior tests**

Mock `search.query`, `resolve.url`, and queue actions. Cover:

- Short search/link placeholder and visible URL-detected state.
- `Refine` opens and closes DJ filters without changing query semantics.
- Active filters render as removable chips and `Clear filters` restores the
  unfiltered state.
- Track `Load More` keeps the existing offset/limit behavior.
- Empty query, filter-empty, partial, and request-error states show distinct
  next actions while preserving the query.
- Download remains the primary action and preview remains secondary.

**Step 2: Run tests and verify failure**

```text
rtk npm test -- --run src/components/SearchView.test.tsx
```

Expected: FAIL because the current view uses direct compact controls, generic
empty copy, and does not expose the new refinement/state structure.

**Step 3: Implement the search surface**

- Keep the single input for text and Tidal URLs.
- Move the long syntax hint into helper text.
- Use the segmented type control and a collapsible `Refine` area.
- Show active filters as chips with keyboard-accessible removal.
- Keep genre-only search, current track pagination, and returned album/playlist
  semantics unchanged.
- Use music rows with the shared cover/title/metadata/action hierarchy and
  accessible labels.
- Add skeleton rows matching result geometry and action-oriented empty/error
  states.

**Step 4: Update ArtistView and run checks**

Give resolved artists a clear return context, artwork header, top tracks, and
album grid using the same row/action primitives. Do not add new artist data
requests.

```text
rtk npm test -- --run src/components/SearchView.test.tsx
rtk npm run build
rtk git add frontend/src/components/SearchView.tsx frontend/src/components/ArtistView.tsx frontend/src/components/SearchView.test.tsx frontend/src/index.css
rtk git commit -m "style: refine music search and discovery flows"
```

Expected: PASS and a clean build.

## Task 7: Rework QueueView and secondary surfaces

**Files:**

- Modify: `frontend/src/components/QueueView.tsx`.
- Modify: `frontend/src/components/HistoryView.tsx`.
- Modify: `frontend/src/components/StatsView.tsx`.
- Modify: `frontend/src/components/SettingsPanel.tsx`.
- Modify: `frontend/src/components/AuthGate.tsx`.
- Create: `frontend/src/components/QueueView.test.tsx`.
- Create: `frontend/src/components/SettingsPanel.test.tsx`.

**Step 1: Write focused component tests**

Cover:

- Queue grouping and collapsed completed section.
- Explicit active cancellation confirmation and keep/cancel actions.
- Retry and bulk actions remain available with accessible labels.
- Settings save failure preserves edited values and shows Retry.
- Settings drawer exposes dialog semantics, Escape, click-away, and focusable
  close control.
- Auth exposes one clear connection action and explicit waiting/error states.

**Step 2: Run tests and verify failure**

```text
rtk npm test -- --run src/components/QueueView.test.tsx src/components/SettingsPanel.test.tsx
```

Expected: FAIL for missing confirmation, error recovery, and semantic drawer
behavior.

**Step 3: Implement QueueView**

Align rows with SearchView and the activity panel. Keep the canonical queue
state and existing endpoints. Use direct cancel for queued items, inline
confirmation for active downloads, explicit `Clear completed` and `Clear all`
labels, and a contextual bulk-action toolbar. Keep completed items collapsed by
default.

**Step 4: Implement History, Stats, Settings, and Auth presentation**

- History becomes a readable download list with re-download as the main action.
- Stats becomes a calm summary of tracks, storage, and quality distribution.
- Settings groups Account, Download defaults, Preview, and Output. Track dirty
  state, preserve edits on failure, and show retry beside the save action.
- Auth progressively reveals device-link details and distinguishes checking,
  waiting, success, and failure.

**Step 5: Run tests/build and commit**

```text
rtk npm test -- --run src/components/QueueView.test.tsx src/components/SettingsPanel.test.tsx
rtk npm run build
rtk git add frontend/src/components/QueueView.tsx frontend/src/components/HistoryView.tsx frontend/src/components/StatsView.tsx frontend/src/components/SettingsPanel.tsx frontend/src/components/AuthGate.tsx frontend/src/components/QueueView.test.tsx frontend/src/components/SettingsPanel.test.tsx
rtk git commit -m "style: refine queue settings and library surfaces"
```

Expected: PASS and a clean build.

## Task 8: Refine the preview player without regressing its fast lifecycle

**Files:**

- Modify: `frontend/src/components/AudioPlayerFooter.tsx`.
- Extend: `frontend/src/components/AudioPlayerFooter.test.tsx` only for newly introduced accessible labels or compact mobile behavior.
- Modify: `frontend/src/App.tsx` only if player/activity stacking requires a shell class adjustment.

**Step 1: Add failing accessibility/mobile assertions**

Cover accessible labels for play/pause, seek/waveform, close, and the visible
track identity. Preserve existing tests for fast audio start, metadata polling,
stale preview protection, retry, terminal metadata failure, and abort on unmount.

**Step 2: Implement the compact player treatment**

Keep the current streaming and waveform logic. Update only presentation and
semantics:

- Maintain artwork, title, artist, play/pause, seek, waveform, and key/Camelot.
- Use the shared surface and focus rules.
- Collapse to a one-line mobile bar and expand without covering content.
- Keep the player below an open activity sheet and reserve safe-area spacing.
- Respect reduced motion and avoid reintroducing noisy waveform effects.

**Step 3: Run player tests/build and commit**

```text
rtk npm test -- --run src/components/AudioPlayerFooter.test.tsx
rtk npm run build
rtk git add frontend/src/components/AudioPlayerFooter.tsx frontend/src/components/AudioPlayerFooter.test.tsx frontend/src/App.tsx
rtk git commit -m "style: polish responsive preview player"
```

Expected: PASS and a clean build.

## Task 9: Full verification and handoff

**Files:**

- Modify: `docs/superpowers/specs/2026-09-13-frontend-ui-ux-rework-design.md` only if implementation exposes a verified design correction.
- Create: `handoff/Session-2026-09-13-frontend-ui-ux-rework.md` with verified changes, tests, known limits, and follow-up ceilings.

**Step 1: Run the complete automated gates**

```text
rtk python -m pytest backend/tests/ -q
rtk npm test -- --run
rtk npm run build
rtk git diff --check
```

Expected: all tests pass, the build succeeds, and `git diff --check` is clean.

**Step 2: Run the manual visual and interaction checklist**

With the app running, verify at desktop and mobile widths:

1. Search text, Tidal URL resolution, DJ refinement, active chips, Load More,
   result actions, empty states, and ArtistView return context.
2. Add several tracks, observe one persistent activity state per work item,
   progress without progress toasts, terminal success/error toasts, and active
   cancellation confirmation.
3. Disconnect WebSocket during an active download; confirm reconnecting state,
   continued polling, stale state after the threshold, and correct recovery.
4. Open Settings and activity on mobile; confirm only one sheet is open, the
   player remains accessible, and safe-area spacing keeps actions visible.
5. Exercise keyboard focus, Escape, drawer close, live status messages, and
   `prefers-reduced-motion`.
6. Confirm a queue with more than 50 items remains usable and record whether
   the documented 500-item rendering ceiling is approached.

**Step 3: Review the final diff and handoff**

Run:

```text
rtk git status --short
rtk git diff --stat
rtk git diff --check
```

Confirm `.env`, runtime databases, `.graphifyignore`, and `graphify-out/` are
not included in commits. Write the handoff with the final commit list, test
results, manual checklist results, and any measured limitation.

**Step 4: Commit the handoff if it contains verified results**

```text
rtk git add handoff/Session-2026-09-13-frontend-ui-ux-rework.md docs/superpowers/specs/2026-09-13-frontend-ui-ux-rework-design.md
rtk git commit -m "docs: record frontend UI UX rework verification"
```

Do not change the spec merely to record unverified future ideas.
