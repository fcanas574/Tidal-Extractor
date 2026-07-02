# Backend: converter.py

**Role:** Thin ffmpeg wrapper for audio format conversion.

**See:** [[Download Pipeline]] · [[Backend downloader]]

## `convert_format(input_path, output_path, target_format, bitrate=None)` → str

### Fast path
```python
if input_ext == target_format:
    return input_path    # no-op, no copy
```
E.g., FLAC source → FLAC target skips entirely.

### Conversion
```python
codec_map = { mp3: "libmp3lame", m4a: "aac", flac: "flac" }
codec = codec_map.get(target_fmt, "copy")

cmd = ["ffmpeg", "-y", "-i", input_path]
if target_fmt in ("mp3", "m4a") and bitrate:
    cmd += ["-c:a", codec, "-b:a", bitrate]
else:
    cmd += ["-c:a", codec]
cmd.append(output_path)
```

- Timeout: 120s
- Raises `RuntimeError(ffmpeg stderr)` on non-zero exit
- Returns `output_path` on success

## Usage in download pipeline

`download_track()` calls this only when the target extension differs from the source manifest's file extension:
```python
if ext != manifest.file_extension:
    final_path = await asyncio.to_thread(convert_format, tmp, final, target_format.lower())
else:
    shutil.move(tmp, final)
```

## Notes

- `bitrate` is optional and currently always passed `None` from `download_track` — the codec defaults apply (e.g., libmp3lame's default). If you want strict 320k MP3, you'd need to pass `bitrate="320k"`.
- `ffmpeg-python` is in requirements but this module uses raw subprocess for simplicity/control.
- Runs synchronously — callers wrap in `asyncio.to_thread()`.

## See Also

- [[Backend downloader]] · [[Download Pipeline]]
