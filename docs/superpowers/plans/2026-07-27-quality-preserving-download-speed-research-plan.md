# Quality-Preserving Download Speed Research Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure download latency and identify safe speed improvements without reducing selected quality or weakening bitrate verification.

**Architecture:** Instrument the existing sequential download pipeline, establish a representative baseline, profile each stage, and produce a recommendation. This plan does not change production download behavior; any later optimization receives its own approved implementation plan.

**Tech Stack:** Python timing/logging, ffmpeg/ffprobe, existing downloader/converter/tagger, pytest fixtures.

## Global Constraints

- Never lower the user-selected quality to improve speed.
- Never skip or weaken ffprobe bitrate verification.
- Never skip metadata tagging or cover-art integrity checks.
- Do not enable concurrent downloads before measuring disk, network, and API behavior.
- Do not commit benchmark audio or credentials.

---

### Task 1: Define baseline measurements

**Files:**
- Create: `docs/performance/download-speed-baseline.md`
- Test: `backend/tests/test_download_timing.py`

**Interfaces:**
- Timing labels: `quality_probe`, `sample_download`, `ffprobe`, `full_download`, `conversion`, `tagging`, `cover_art`, `total`.
- Every benchmark record includes selected preset, verified bitrate, output format, file size, and pass/fail status.
- The test helper is `run_timed_download(download_callable: Callable[[], dict]) -> dict`; the callable is a fixture that executes the existing download path with no altered arguments.

- [ ] **Step 1: Write the failing timing test**

```python
def test_download_timing_contains_quality_and_integrity_fields():
    result = run_timed_download(lambda: execute_existing_download_fixture())
    assert set(result['timings']) >= {'quality_probe', 'full_download', 'ffprobe', 'total'}
    assert result['selected_quality'] == 'high_lossless'
    assert result['verified'] is True
```

- [ ] **Step 2: Run the test to verify failure**

Run: `python3 -m pytest backend/tests/test_download_timing.py -q`

Expected: FAIL because timing instrumentation does not exist.

- [ ] **Step 3: Add instrumentation only**

Wrap existing downloader stages with `time.perf_counter()` and return or log structured timing records without changing command arguments, quality selection, retry order, or concurrency.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest backend/tests/test_download_timing.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/performance/download-speed-baseline.md backend/tests/test_download_timing.py backend/downloader.py
git commit -m "perf: instrument download pipeline timings"
```

### Task 2: Measure stage-level bottlenecks

**Files:**
- Modify: `docs/performance/download-speed-baseline.md`
- Create: `docs/performance/download-speed-results.json` locally, excluded from git

- [ ] **Step 1: Measure the same track three times**

Record cold-cache and warm-cache runs for one lossless track and one HiRes track. Record network time, file size, selected preset, verified bitrate, total time, and every stage timing.

- [ ] **Step 2: Compare redundant work**

Check whether quality probing, sample downloads, full downloads, conversion, or cover-art fetches repeat requests that could safely share a connection or artifact. Do not change code while measuring.

- [ ] **Step 3: Profile ffmpeg and filesystem overhead**

Compare subprocess wall time with file write time and ffprobe time. Confirm whether temporary-file placement, conversion, or tagging dominates before considering parallelism.

- [ ] **Step 4: Document the bottleneck**

Update `docs/performance/download-speed-baseline.md` with measured numbers and a single primary hypothesis. If no stage dominates, document that result rather than proposing speculative changes.

### Task 3: Produce a safe optimization recommendation

**Files:**
- Modify: `docs/performance/download-speed-baseline.md`
- No production source files are changed by this task. If a safe target is identified, record it in the baseline document and stop for a separately approved implementation plan.

- [ ] **Step 1: Evaluate connection reuse**

Determine whether the HTTP client or tidalapi session can reuse connections without changing requested media quality or signed URL behavior.

- [ ] **Step 2: Evaluate artifact reuse**

Determine whether the sample used for quality verification can be reused by the full download path without accepting an unverified remainder. Reject the idea if it weakens verification.

- [ ] **Step 3: Evaluate bounded concurrency**

Measure one-at-a-time behavior before proposing a bounded worker count. Reject concurrency if it causes rate limits, disk contention, session races, or quality-verification failures.

- [ ] **Step 4: Write the recommendation**

The result must classify each candidate as `safe to implement`, `needs more measurement`, or `reject`, and include the exact verification commands required for any future implementation.

- [ ] **Step 5: Do not modify production behavior in this plan**

Stop after the recommendation. A later implementation must be separately approved and must include before/after verified bitrate, output checksum/metadata checks, and full backend tests.
