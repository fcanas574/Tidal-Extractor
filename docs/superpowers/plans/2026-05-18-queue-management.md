# Queue Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add queue batch operations (clear completed, clear all, retry failed, multi-select remove/cancel) and a completed-downloads section to the Queue view.

**Architecture:** Queue-only approach. No new database tables. Three new backend batch endpoints + three new DB methods. Frontend keeps completed items in queue instead of auto-removing them, adds a collapsible completed section, header action buttons, and select mode for batch operations.

**Tech Stack:** Python (FastAPI, aiosqlite), React, TypeScript

---

### Task 1: Backend DB methods for queue batch operations

**Files:**
- Modify: `backend/models.py` (add `remove_completed`, `remove_batch`, `remove_all`)
- Test: `backend/tests/test_models.py` (add tests for new methods)

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_models.py` after the existing `test_remove_from_queue` test:

```python
@pytest.mark.asyncio
async def test_remove_completed(db):
    item1 = await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    item2 = await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )
    await db.update_queue_status(item1["id"], "complete")
    await db.update_queue_status(item2["id"], "downloading")

    removed = await db.remove_completed()
    assert removed == 1

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "2"


@pytest.mark.asyncio
async def test_remove_batch(db):
    item1 = await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    item2 = await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )
    item3 = await db.add_to_queue(
        tidal_id="3", item_type="track", title="Song C",
        artist="C", album="C", quality="high_lossless", format="FLAC",
    )

    removed = await db.remove_batch([item1["id"], item3["id"]])
    assert removed == 2

    queue = await db.get_queue()
    assert len(queue) == 1
    assert queue[0]["tidal_id"] == "2"


@pytest.mark.asyncio
async def test_remove_all(db):
    await db.add_to_queue(
        tidal_id="1", item_type="track", title="Song A",
        artist="A", album="A", quality="high_lossless", format="FLAC",
    )
    await db.add_to_queue(
        tidal_id="2", item_type="track", title="Song B",
        artist="B", album="B", quality="high_lossless", format="FLAC",
    )

    removed = await db.remove_all()
    assert removed == 2

    queue = await db.get_queue()
    assert len(queue) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_models.py -k "remove_completed or remove_batch or remove_all" -v`

Expected: FAIL with `AttributeError: 'Database' object has no attribute 'remove_completed'`

- [ ] **Step 3: Implement the three DB methods**

Add to `backend/models.py` after the existing `remove_from_queue` method (after line 91):

```python
    async def remove_completed(self) -> int:
        cursor = await self._conn.execute("DELETE FROM queue WHERE status = 'complete'")
        await self._conn.commit()
        return cursor.rowcount

    async def remove_batch(self, ids: list[int]) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._conn.execute(
            f"DELETE FROM queue WHERE id IN ({placeholders})", ids
        )
        await self._conn.commit()
        return cursor.rowcount

    async def remove_all(self) -> int:
        cursor = await self._conn.execute("DELETE FROM queue")
        await self._conn.commit()
        return cursor.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_models.py -k "remove_completed or remove_batch or remove_all" -v`

Expected: All 3 new tests PASS

- [ ] **Step 5: Run all model tests**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/test_models.py -v`

Expected: All tests PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/models.py backend/tests/test_models.py
git commit -m "feat: add remove_completed, remove_batch, remove_all DB methods"
```

---

### Task 2: Backend batch queue endpoints

**Files:**
- Modify: `backend/main.py` (add three DELETE endpoints and BatchRemoveRequest model)

- [ ] **Step 1: Add the BatchRemoveRequest model and three endpoints**

In `backend/main.py`, add after the `AddToQueueRequest` class (after line 131):

```python
class BatchRemoveRequest(BaseModel):
    ids: list[int]
```

Add after the existing `remove_from_queue` endpoint (after line 159):

```python
@app.delete("/queue/completed")
async def clear_completed():
    removed = await db.remove_completed()
    return {"removed": removed}


