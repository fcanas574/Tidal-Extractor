# Frontend: vite.config.ts

**Role:** Vite dev-server + build configuration. Defines the dev port and the proxy that lets the frontend talk to the backend on a different port.

**See:** [[Realtime Updates]] · [[Development Setup]]

## Config

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

## The `/api` Proxy

The frontend `api.ts` uses `BASE = '/api'`, so every fetch goes to `localhost:3000/api/...`. Vite proxies these to `localhost:8000/...` (stripping the `/api` prefix):

| Frontend call | Proxied to |
|---------------|------------|
| `GET /api/search?q=...` | `GET localhost:8000/search?q=...` |
| `POST /api/queue/add` | `POST localhost:8000/queue/add` |
| `WS /ws` | `WS localhost:8000/ws` |

`changeOrigin: true` sets the `Host` header to the target, avoiding CORS origin mismatch in some setups.

## The `/ws` Proxy

`ws: true` enables WebSocket proxying. The `useWebSocket` hook connects to `ws://localhost:3000/ws`, which Vite upgrades and tunnels to `ws://localhost:8000/ws`.

## Why Proxy?

- **Same-origin simplicity:** frontend code doesn't need to know the backend port or handle CORS in dev
- **CORS still configured on backend** (allows `localhost:3000` + `localhost:5173`) as a fallback for non-proxied setups
- **Works in prod** if frontend is served from the same origin as the backend (or behind a reverse proxy)

## Ports

| Service | Port |
|---------|------|
| Vite dev server | **3000** |
| Backend uvicorn | 8000 |
| Alternate Vite (some setups) | 5173 (allowed in CORS) |

## Build

`npm run build` = `tsc && vite build` — type-checks then bundles. Output goes to `frontend/dist/`.

## See Also

- [[Realtime Updates]] · [[Frontend api]] · [[Development Setup]] · [[Tech Stack]]
