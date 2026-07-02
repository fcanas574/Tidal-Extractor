# Configuration

How TidalExtractor is configured: YAML settings, env vars, and the settings UI.

**See:** [[Backend config]] · [[Development Setup]] · [[Components]]

## `config.yaml` (project root)

The committed file:
```yaml
default_format: FLAC
default_quality: high_lossless
output_dir: ~/Downloads
```

> ⚠️ Note: `output_dir` here is `~/Downloads`, but the code default in `AppConfig.DEFAULTS` is `~/Music/TidalDownloads`. The committed `config.yaml` overrides it. Edited in-place by `PUT /settings`.

### Fields

| Field | Values | Code Default | Committed Value |
|-------|--------|--------------|-----------------|
| `default_quality` | `hi_res_lossless`, `high_lossless`, `low_320k`, `low_96k` | `high_lossless` | `high_lossless` |
| `default_format` | `FLAC`, `MP3`, `M4A` | `FLAC` | `FLAC` |
| `output_dir` | any path (supports `~`) | `~/Music/TidalDownloads` | `~/Downloads` |

`output_dir` is stored unexpanded; callers expand via `os.path.expanduser` at use time.

## `.env` (project root, gitignored)

```
FREQBLOG_API_KEY=<your-key>
```

Loaded by `backend/freqblog.py` via `python-dotenv` from `Path(__file__).parent.parent / ".env"`. If absent, FreqBlog lookups are skipped (local librosa analysis is the only key-detection path).

## `tidal-session.json` (project root, gitignored)

Persisted Tidal OAuth session. Created on successful device-link auth, loaded on startup. Deleted on logout. See [[Auth Flow]].

## Settings Panel (UI)

Accessible via the gear icon in `NavBar`. Slide-out drawer (`SettingsPanel.tsx`):
- **Default Quality** dropdown
- **Default Format** dropdown
- **Output Directory** text input

Commits via `PUT /settings` → `AppConfig.update()` + `save()`.

## Frontend Initial State Note

`AppContext.tsx` initial `settings.output_dir` is `~/Music/TidalDownloads` (the code default). On mount, `settings.get()` overwrites with the actual server value. The transient mismatch is harmless but worth knowing if you see the default briefly.

## Quality Preset ↔ OAuth

```
hi_res_lossless  → requires PKCE-enabled OAuth
high_lossless    → standard BTS manifest
low_320k, low_96k → standard BTS manifest
```

If you want HiRes, the Tidal OAuth must be PKCE-enabled (a tidalapi config concern). See [[Gotchas & Traps]].

## CORS

```python
allow_origins = ["http://localhost:3000", "http://localhost:5173"]
```
Configured in `main.py`. Both Vite default ports covered.

## See Also

- [[Backend config]] · [[Development Setup]] · [[Auth Flow]] · [[Gotchas & Traps]]
