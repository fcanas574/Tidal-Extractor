# Queue Management & Download History Design

**Goal:** Add queue batch operations (clear completed, clear all, retry failed, multi-select remove/cancel) and a completed-downloads section to the Queue view.

**Architecture:** Queue-only approach. No new database tables or views. Completed items stay in the queue until explicitly cleared. Retry reuses the existing `/queue/add` endpoint.

**Tech Stack:** Python (FastAPI), React, TypeScript

---

## Backend Changes

### New endpoints in `backend/main.py`

**`DELETE /queue/completed`** — Remove all queue items with status `complete`.
- Auth required
- Calls `db.remove_completed()`
- Returns `{ removed: <count> }`
- Only shown when completed items exist

**`DELETE /queue/batch`** — Remove specific queue items by ID.
- Auth required
- Accepts JSON body: `{ ids: [1, 2, 3] }`
- Calls `db.remove_batch(ids)`
- Returns `{ removed: <count> }`

**`DELETE /queue/all`** — Remove all queue items regardless of status.
- Auth required
- Stops the orchestrator if running, then calls `db.remove_all()`
- Returns `{ removed: <count> }`
- Clear All confirmation: the button text changes to "Confirm?" for 3 seconds, then reverts. A second click within that window executes the action.

### New DB methods in `backend/models.py`

- `remove_completed() -> int` — DELETE from queue where status = 'complete', return count
- `remove_batch(ids: list[int]) -> int` — DELETE from queue where id IN (ids), return count
- `remove_all() -> int` — DELETE all from queue, return count

### Retry flow

Retry does not need a new endpoint. The frontend calls `POST /queue/add` with the same `tidal_id`, `item_type`, `title`, `artist`, `album`, `quality`, and `format` from the failed item. This creates a fresh queue entry and triggers download processing.

---

## Frontend Changes

### AppContext reducer change

Currently, the WS `complete` message handler removes completed items from queue:

```typescript
queue: state.queue.filter((item) => String(item.id) !== msg.id),
```

Change to: keep the item in queue, just update its status:

```typescript
queue: state.queue.map((item) =>
  String(item.id) === msg.id
    ? { ...item, status: 'complete' as const, progress: 100 }
    : item
),
```

This ensures completed items remain visible in the queue until cleared.

### QueueView redesign

The queue view organizes items into three visual zones:

**Active zone** (top of list):
- Items with status `downloading` or `queued`
- Same card style as current, with progress bars for downloading items
- In select mode, each item gets a checkbox

**Failed items** (inline with active zone):
- Items with status `failed` appear in the active zone
- Add a "Retry" button (accent color) next to the existing "Cancel" button
- Retry calls `queue.add()` with the failed item's original parameters
- Error message shown below the item as before

**Completed zone** (bottom, collapsible):
- All items with status `complete`
- Dimmer styling (reduced opacity, muted colors)
- Under a collapsible header: `Completed <count badge>`
- Collapsed by default when there are active/failed items above
- Expanded by default when queue has only completed items
- In select mode, each completed item also gets a checkbox

**Header action buttons** (next to "Download Queue" title):

| Button | Condition | Action |
|--------|-----------|--------|
| Retry Failed | failed items exist | Calls `/queue/add` for each failed item |
| Clear Completed | completed items exist | Calls `DELETE /queue/completed` |
| Clear All | always visible | Calls `DELETE /queue/all` with confirmation |

**Select mode:**
- "Select" toggle button in the header area
- When active, checkboxes appear on all items (active, failed, completed)
- A sticky action bar appears at the bottom of the queue when items are selected
- Action bar shows: `{N} selected` + "Remove Selected" + "Cancel Selected"
- "Remove Selected" calls `DELETE /queue/batch` with the selected IDs
- "Cancel Selected" also calls `DELETE /queue/batch` (same behavior, different label for clarity)
- Select all / deselect all checkbox in the action bar
- Deactivating select mode clears all selections

### NavBar update

The queue badge in the nav bar currently shows `state.queue.length`. Since completed items now stay in queue, change to show only non-completed count:

```typescript
const pendingCount = state.queue.filter((i) => i.status !== 'complete').length;
```

The badge displays `pendingCount`, and only appears when `pendingCount > 0`.

---

## Error Handling

- Batch endpoint failures show a toast: "Failed to clear items"
- Retry failures show the same toast as any queue add failure
- Clear All shows a confirmation via toast or inline prompt before executing
- Select mode selections are cleared after batch actions complete (success or failure)

---

## Not In Scope

- Download history persistence across sessions (would require a new DB table)
- Re-download from history
- Open output folder from queue
- Keyboard shortcuts for queue management
