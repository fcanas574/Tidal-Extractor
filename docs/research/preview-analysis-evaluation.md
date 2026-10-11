# Preview analysis validation and evaluation

- Run date: 2026-10-10
- Validation base: `b78c3737430e911c0e8bae50ba15eac4fff605a5`
- Release acceptance: incomplete

## Readiness decision

Preview analysis is implemented and optional. The supported local analysis runtime
and the official Beat This! `final0` checkpoint loaded successfully on this host, and
the model produced output for generated synthetic audio. This verifies the setup and
inference path only. No authorized, manually annotated real-track set was available,
so real-track accuracy and calibration have not been measured. Rekordbox parity is
not established.

The preview analyzer requires its optional Python dependencies; beat/downbeat
inference also requires a verified local `final0` checkpoint. If a dependency or the
checkpoint is missing or invalid, analysis reports the affected component as
unavailable and preview playback remains usable. Ordinary application startup and
preview code do not provision the model: `provision_model()` is called only by the
explicit setup CLI, while runtime paths request an already verified local path. The
existing `test_app_import_never_downloads_model` test replaces `urllib.request.urlopen`
with a failure before importing `backend.main` and passed in the full backend suite.

`Ready` means the current per-result heuristics accepted the result; it is not a
measured real-track accuracy claim. Preserve `Needs review` for uncertain results
and review any estimate against the audio. The authorized 20-track evaluation and
the manual preview-path check remain incomplete. No streaming account, personal
audio, or unlicensed track was used. No audio fixture or fixture manifest was added.

## Host and model evidence

| Item | Measured result |
|---|---|
| Host | macOS, Apple Silicon (`Darwin arm64`) |
| Python | 3.13.7 |
| Node.js | 25.2.1 |
| Analysis dependencies | `beat-this==1.1.0`, `librosa==0.11.0`, `numpy==2.2.6`, `scipy==1.15.3`, `torch==2.9.1`, `torchaudio==2.9.1` |
| Lock verification | `pip check`: no broken requirements |
| Model ID | `final0` |
| Checkpoint size | 81,058,141 bytes |
| Local SHA-256 | `8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331` |

The lock in `requirements-analysis.txt` targets CPython 3.13 on macOS arm64. I
installed the base requirements and then the hash-locked analysis requirements into
an isolated venv under the ignored Task 8 scratch directory. The setup CLI was
invoked once with `TIDALEXTRACTOR_MODEL_DIR` pointed at that scratch directory; the
normal application data directory and the primary checkout's environment were left
untouched. The downloaded checkpoint passed the setup script's archive and manifest
checks, and a second local verification matched the manifest digest to the file.

To reproduce the isolated setup from the repository root on the lock's supported
host:

```sh
rtk proxy mkdir -p .superpowers/sdd/2026-10-10-preview-hybrid-analysis
rtk proxy python3 -m venv .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv
rtk proxy .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv/bin/python -m pip install -r requirements.txt
rtk proxy .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv/bin/python -m pip install --require-hashes -r requirements-analysis.txt
rtk proxy env TIDALEXTRACTOR_MODEL_DIR="$PWD/.superpowers/sdd/2026-10-10-preview-hybrid-analysis/model-cache" .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv/bin/python scripts/setup_analysis_model.py --model final0
```

The scratch venv and model directory are ignored validation artifacts. For another
OS, architecture, or Python version, regenerate the analysis hash lock for that
target before installing it.

The official setup CLI printed the Beat This! MIT notice and the upstream training
data caveat. The README retains both notices. The upstream source does not publish a
signed checkpoint digest, so the local SHA-256 detects later changes but does not
independently authenticate the first download.

## Synthetic CPU smoke

The smoke generated a 16-second, 44.1 kHz click track at 120 BPM and passed it to
the real Beat This! inference path with `device="cpu"` and two Torch threads. It
used no external audio.

| Measurement | Result |
|---|---|
| Model | `final0`, SHA-256 above |
| Inference wall time | 0.776 seconds |
| Peak process RSS | 398.2 MiB |
| Output | 120.0 BPM, 32 beat events, 30 downbeat events |
| Status | Rhythm and steady grid reported `reliable`; the grid reason said the downbeats did not meet one accepted 4/4 phase |

This is one synthetic load/inference smoke, not a real-track result or accuracy
measurement. Its CPU time and memory are not representative of a music library or
the running application's playback responsiveness.

The smoke can be repeated from the repository root after the setup above:

