# Backend: auth.py

**Role:** `AuthManager` — wraps the Tidal OAuth device-link flow and session persistence. See [[Auth Flow]] for the full protocol.

**See:** [[Auth Flow]] · [[Backend main]]

## Class: `AuthManager`

```python
session_file = Path("tidal-session.json")     # gitignored
session: Optional[tidalapi.Session] = None
_device_login = None     # OAuth login object (url, code, expires_in)
_device_future = None    # concurrent future blocking on user auth
```

## Methods

### `is_authenticated` (property)
```python
session is not None and session.check_login()
```
Swallows exceptions → returns `False`. Safe to call anytime.

### `get_status()` → dict
`{authenticated: bool, username: str | None}`. Username pulled from `session.user.username` (wrapped in try/except).

### `get_device_link()` → dict
Initiates OAuth:
```python
config = Config(quality=Quality.high_lossless)
session = tidalapi.Session(config)
login, future = session.login_oauth()    # tidalapi returns (login, future)
return { url: login.verification_uri_complete,
         code: login.user_code,
         expires_in: login.expires_in }
```
Stores `login` + `future` for the verify step.

### `wait_for_device_auth()` → bool
**Blocking.** Called in a thread (`asyncio.to_thread` in main.py):
```python
future.result()                                  # blocks until user authorizes
session.save_session_to_file(session_file)       # persist
return True
```
Returns `False` if no future or on exception.

### `load_saved_session(quality="high_lossless")` → bool
Called in lifespan on startup:
```python
quality_enum = {hi_res_lossless, high_lossless, low_320k, low_96k}.get(quality, high_lossless)
session = tidalapi.Session(Config(quality=quality_enum))
if session_file.exists():
    session.login_session_file(session_file)
    if session.check_login(): return True
# any failure → self.session = None, return False
```

### `logout()`
Deletes `tidal-session.json`, clears `session`, `_device_login`, `_device_future`.

## Quality Enum Map

```python
"hi_res_lossless" → Quality.hi_res_lossless   # ⚠️ requires PKCE
"high_lossless"   → Quality.high_lossless
"low_320k"        → Quality.low_320k
"low_96k"         → Quality.low_96k
```

## Integration with main.py

- `lifespan` calls `load_saved_session()` — if true, builds the orchestrator
- `POST /auth/device-link/verify` calls `wait_for_device_auth()` in a thread, then builds orchestrator on success
- All protected endpoints check `auth_manager.is_authenticated`

## See Also

- [[Auth Flow]] · [[Backend main]]
