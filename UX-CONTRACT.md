# UX Contract

This contract defines stable ownership and cross-screen behavior for the TidalExtractor UI. Product/API behavior remains owned by the existing frontend client, reducer, and backend contract.

## Product context

- Audience: people organizing a local TIDAL music collection, especially DJs who use preview, BPM, Camelot key, quality, and format metadata.
- Primary jobs: find TIDAL content, refine by DJ metadata, preview a track, enqueue downloads, monitor/recover queue work, inspect download history, and configure audio/output preferences.
- Target market(s): English-first, local-first desktop application; no market-specific business rules are currently encoded.
- Active locales: English UI copy. Dates and numbers use the browser locale where the current implementation calls platform formatting APIs.
- Language/content register and native-review policy: concise, direct English; technical terms follow the existing API/product vocabulary. No additional translation is implied by this redesign.
- Timezone/calendar policy: display timestamps in the device/browser local timezone and calendar; no user-configurable timezone exists.
- Accessibility target: WCAG 2.2 AA.

## Business-context sources

| Domain / scope | Authoritative source | Source type | Reviewed date |
|---|---|---|---|
| Product scope and user-visible behavior | `README.md`, `Design.md`, `docs/superpowers/specs/2026-09-22-quiet-studio-workspace-design.md` | Product documentation / approved design | 2026-09-22 |
| Catalog, queue, history, stats, preview, and settings data shapes | `frontend/src/api.ts`, corresponding backend routes in `backend/main.py` | API / implementation contract | 2026-09-22 |
| Queue ordering, revisions, realtime freshness, retry, and cancellation | `frontend/src/context/AppContext.tsx`, `frontend/src/hooks/useWebSocket.ts`, `docs/superpowers/specs/2026-09-13-frontend-ui-ux-rework-design.md` | Domain implementation / queue design | 2026-09-22 |
| Authentication/session boundary | `frontend/src/components/AuthGate.tsx`, `frontend/src/api.ts` | UI / API contract | 2026-09-22 |

Billing, payment, multi-role permissions, and regulated-market copy do not apply to the current local-first product surface. This is a UI contract, not a replacement for product, API, privacy, or legal policy.

## Visual contract

- Project `DESIGN.md`: `Design.md` (the established project file uses this capitalization).
- Token ownership model (`DESIGN.md` generated / existing runtime canonical): `Design.md` records intent and token roles; the runtime stylesheet owns resolved CSS values.
- Runtime design-system/token source: `frontend/src/index.css` custom properties and shared classes.
- Mapping/export/adapters: conceptual Obsidian/Graphite/Slate/Porcelain/Silver/Mint roles map to the existing `--obsidian`, `--graphite`, `--slate`, `--porcelain`, `--silver`, and `--mint` properties; component aliases remain in `:root`.
- Token drift gate: review `Design.md` against `index.css`; run the premium strict audit and inspect changed component styles for local token duplication.
- Supported themes: dark theme only.
- Design-context owner/review policy: update `Design.md` and this contract when shell, token ownership, scroll ownership, or shared interaction behavior changes; do not treat exported Stitch HTML or screenshots as runtime behavior.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Queue selection | `QueueView` | currently loaded canonical queue in `AppContext` | current queue snapshot only; no all-results selection | `QueueView.test.tsx` |
| Select/Listbox | Existing native `<select>` controls in Search filters and Settings | component draft/filter state | native only | component tests; keyboard and native popup check |
| Date | History row formatter | API timestamp plus browser locale/timezone | platform-formatted local date/time | `HistoryView.test.tsx`; browser locale check |
| Form | Search command form; Settings draft/save form | Search/Settings component state and existing API calls | search submit; explicit settings save | `SearchView.test.tsx`, `SettingsPanel.test.tsx` |
| Scrollbar | `frontend/src/index.css`; active list/pane owns overflow | CSS custom properties and each view's content | document scroll on narrow screens; bounded Search/Queue panes at >=1100px | computed-style/browser review; visible chrome; no hidden scrollbar rules |
| Toast | `ToastContainer` presentation; `AppContext` toast actions/state | canonical app toast state | success / warning / info / error; progress is excluded | `ToastContainer.test.tsx`, Context tests |
| Preview artist navigation | `SearchView` artist lookup and inspector; player emits a request through `AppContext` | `TrackResult.artist_id` carried by the active preview | activate Search and open the same artist inspector while preserving search session | `AudioPlayerFooter.test.tsx`, `SearchView.test.tsx` |
| Preview player expansion | `AudioPlayerFooter` and its fixed-player styles | active preview track plus local expanded state | up/down arrow overlays the cover on hover (and is available on keyboard focus/touch); expansion enlarges and anchors the cover left, moves waveform/details beside it with key/BPM left-aligned beneath, preserves right-anchored transport, and reserves the extra height | `AudioPlayerFooter.test.tsx`; responsive player review |
| CRUD | No generic CRUD workspace | feature-specific API calls own mutations | not applicable; queue/settings have dedicated flows | queue/settings component tests and API tests |

