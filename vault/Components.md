# Components

The React component tree in `frontend/src/components/`. The root composition lives in `App.tsx`.

**See:** [[State Management]] · [[Frontend api]] · [[File Tree]]

## Composition (`App.tsx`)

```
<AppProvider>
  <AuthGate>                         # gate: shows device-link UI if !auth
    <NavBar />                       # tabs: search/queue/history/stats + settings gear
    <main>
      {activeTab === 'search'  && <SearchView />}
      {activeTab === 'queue'   && <QueueView />}
      {activeTab === 'history' && <HistoryView />}
      {activeTab === 'stats'   && <StatsView />}
    </main>
    <SettingsPanel />                # slide-out drawer (toggled from NavBar)
    <ToastContainer />               # stacked notifications
    <AudioPlayerFooter />            # fixed bottom bar when previewTrack set
  </AuthGate>
</AppProvider>
```

`main` gets `paddingBottom: 120px` when a preview is active so the footer doesn't cover content.

## Component Inventory

### `AuthGate.tsx`
OAuth device-link flow UI. If `!state.auth.authenticated`, renders the link URL + code and a verify button. Otherwise renders `children`. Calls `auth.getDeviceLink()` / `auth.verifyDeviceLink()` / `auth.getStatus()`.

### `NavBar.tsx`
Top navigation: tab buttons (Search/Queue/History/Stats) + settings gear icon. Dispatches `SET_TAB` and `TOGGLE_SETTINGS_PANEL`. Likely shows auth username + logout.

### `SearchView.tsx` (~25KB — the largest component)
The DJ-oriented search experience:
- **Search header:** text input, type selector, **genre dropdown** (always visible — enables genre-only searches)
- **Filter bar** (appears when results exist): BPM min/max inputs, Camelot key dropdown (1A–12B), **🎯 Compatible toggle**, Clear button
- **Results list:** each track shows title/artist/album/duration/quality + **amber BPM badge** + **cyan Camelot badge**, plus preview + download actions
- **"Load More" button:** pagination (see [[Search Subsystem]])
- **Artist view:** when resolving an artist URL, shows top tracks + albums
- Local state: `query`, `searchType`, `results`, `bpmMin/Max`, `selectedKey`, `keyCompatible`, `selectedGenre`, `loadedCount`, `hasMore`, `loadingMore`, `artistResult`
- Helper: `toCamelot()` for client-side key conversion

### `QueueView.tsx` (~16KB)
Download queue management:
- Lists all queue items with live progress bars (driven by WS `progress` messages)
- Per-item actions: remove, retry (on failure)
- Bulk actions: clear completed, clear all, batch remove
- Status badges: queued / downloading (with %) / complete / failed (with error)

### `HistoryView.tsx`
Completed downloads:
- List of `HistoryItem`s (title, artist, quality, format, size, date)
- **Re-download** button (calls `history.reDownload`)
- **Open folder** action (reveals the file in Finder/Explorer)
- Pagination via offset/limit

### `StatsView.tsx`
Device-wide statistics dashboard:
- Total tracks downloaded
- Total storage used (formatted)
- Quality breakdown (count per preset)
- Reads from `GET /stats`

### `SettingsPanel.tsx`
Slide-out drawer (toggled from NavBar gear):
- Default Quality dropdown (HiRes Lossless / Lossless / High / Normal)
- Default Format dropdown (FLAC / MP3 / M4A)
- Output Directory text input
- Saves via `settings.update()` → `PUT /settings`
- Local form state, commits on save

### `ToastContainer.tsx`
Stacked notification toasts:
- Types: info / success / error / downloading (with progress bar)
- Auto-dismiss based on `dismissAt` timestamp
- Driven by `state.toasts` (WS messages create/update/dismiss them)

### `AudioPlayerFooter.tsx` (~13KB)
Fixed bottom bar — the waveform preview player:
- Renders tri-band waveform on a `<canvas>` (lows/mids/highs from `WaveformData.bands`)
- Play/pause, seek by clicking the waveform
- Shows track title/artist + detected key/Camelot
- Listens for `preview-toggle-play` custom DOM event (from Space key in `App.tsx`)
- Colors: low `#0055e2`, mid `#f2aa3c`, high `#ffffff`
- Appears only when `state.previewTrack` is set; `CLEAR_PREVIEW` hides it

### `ArtistView.tsx` (~8KB)
Artist detail view (reached via URL resolve):
- Artist bio + image
- Top tracks list (with preview/download)
- Albums grid

## Styling

Tailwind utility classes throughout. Custom CSS classes in `index.css`:
- `.dj-filter-bar`, `.filter-group`, `.filter-toggle`, `.btn-clear-filters` (DJ filters)
- Badge styles for BPM (amber) and Camelot (cyan)
- Rainbow animation for Camelot key display during preview
- `btn-primary` and other shared button styles

## See Also

- [[State Management]] · [[Frontend api]] · [[Search Subsystem]] · [[DJ Filters]]
