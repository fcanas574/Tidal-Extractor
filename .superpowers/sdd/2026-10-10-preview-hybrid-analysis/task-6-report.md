# Task 6 implementation report

Implemented the preview API and job lifecycle for hybrid analysis.

- Preview snapshots now expose independent waveform and analysis states, the hybrid result and error, and local/provider sources while retaining the existing display fields. Completed waveforms remain available during analysis; failed or unknown analysis with a usable waveform becomes terminal `partial`.
- Preview decoding hashes the exact aligned PCM written to the single analysis WAV and reports duration from decoded samples. The WAV remains available until `AnalysisService` returns and is cleaned up on success and failure. Track-ID-only waveform cache data is ignored because it carries no audio identity.
- Analysis service creation stays lazy, startup does not provision models, shutdown closes preview jobs and the worker before closing the database, and an authenticated bodyless retry route requeues only failed/deferred analysis.
- The legacy `GET /preview/{track_id}` response still includes `stream_url`, `waveform`, `key`, `camelot`, and `bpm`; local values win and provider values are field-specific fallbacks with source labels.

The lifecycle regression cases were added first and run red: the focused preview tests reported 8 failures and 18 passes against the starting implementation. The legacy `backend/tests/test_preview_analysis.py` expectations were then updated, with parent approval, to replace track-ID-only cache reuse assertions with PCM identity assertions. A route regression now pins the legacy response fields and local-first source mapping.

Verification used the repository interpreter and required `PYTHONPATH`:

```text
rtk proxy env PYTHONPATH=/Users/felipecanas/.codex/worktrees/preview-analysis/TidalExtractor/backend/wavypy:/Users/felipecanas/.codex/worktrees/preview-analysis/TidalExtractor /Users/felipecanas/Projects/TidalExtractor/venv/bin/python -m pytest backend/tests/test_preview_jobs.py backend/tests/test_preview_routes.py backend/tests/test_waveform_stream.py -q
30 passed

rtk proxy env PYTHONPATH=/Users/felipecanas/.codex/worktrees/preview-analysis/TidalExtractor/backend/wavypy:/Users/felipecanas/.codex/worktrees/preview-analysis/TidalExtractor /Users/felipecanas/Projects/TidalExtractor/venv/bin/python -m pytest backend/tests -q
227 passed, 1 skipped
```