@app.delete("/queue/batch")
async def remove_batch(body: BatchRemoveRequest):
    removed = await db.remove_batch(body.ids)
    return {"removed": removed}


@app.delete("/queue/all")
async def clear_all():
    global orchestrator
    if orchestrator and orchestrator._running:
        orchestrator._running = False
    removed = await db.remove_all()
    return {"removed": removed}
```

- [ ] **Step 2: Verify the server starts**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -c "from backend.main import app; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add backend/main.py
git commit -m "feat: add DELETE /queue/completed, /queue/batch, /queue/all endpoints"
```

---

### Task 3: Frontend API client — add batch queue methods

**Files:**
- Modify: `frontend/src/api.ts` (add `clearCompleted`, `removeBatch`, `clearAll` to queue object)

- [ ] **Step 1: Add new queue API methods**

In `frontend/src/api.ts`, replace the existing `queue` export:

```typescript
export const queue = {
  list: () => request<QueueItem[]>('/queue'),
  add: (item: { tidal_id: string; item_type: string; title: string; artist?: string; album?: string; quality?: string; format?: string }) =>
    request<QueueItem>('/queue/add', { method: 'POST', body: JSON.stringify(item) }),
  remove: (id: number) => request<{ ok: boolean }>(`/queue/${id}`, { method: 'DELETE' }),
  removeBatch: (ids: number[]) =>
    request<{ removed: number }>('/queue/batch', { method: 'DELETE', body: JSON.stringify({ ids }) }),
  clearCompleted: () =>
    request<{ removed: number }>('/queue/completed', { method: 'DELETE' }),
  clearAll: () =>
    request<{ removed: number }>('/queue/all', { method: 'DELETE' }),
};
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/api.ts
git commit -m "feat: add removeBatch, clearCompleted, clearAll to queue API client"
```

---

### Task 4: Frontend AppContext — keep completed items in queue

**Files:**
- Modify: `frontend/src/context/AppContext.tsx` (change WS complete handler + add NavBar badge logic)

- [ ] **Step 1: Change the WS complete handler to keep items**

In `frontend/src/context/AppContext.tsx`, find the `msg.type === 'complete'` case in the reducer (around line 101). Replace:

```typescript
          queue: state.queue.filter((item) => String(item.id) !== msg.id),
```

With:

```typescript
          queue: state.queue.map((item) =>
            String(item.id) === msg.id
              ? { ...item, status: 'complete' as const, progress: 100 }
              : item
          ),
```

Also, in the `complete` toast section, remove the item-specific download toast cleanup that filtered the queue:

```typescript
          toasts: [
            ...state.toasts.filter((t) => t.id !== toastId),
```

This line is fine — it only removes the progress toast for the completed item, not the queue item. No change needed here.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/context/AppContext.tsx
git commit -m "fix: keep completed items in queue instead of auto-removing"
```

---

### Task 5: Frontend NavBar — use pending count for badge

**Files:**
- Modify: `frontend/src/components/NavBar.tsx` (change badge to count non-completed items)

- [ ] **Step 1: Update the queue count logic**

In `frontend/src/components/NavBar.tsx`, replace:

```typescript
  const activeDownloads = state.queue.filter((i) => i.status === 'downloading').length;
```

With:

```typescript
  const activeDownloads = state.queue.filter((i) => i.status === 'downloading').length;
  const pendingCount = state.queue.filter((i) => i.status !== 'complete').length;