## Component behavior

| Component | Default | Hover | Focus | Active | Disabled | Busy | Error |
|---|---|---|---|---|---|---|---|
| Button | One clear verb; primary for the next action, quiet secondary otherwise | tonal change without layout shift | visible 2px focus ring | pressed color/state; no essential motion | native disabled semantics and clear contrast | stable dimensions and status text where applicable | inline message or shared error feedback |
| Icon button | compact icon with accessible name and full touch target | tonal surface | visible 2px focus ring | pressed/current surface | native disabled semantics | stable icon geometry | accessible label remains present |
| Input | persistent visible label; current value and placeholder remain distinct | border/surface change only | high-contrast border and ring | typed value | disabled state remains legible | pending search retains query and result context | inline error, preserve value and Retry where safe |
| Secret input | no secret-entry control is rendered in the redesigned workspace | n/a | n/a | n/a | n/a | n/a | authentication errors remain in `AuthGate` |
| Search | explicit submit; URL detection, filters, type, and query stay in the existing Search session | row/control tonal change | keyboard-visible | submitted/loading state announced | submit disabled only under existing validation/pending rules | stable result skeleton; stale request aborted/ignored | retain query and existing results as allowed; inline error and Retry |
| Textarea | not currently used by workspace forms | n/a | n/a | n/a | n/a | n/a | n/a |
| Table/list | one quiet list surface with clear row actions and separators | restrained row surface | focus goes to the real button/link, not a fake clickable container | selection/open state is explicit | action-specific native disabled state | row geometry stays stable while work progresses | preserve unaffected rows and offer the existing retry/recovery action |

## Dataset navigation

- Admin tables: none.
- Exploratory lists: Search catalog results, Queue items, and History items. At >=1100px Search results and Queue own bounded scrolling only after the shell/view flex chain is established. At narrower widths the document is the scroll owner.
- URL state: Search query/type/filters/detail remain transient in `AppContext`; they are not written to URL or browser storage. Queue and Activity derive from API/realtime state. No secret/session values enter URLs.
- Page size: Search follows the existing server response and explicit `Load more` for tracks; no user-facing page-size control. Queue and History use the existing API response size.
- Empty/no-results/error/loading treatment: compact contextual state; stable list geometry while loading; explain the next action; Retry where the existing operation is safe; partial Search results retain any successful result groups.
- Back/scroll restoration: opening/closing Search details preserves the current query, filters, results, and request generation. On mobile, `Back to search` returns to the result context. Avoid resetting a list just to open its inspector.
- Selection scope, selected count, filter/sort/paging behavior, keyboard operation, bulk confirmation, and post-action focus: Queue selection is limited to the current queue snapshot; count and bulk actions appear only in selection mode. Search and History do not have bulk selection. Selection and bulk removal/cancellation keep their explicit confirmation and feedback behavior; keyboard users activate real controls and focus returns to the invoking control after a panel closes.

## Flow ledger

| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Focus outcome | Source ref |
|---|---|---|---|---|---|---|---|
| Search | Search submit or existing query/type/filter interaction | retain query; announce loading; ignore/abort superseded request | same Search context, with returned results or detail | results/partial status in the page | preserve query and safe prior context; inline Retry | remains with Search controls/results | `SearchView.tsx`, `SearchView.test.tsx`, `frontend/src/api.ts` |
| Add download | Track/album/playlist download action | existing API and queue pending behavior; no progress toast | same view plus canonical Queue/Activity update | existing success toast/status | existing error feedback and safe retry | remain on the activated row action | `TrackRow.tsx`, `AlbumCard.tsx`, `AppContext.tsx` |
| Edit settings | Save changes in Settings | stable button and saving status | Settings stays open with saved values | inline success status | retain draft values; show inline error and Retry | stay in the form; close restores trigger focus | `SettingsPanel.tsx`, `SettingsPanel.test.tsx` |
| Queue bulk action | Enter selection mode, select current items, invoke bulk action | selected count/actions remain visible | same Queue with canonical API/reducer result | existing success feedback | keep recoverable selection/context and explain failure | return focus to the bulk action/selection control | `QueueView.tsx`, `QueueView.test.tsx` |
| Background download | Add work to canonical queue; REST/WebSocket updates | queue status/progress belongs to `AppContext` | Queue and Activity show the same item/state | terminal success/failure only; no progress toast | retry failed item; stale/reconnecting state is explicit | navigation focus is not stolen by progress | `AppContext.tsx`, `useWebSocket.ts`, `DownloadActivityPanel.tsx` |
| Cancel/back | Close detail/panel or cancel an active download | explicit inline confirmation for active cancellation | detail closes to preserved list; panel returns to caller; canceled queue state follows API | existing terminal/close feedback | failure remains visible with safe retry | Escape/cancel returns focus to trigger when the overlay owns focus | `SearchView.tsx`, `QueueView.tsx`, `SettingsPanel.tsx`, `DownloadActivityPanel.tsx` |

Downloads do not upload a local file. The app does not currently expose soft-delete or irreversible deletion of downloaded local files; those flows are not introduced here.

## Navigation and responsive behavior

- Route document title policy: one application title in `index.html`; active tabs do not create routes.
- Route error / 403 page behavior: no client-side route or 403 surface; authentication and API failures stay with their owning views.
- Breadcrumb/tab/route-state policy: `AppContext.activeTab` is canonical for Search, Queue, History, and Stats; selected tab exposes `aria-current="page"`.
- Sidebar/drawer/bottom-sheet transformation: desktop rail at >=1100px; labeled horizontal top navigation below; Activity and Settings use one app-owned surface each, lateral on wide screens and full-width/bottom-sheet treatment on mobile.
- Responsive table strategy: use compact list rows, not a wide data grid; labels and primary actions remain reachable at 390px; no horizontal page overflow.
- Truncation/full-value access: long titles may truncate visually while their text remains in the DOM; title/artist context and explicit detail view expose full values.
- Focus restoration and sticky-obstruction policy: Escape and close controls dismiss app-owned panels; return focus to the opening control; the desktop player starts after the persistent rail and content reserves player/safe-area space so actionable content is not covered.
- Preview navigation: a preview artist action activates Search and opens its canonical artist inspector without clearing the committed search; when cover art exists, a hover-revealed up/down arrow overlays the cover and toggles the fixed preview player inline between compact and expanded sizes. Expansion reveals the details on mobile; the player does not open a modal. The expanded cover is 100px on desktop and 88px on mobile, anchors left, and moves the waveform and key/BPM closer into the same composition while transport stays on the right. The control remains available on keyboard focus and touch, and respects reduced-motion preferences.

## Overlays and feedback

- Dialog primitive: existing app-owned Activity/Settings components own their documented modal/panel behavior; preview-player expansion is inline and non-modal, with no focus trap or dialog layer.
- Destructive confirmation levels: active download cancellation keeps inline `Cancel download` and `Keep downloading`; no browser-native confirmation dialogs.
- Toast placement/duration/deduplication: `ToastContainer`; at most three visible, dismissible messages, existing duration/deduplication behavior; progress remains in Queue/Activity.
- Alert/banner scope and persistence: inline field/view errors persist with the owning operation; connection/reconnecting is a persistent shell status.
- Tooltip delay/dismissal: native `title` only for supplementary labels; essential actions never rely on a tooltip.
- Unsaved-changes behavior: Settings Discard resets its draft; failed save retains the draft and leaves Retry available; explicit close/Escape behavior must match current modal tests.
- Layer/z-index contract: Activity/Settings surfaces > app navigation/content; the fixed player stays within the desktop workspace, remains visible unless an active modal intentionally covers it, and reserves additional content space while expanded; toast is above non-modal content and must not block its close/action controls.

