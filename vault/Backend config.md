# Backend: config.py

**Role:** `AppConfig` — YAML-backed user settings with safe defaults. Single source of truth for quality, format, and output directory.

**See:** [[Configuration]] · [[Backend main]]

## Defaults

```python
DEFAULTS = {
    "default_quality": "high_lossless",
    "default_format":  "FLAC",
    "output_dir":      "~/Music/TidalDownloads",
}
```

> ⚠️ The committed `config.yaml` overrides `output_dir` to `~/Downloads` and `default_quality` to `high_lossless`. See [[Configuration]].

## Class: `AppConfig`

```python
def __init__(config_path="config.yaml"):
    self.default_quality: str
    self.default_format:  str
    self.output_dir:      str
    self._load()                  # read file if exists, else keep defaults
```

## Methods

### `_load()`
```python
if Path(config_path).exists():
    data = yaml.safe_load(f) or {}
    self.default_quality = data.get("default_quality", self.default_quality)
    self.default_format  = data.get("default_format",  self.default_format)
    self.output_dir      = data.get("output_dir",      self.output_dir)
```
Missing keys fall back to current value (which started from DEFAULTS).

### `save()`
Writes all three fields back to `config.yaml` (creates parent dirs). Uses `default_flow_style=False` for readability.

### `update(**kwargs)`
Sets fields in-memory only (does NOT save). Used internally; `PUT /settings` calls `update()` then `save()`.

### `as_dict()` → dict
`{default_quality, default_format, output_dir}` — returned by `GET /settings`.

## Integration

- `main.py` instantiates `config = AppConfig()` at module load
- `GET /settings` → `config.as_dict()`
- `PUT /settings` → `config.update(**valid_fields); config.save()`
- `downloader.py` reads `config.output_dir` (expanded via `os.path.expanduser`)
- `main.py` lifespan calls `_cleanup_tmp_files(config.output_dir)`

## Expansion

`output_dir` is stored as-is (may contain `~`). Callers expand with `os.path.expanduser` / `Path.expanduser()` at use time, not at load time.

## See Also

- [[Configuration]] · [[Backend main]]