```sh
rtk proxy env PYTHONPATH="$PWD/backend/wavypy:$PWD" TIDALEXTRACTOR_MODEL_DIR="$PWD/.superpowers/sdd/2026-10-10-preview-hybrid-analysis/model-cache" .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv/bin/python - <<'PY'
import json
import resource
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from backend.analysis.rhythm_engine import estimate_rhythm
from backend.analysis.types import AnalysisSettings
from scripts.setup_analysis_model import get_model_path

torch.set_num_threads(2)
model_path = get_model_path("final0")
manifest = json.loads(model_path.with_name("final0.manifest.json").read_text())
sample_rate, duration = 44100, 16.0
samples = np.zeros(round(sample_rate * duration), dtype=np.float32)
click_samples = round(sample_rate * 0.08)
click_t = np.arange(click_samples, dtype=np.float32) / sample_rate
click = 0.45 * np.exp(-click_t / 0.012) * (
    np.sin(2 * np.pi * 62 * click_t) + 0.35 * np.sin(2 * np.pi * 1760 * click_t)
)
for start_seconds in np.arange(0.25, duration, 0.5):
    start = round(start_seconds * sample_rate)
    samples[start : start + click_samples] += click
audio_path = Path(".superpowers/sdd/2026-10-10-preview-hybrid-analysis/synthetic-120bpm.wav")
sf.write(audio_path, samples, sample_rate, subtype="PCM_16")
started = time.perf_counter()
result = estimate_rhythm(
    str(audio_path), duration, model_path, "final0", manifest["sha256"], AnalysisSettings()
)
print(f"elapsed_seconds={time.perf_counter() - started:.3f}")
print(f"peak_process_rss_mib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024):.1f}")
print(f"status={result.status}; grid_status={result.grid.status}; bpm={result.bpm}")
print(f"beats={len(result.beats)}; downbeats={len(result.downbeats)}; phase_reason={result.grid.reason}")
PY
```

## Automated checks

| Check | Result |
|---|---|
| Backend: `rtk proxy env PYTHONPATH="$PWD/backend/wavypy:$PWD" .superpowers/sdd/2026-10-10-preview-hybrid-analysis/task8-venv/bin/python -m pytest backend/tests/ -q` | 233 passed, 1 skipped, 3 warnings in 30.93 seconds |
| Frontend: `rtk npm --prefix frontend test -- --run` | 18 test files passed; 114 tests passed |
| Frontend: `rtk npm --prefix frontend run build` | TypeScript check and Vite 6.4.2 production build passed in 2.35 seconds |
| Model download guard | `test_app_import_never_downloads_model` passed; runtime call-site inspection found no implicit provisioning call |

If frontend dependencies are absent in a fresh checkout, install the locked packages
with `rtk npm --prefix frontend ci` before running its tests and build.

The skipped backend test is the existing async `backend/tests/test_freqblog_api.py::test_freqblog_api`, which the current pytest configuration does not run. Backend warnings included a Starlette deprecation and the existing unawaited-coroutine warning in `test_stream_route_returns_before_analyzer`. Frontend output included Node local-storage-path warnings and React `act(...)` warnings in existing tests.

For the backend command, `PYTHONPATH` includes the worktree's `backend/wavypy`
helper directory and repository root. The isolated venv was created only for this
validation run; the command records its path so the setup can be repeated in the
same managed worktree.

## Evaluation status and remaining acceptance work

| Evaluation item | Status |
|---|---|
| Authorized/licensed 20-track set | Not supplied; not run |
| Required split | Not run: 14 electronic, 3 reggaeton, 3 pop |
| Manual key and relative-key annotations | Not available; errors not measured |
| Strict BPM and half/double-tempo errors | Not measured on real tracks |
| Downbeat phase, beat timing, and early/middle/late drift | Not measured on real tracks |
| Real-track CPU time and peak memory | Not measured |
| Manual preview playback, waveform/polling, marker seeking, retry, cache reuse, and stale-track switch | Incomplete; no authorized local preview source was available |
| Rekordbox comparison | Not run; parity is not established |

When an authorized evaluation set is available, keep its final labels separate from
any tuning subset. Record a pseudonymous track ID, documented source permission,
manual key and relative key, tempo, beat and downbeat annotations, and early/middle/
late checks. For each track, report key/relative-key errors, strict BPM error,
half/double-tempo errors, downbeat phase agreement, beat timing, split drift, CPU
time, and peak memory. Treat Rekordbox exports as comparison references rather than
automatic ground truth. Do not commit personal or streaming-service audio.

The current per-result engineering criteria are:

- A steady grid needs at least 32 usable beats spanning at least half the decoded
  duration, a 95th-percentile timing residual no greater than 35 ms, and an
  early/late median residual difference no greater than 40 ms.
- A 4/4 bar phase needs at least eight grid-aligned downbeats and at least 90%
  agreement on one beat phase modulo four within 50 ms. A steady beat grid can still
  be useful when no bar phase is accepted.
- A key is not reliable below -70 dBFS RMS or a pitch-class coefficient of variation
  below 0.05. A top-two profile gap below 0.10, segment-winner agreement below 60%, or
  fewer than three usable windows requires review.

These thresholds describe the implemented component heuristics; the single
synthetic smoke does not validate their behavior on genres or establish an overall
acceptance rate. Complete the authorized 20-track evaluation and manual preview
check before treating release acceptance as complete.
