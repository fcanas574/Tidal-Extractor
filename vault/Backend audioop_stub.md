# Backend: audioop_stub.py

**Role:** Compatibility shim providing the `audioop` module API for Python 3.13+, where the stdlib `audioop` was removed. Needed because **pydub** (used by wavypy) imports `audioop`.

**See:** [[Backend waveform]] · [[Gotchas & Traps]]

## The Problem

Python 3.13 removed the `audioop` stdlib module ([PEP 594](https://peps.python.org/pep-0594/) — removing "dead batteries"). However:
- `pydub` imports `audioop` at module load
- `wavypy` (the waveform submodule) imports `pydub`
- The project targets Python 3.13+

Without a shim, importing wavypy crashes with `ModuleNotFoundError: No module named 'audioop'`.

## The Solution

`audioop_stub.py` provides the functions pydub actually calls (ratecv, tomono, tostereo, etc.), implemented in pure Python / numpy. It's registered into `sys.modules` *before* pydub is imported.

## How It's Wired

In `waveform.py:_run_wavypy()`, the generated subprocess script does:
```python
sys.path.insert(0, <audioop_stub dir>)
import audioop_stub
sys.modules["audioop"]   = audioop_stub
sys.modules["pyaudioop"] = audioop_stub     # pydub also tries this alias
# NOW safe to import pydub:
import pydub
pydub.AudioSegment = FakeAudioSegment        # bypass pydub entirely
```

The stub is installed into `sys.modules` so that `import audioop` inside pydub resolves to it.

## Why Not Just `pip install audioop-lfc` or similar?

The project chose a vendored shim for:
- Zero external dependency on a third-party reimplementation
- Full control over which functions are needed
- The actual audio decoding is bypassed anyway (`FakeAudioSegment` reads via scipy), so the stub only needs to satisfy imports, not do real DSP

## Note

This is a **build/runtime dependency quirk**, not a feature. It exists solely to keep a legacy dependency (pydub via wavypy) working on modern Python. If wavypy were ever replaced or pydub dropped, this file could be removed.

## See Also

- [[Backend waveform]] · [[Gotchas & Traps]]