## Async and resilience

- Mutation default (pessimistic/optimistic/queued): follow each existing API/reducer path; downloads are canonical queue work, not a second component store.
- Idempotency and duplicate-submit policy: use existing API semantics and disable only the in-flight action; no new retry key or duplicate backend request protocol.
- Auto-save/draft recovery: Settings uses an explicit in-memory draft; no autosave or persisted draft is promised.
- Offline/read-stale/write behavior: realtime disconnect is visible; REST refresh and WebSocket reconciliation retain existing queue rules; no new offline-write mode.
- Retry/backoff/timeout behavior: existing API/component retry behavior is authoritative; do not add a UI-only retry loop.
- Version conflict and multi-tab behavior: queue item revisions and monotonic progress are reconciled by `AppContext`; no cross-tab coordination is promised.
- Session expiry/re-authentication: `AuthGate` and existing auth API own the session boundary.
- Long-running progress and return path: Queue and Activity read the same canonical queue and metadata; terminal state remains inspectable after navigating elsewhere.
- Stale-request cancellation/invalidation and pending-state ownership: Search abort controller/request generation remains in Search; preview uses current abort/token guards; queue revisions/progress are reducer-owned.
- Dialog/form preservation and retry after mutation failure: preserve Settings draft on error and leave panel open; detail dismissal preserves Search results; avoid clearing selected work on a failed action.

## Validation

- Schema/validation layer: existing client/server API validation and current field-level constraints; no new client schema library.
- Trigger timing: Search on explicit submit and existing supported query interactions; Settings validates through its current submit/save path.
- Error summary/inline policy: errors stay near the owning view/control; shared Toast is reserved for cross-view status and important mutation outcomes.
- Server error mapping: display existing API error text through current component behavior; do not fabricate fields or failure categories.
- Sensitive-value handling: no TIDAL credential or session secret is rendered into query strings, toasts, or diagnostic UI.
- `noValidate`, first-invalid focus, duplicate-submit prevention, unsaved changes, and submit recovery: Search declares `noValidate`, trims on submit, accepts a genre-only search, and leaves an empty unfiltered submit inert; Settings saves its local draft only through the explicit Save action. Keep drafts on failure and preserve the current API pending guards and discard/recovery interaction.

## Permission and clipboard

- Permission UI strategy (hide vs disable vs 403 page): local app has no workspace-role permission matrix; TIDAL connection/auth gating remains in `AuthGate`.
- Clipboard copy policy (truncated preview + copy button, no secret in toast): no new clipboard behavior; never copy session secrets.
- Disabled-state explanation (tooltip with reason): retain visible disabled state and inline explanation where the current component supplies one; never make a disabled action available only through hover.

## Verification

- Required static commands: `rtk npm test -- --run`, `rtk npm run build`, `rtk git diff --check`, and the premium frontend-design strict audit.
- Browser/device/locale/theme matrix: 1440px desktop, 1024px tablet, and 390px mobile; dark theme; current English copy; narrow-width and safe-area checks.
- Accessibility checks: semantic navigation/headings/buttons, keyboard operation and visible focus, reduced motion, forced-colors scrollbar visibility, status/live regions, long-title and zoom review.
- Native-language/domain review and target-user evidence: not applicable to the English-only copy change; existing DJ metadata terms remain literal.
- Japan readiness matrix: not applicable; this product does not currently target Japanese copy or market conventions.
- Component-state/visual regression coverage: Vitest/Testing Library tests for navigation, Search, Queue/Activity, Settings, player, History, toast, and APIs; manual screenshot/layout review at the listed viewports.
- Canonical sibling flow used for comparison: Search detail open/close and queue progress/retry, compared with their existing API/reducer owners.
- Project audit command/result: run `frontend-design-premium/scripts/audit_project.py` with `--mode strict`; record audit output alongside implementation verification.
- CRUD full-flow evidence: generic CRUD is not applicable; verify feature-specific Queue and Settings mutation tests.
- Failure-path evidence: Search Retry/partial results, Queue failed/retry/cancel, Activity stale/reconnect, Settings save failure with draft retention, and player unavailable waveform/metadata states.
