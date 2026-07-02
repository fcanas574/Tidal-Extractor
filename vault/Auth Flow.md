# Auth Flow

Tidal OAuth **device-link flow** with local session persistence. Single-user, single-account.

## Backend (`auth.py` — `AuthManager`)

### State
```python
session_file = "tidal-session.json"   # Path, gitignored
session: Optional[tidalapi.Session]
_device_login     # OAuth login object
_device_future    # concurrent future for auth completion
```

### `is_authenticated`
Returns `session is not None and session.check_login()`. Swallows exceptions → `False`.

## Device-Link Flow

### 1. `POST /auth/device-link` → `get_device_link()`
```python
config = Config(quality=Quality.high_lossless)
session = tidalapi.Session(config)
login, future = session.login_oauth()    # non-blocking, returns future
return { url, code, expires_in }         # verification_uri_complete, user_code
```

### 2. Frontend displays URL + code (`AuthGate.tsx`)
User visits `verification_uri_complete` in a browser, authorizes the app on Tidal.

### 3. `POST /auth/device-link/verify` → `wait_for_device_auth()` (in thread)
```python
future.result()                          # blocks until user completes auth
session.save_session_to_file(session_file)  # persist tidal-session.json
```
On success, constructs the `DownloadOrchestrator` and binds the session. Returns `{authenticated: true}`. On failure → 401.

## Session Persistence

### `load_saved_session(quality)` — called in lifespan on startup
```python
session = tidalapi.Session(Config(quality=...))
if session_file.exists():
    session.login_session_file(session_file)
    if session.check_login():
        return True
# on any failure: self.session = None, return False
```

If a valid `tidal-session.json` exists, the app boots already authenticated — no user interaction needed. The orchestrator is constructed and bound in `lifespan`.

### `logout()`
Deletes `tidal-session.json`, clears session + login state.

## Quality Mapping

```python
{
  "hi_res_lossless": Quality.hi_res_lossless,   # ⚠️ requires PKCE auth
  "high_lossless":   Quality.high_lossless,
  "low_320k":        Quality.low_320k,
  "low_96k":         Quality.low_96k,
}
```

> ⚠️ **HiRes Lossless requires PKCE-enabled OAuth.** LOSSLESS and below use the standard BTS manifest. HiRes uses a different manifest type. See [[Gotchas & Traps]].

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/device-link` | Start flow, get URL + code |
| POST | `/auth/device-link/verify` | Block until user authorizes |
| GET | `/auth/status` | `{authenticated, username}` |
| POST | `/auth/logout` | Clear session |

## Frontend

`AuthGate.tsx` wraps the entire app. If `!state.auth.authenticated`, it renders the device-link UI instead of the main app. On successful verify, dispatches `SET_AUTH`.

## See Also

- [[Backend auth]] · [[Components]] · [[System Design]]