```

Then in the JSX, replace the badge that shows `{state.queue.length}`:

```typescript
{tab.key === 'queue' && state.queue.length > 0 && (
```

With:

```typescript
{tab.key === 'queue' && pendingCount > 0 && (
```

And replace the badge content:

```typescript
{state.queue.length}
```

With:

```typescript
{pendingCount}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/components/NavBar.tsx
git commit -m "fix: nav bar queue badge shows pending count instead of total"
```

---

### Task 6: Frontend QueueView — full redesign with completed section, actions, and select mode

**Files:**
- Modify: `frontend/src/components/QueueView.tsx` (complete rewrite)

- [ ] **Step 1: Rewrite QueueView with all new features**

Replace the full contents of `frontend/src/components/QueueView.tsx` with:

```tsx
import { useState } from 'react';
import { queue } from '../api';
import { useApp } from '../context/AppContext';

const statusConfig: Record<string, { label: string; color: string; bg: string; dot: string }> = {
  queued: { label: 'Queued', color: 'var(--text-muted)', bg: 'var(--bg-surface)', dot: 'var(--text-dim)' },
  downloading: { label: 'Downloading', color: 'var(--accent-secondary)', bg: 'rgba(0, 184, 212, 0.1)', dot: 'var(--accent-secondary)' },
  complete: { label: 'Complete', color: 'var(--accent-primary)', bg: 'rgba(0, 229, 199, 0.1)', dot: 'var(--accent-primary)' },
  failed: { label: 'Failed', color: 'var(--danger)', bg: 'rgba(255, 64, 96, 0.1)', dot: 'var(--danger)' },
};

export default function QueueView() {
  const { state, dispatch } = useApp();
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [clearAllConfirm, setClearAllConfirm] = useState(false);
  const [completedCollapsed, setCompletedCollapsed] = useState(false);

  const activeItems = state.queue.filter((i) => i.status === 'downloading' || i.status === 'queued');
  const failedItems = state.queue.filter((i) => i.status === 'failed');
  const completedItems = state.queue.filter((i) => i.status === 'complete');
  const pendingItems = [...activeItems, ...failedItems];

  const hasFailed = failedItems.length > 0;
  const hasCompleted = completedItems.length > 0;

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === state.queue.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(state.queue.map((i) => i.id)));
    }
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const handleRemove = async (id: number) => {
    await queue.remove(id);
    dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: id });
  };

  const handleRetry = async (item: typeof state.queue[0]) => {
    try {
      await queue.add({
        tidal_id: item.tidal_id,
        item_type: item.item_type,
        title: item.title,
        artist: item.artist,
        album: item.album,
        quality: item.quality,
        format: item.format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `retry-${Date.now()}-${item.id}`,
          type: 'info',
          title: 'Re-added to queue',
          detail: item.title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `retry-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to retry',
          detail: item.title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const handleRetryAllFailed = async () => {
    for (const item of failedItems) {
      await handleRetry(item);
    }
  };

  const handleClearCompleted = async () => {
    try {
      await queue.clearCompleted();
      const newQueue = state.queue.filter((i) => i.status !== 'complete');
      dispatch({ type: 'SET_QUEUE', payload: newQueue });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `clear-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to clear completed',
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const handleClearAll = async () => {
    if (!clearAllConfirm) {
      setClearAllConfirm(true);
      setTimeout(() => setClearAllConfirm(false), 3000);
      return;
    }
    try {
      await queue.clearAll();
      dispatch({ type: 'SET_QUEUE', payload: [] });
      setClearAllConfirm(false);
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `clear-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to clear queue',
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const handleRemoveSelected = async () => {
    try {
      await queue.removeBatch(Array.from(selectedIds));
      const newQueue = state.queue.filter((i) => !selectedIds.has(i.id));
      dispatch({ type: 'SET_QUEUE', payload: newQueue });
      exitSelectMode();
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `batch-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to remove selected',
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const activeCount = state.queue.filter((i) => i.status === 'downloading').length;
  const queuedCount = state.queue.filter((i) => i.status === 'queued').length;

  const renderItem = (item: typeof state.queue[0], dimmed: boolean = false) => {
    const cfg = statusConfig[item.status] || statusConfig.queued;
    return (
      <div
        key={item.id}
        className="glass p-4"
        style={{ opacity: dimmed ? 0.6 : 1 }}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {selectMode && (
              <input
                type="checkbox"
                checked={selectedIds.has(item.id)}
                onChange={() => toggleSelect(item.id)}
                style={{ accentColor: 'var(--accent-primary)' }}
                className="shrink-0"
              />
            )}
            <div className="flex-1 min-w-0">
              <p
                className="text-sm font-medium truncate"
                style={{ color: dimmed ? 'var(--text-muted)' : 'var(--text-bright)' }}
              >
                {item.title}
              </p>
              <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {item.artist}
                {item.album && ` · ${item.album}`}
                {' · '}
                <span className="mono" style={{ color: 'var(--text-dim)' }}>{item.quality}</span>
                {' · '}
                <span className="mono" style={{ color: 'var(--text-dim)' }}>{item.format}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 ml-3">
            <span
              className="flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-md"
              style={{ background: cfg.bg, color: cfg.color }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: cfg.dot,
                  boxShadow: item.status === 'downloading' ? `0 0 6px ${cfg.dot}` : 'none',
                  animation: item.status === 'downloading' ? 'pulse-glow 1.5s ease-in-out infinite' : 'none',
                }}
              />
              {cfg.label}
            </span>
            {!selectMode && item.status === 'failed' && (
              <button
                onClick={() => handleRetry(item)}
                className="text-xs transition-colors font-medium"
                style={{ color: 'var(--accent-primary)' }}
              >
                Retry
              </button>
            )}
            {!selectMode && item.status !== 'complete' && (
              <button
                onClick={() => handleRemove(item.id)}
                className="text-xs transition-colors"
                style={{ color: 'var(--text-dim)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--danger)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-dim)')}
              >
                Cancel
              </button>
            )}
          </div>
        </div>

        {item.status === 'downloading' && (
          <div className="progress-track mt-3">
            <div
              className="progress-fill active"
              style={{ width: `${item.progress}%` }}
            />
          </div>
        )}

        {item.status === 'failed' && item.error && (
          <p className="text-xs mt-2" style={{ color: 'var(--danger)' }}>{item.error}</p>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-bright)' }}>
            Download Queue
          </h2>
          {state.queue.length > 0 && (
            <p className="text-xs mt-1" style={{ color: 'var(--text-dim)' }}>
              {activeCount > 0 && `${activeCount} active`}
              {activeCount > 0 && queuedCount > 0 && ' · '}
              {queuedCount > 0 && `${queuedCount} queued`}
              {hasFailed && ` · ${failedItems.length} failed`}
              {hasCompleted && ` · ${completedItems.length} complete`}
            </p>
          )}
        </div>

        {state.queue.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelectMode(!selectMode)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all duration-200"
              style={{
                color: selectMode ? 'var(--accent-primary)' : 'var(--text-dim)',
                background: selectMode ? 'var(--accent-dim)' : 'transparent',
                border: selectMode ? '1px solid rgba(0, 229, 199, 0.15)' : '1px solid transparent',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="1" y="1" width="4" height="4" rx="1" />
                <rect x="9" y="1" width="4" height="4" rx="1" />
                <rect x="1" y="9" width="4" height="4" rx="1" />
                <rect x="9" y="9" width="4" height="4" rx="1" />
              </svg>
              {selectMode ? 'Done' : 'Select'}
            </button>

            {hasFailed && !selectMode && (
              <button
                onClick={handleRetryAllFailed}
                className="text-xs px-3 py-1.5 rounded-lg transition-all duration-200"
                style={{
                  color: 'var(--accent-primary)',
                  background: 'transparent',
                  border: '1px solid rgba(0, 229, 199, 0.15)',
                }}
              >
                Retry Failed
              </button>
            )}

            {hasCompleted && !selectMode && (
              <button
                onClick={handleClearCompleted}
                className="text-xs px-3 py-1.5 rounded-lg transition-all duration-200"
                style={{
                  color: 'var(--text-dim)',
                  background: 'transparent',
                  border: '1px solid var(--glass-border)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--accent-primary)';
                  e.currentTarget.style.borderColor = 'rgba(0, 229, 199, 0.15)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--text-dim)';
                  e.currentTarget.style.borderColor = 'var(--glass-border)';
                }}
              >
                Clear Completed
              </button>
            )}

            {!selectMode && (
              <button
                onClick={handleClearAll}
                className="text-xs px-3 py-1.5 rounded-lg transition-all duration-200"
                style={{
                  color: clearAllConfirm ? 'var(--danger)' : 'var(--text-dim)',
                  background: 'transparent',
                  border: `1px solid ${clearAllConfirm ? 'rgba(255, 64, 96, 0.3)' : 'var(--glass-border)'}`,
                }}
              >
                {clearAllConfirm ? 'Confirm?' : 'Clear All'}
              </button>
            )}
          </div>
        )}
      </div>

      {state.queue.length === 0 ? (
        <div className="text-center py-24">
          <div
            className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{ background: 'var(--bg-mid)', border: '1px solid var(--glass-border)' }}
          >
            <span className="text-2xl" style={{ color: 'var(--text-dim)' }}>&#8595;</span>
          </div>
          <p className="text-sm" style={{ color: 'var(--text-dim)' }}>
            Queue is empty. Search and add tracks to download.
          </p>
        </div>
      ) : (
        <>
          {/* Active + Failed items */}
          {pendingItems.length > 0 && (
            <div className="space-y-2">
              {pendingItems.map((item) => renderItem(item))}
            </div>
          )}

          {/* Completed section */}
          {hasCompleted && (
            <div className={pendingItems.length > 0 ? 'mt-6' : ''}>
              <button
                onClick={() => setCompletedCollapsed(!completedCollapsed)}
                className="flex items-center gap-2 mb-3 cursor-pointer"
                style={{ background: 'none', border: 'none', padding: 0 }}
              >
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 10 10"
                  fill="none"
                  stroke="var(--text-dim)"
                  strokeWidth="1.5"
                  style={{
                    transform: completedCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                  }}
                >
                  <path d="M2 4l3 3 3-3" />
                </svg>
                <span
                  className="text-xs font-medium uppercase tracking-wider"
                  style={{ color: 'var(--text-dim)' }}
                >
                  Completed
                </span>
                <span
                  className="mono text-[10px] px-1.5 py-0.5 rounded"
                  style={{
                    background: 'rgba(0, 229, 199, 0.08)',
                    color: 'var(--text-dim)',
                  }}
                >
                  {completedItems.length}
                </span>
              </button>

              {!completedCollapsed && (
                <div className="space-y-2">
                  {completedItems.map((item) => renderItem(item, true))}
                </div>
              )}
            </div>
          )}

          {/* Batch action bar */}
          {selectMode && selectedIds.size > 0 && (
            <div
              className="mt-6 p-3 flex items-center justify-between"
              style={{
                background: 'rgba(0, 229, 199, 0.06)',
                border: '1px solid rgba(0, 229, 199, 0.15)',
                borderRadius: 'var(--radius)',
              }}
            >
              <div className="flex items-center gap-3">
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={selectedIds.size === state.queue.length}
                    onChange={toggleSelectAll}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  All
                </label>
                <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {selectedIds.size} selected
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRemoveSelected}
                  className="btn-primary text-xs px-3 py-1.5"
                >
                  Remove Selected
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /Users/felipecanas/Projects/TidalExtractor
git add frontend/src/components/QueueView.tsx
git commit -m "feat: redesign QueueView with completed section, batch actions, and select mode"
```

---

### Task 7: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/felipecanas/Projects/TidalExtractor && python3 -m pytest backend/tests/ -v`

Expected: All tests PASS (including new remove_completed, remove_batch, remove_all)

- [ ] **Step 2: Run frontend type check**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx tsc --noEmit`

Expected: No errors

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/felipecanas/Projects/TidalExtractor/frontend && npx vite build`

Expected: Build succeeds with no errors
