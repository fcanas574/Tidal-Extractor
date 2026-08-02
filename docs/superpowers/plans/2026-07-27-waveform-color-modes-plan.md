# Waveform Color Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persisted 3Band and RGB waveform color options without changing waveform analysis or playback.

**Architecture:** Extend settings with `waveform_color: "3band" | "rgb"`, default to `3band`, expose the option in the existing SettingsPanel, and pass the selected palette into the canvas renderer. The numeric low/mid/high waveform data remains unchanged.

**Tech Stack:** React, TypeScript, FastAPI/Pydantic, YAML settings, Canvas 2D compositing.

## Global Constraints

- Default appearance remains the current 3Band blue/orange/white palette.
- RGB maps low/mid/high to red/green/blue.
- Changing color mode must not call preview or metadata APIs.
- Invalid persisted values must fall back to `3band`.
- Settings save behavior must remain compatible with existing config files.

---

### Task 1: Add the persisted waveform setting

**Files:**
- Modify: `backend/config.py:5-55`
- Modify: `backend/main.py:482-497`
- Modify: `frontend/src/api.ts:86-90`
- Modify: `frontend/src/context/AppContext.tsx:61`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- `Settings.waveform_color: '3band' | 'rgb'`.
- `AppConfig.waveform_color: str` with default `3band`.
- `UpdateSettingsRequest.waveform_color: str | None`.

- [ ] **Step 1: Write failing config tests**

```python
def test_waveform_color_defaults_to_3band(tmp_path):
    config = AppConfig(str(tmp_path / 'missing.yaml'))
    assert config.waveform_color == '3band'
    assert config.as_dict()['waveform_color'] == '3band'


def test_invalid_waveform_color_is_rejected(tmp_path):
    config = AppConfig(str(tmp_path / 'settings.yaml'))
    with pytest.raises(ValueError):
        config.update(waveform_color='purple')
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python3 -m pytest backend/tests/test_config.py -q`

Expected: FAIL because `waveform_color` is not part of `AppConfig`.

- [ ] **Step 3: Implement validation and persistence**

Define `WAVEFORM_COLORS = {'3band', 'rgb'}`. Add `waveform_color` to defaults, YAML load/save, `update()`, and `as_dict()`. Raise `ValueError("waveform_color must be '3band' or 'rgb'")` for other values. Add the optional field to `UpdateSettingsRequest`; only assign it after validation.

- [ ] **Step 4: Update frontend types and initial state**

Add `waveform_color: '3band' | 'rgb'` to `Settings` and set the initial context value to `3band`.

- [ ] **Step 5: Run tests and build**

Run: `python3 -m pytest backend/tests/test_config.py -q && cd frontend && npm run build`

Expected: PASS and successful build.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/main.py backend/tests/test_config.py frontend/src/api.ts frontend/src/context/AppContext.tsx
git commit -m "feat: persist waveform color preference"
```

### Task 2: Add settings controls and palette selection

**Files:**
- Modify: `frontend/src/components/SettingsPanel.tsx`
- Modify: `frontend/src/components/AudioPlayerFooter.tsx`
- Test: `frontend/src/components/AudioPlayerFooter.test.tsx`

**Interfaces:**
- `WaveformMode = '3band' | 'rgb'`.
- `WAVEFORM_PALETTES: Record<WaveformMode, { low: string; mid: string; high: string }>`.
- `drawClubWaveform(..., palette: WaveformPalette)`.

- [ ] **Step 1: Write palette tests**

```tsx
it('uses the 3Band palette by default', () => {
  expect(WAVEFORM_PALETTES['3band']).toEqual({ low: '#0055e2', mid: '#f2aa3c', high: '#ffffff' });
});

it('uses RGB colors without requesting new metadata', async () => {
  render(<PreviewHarness settings={{ waveform_color: 'rgb' }} />);
  const callsBefore = vi.mocked(preview.getMetadata).mock.calls.length;
  expect(screen.getByTestId('waveform-color-mode')).toHaveTextContent('rgb');
  expect(vi.mocked(preview.getMetadata).mock.calls.length).toBe(callsBefore);
});
```

- [ ] **Step 2: Run focused test to verify failure**

Run: `cd frontend && npm test -- --run src/components/AudioPlayerFooter.test.tsx`

Expected: FAIL because the palette map and setting control do not exist.

- [ ] **Step 3: Add the settings UI**

Add `WAVEFORM_OPTIONS` with `3band` label `3Band (Rekordbox)` and `rgb` label `RGB`. Render a two-option button group in `SettingsPanel.tsx`. Dispatch `SET_SETTINGS` on selection and rely on the existing Save button to persist the value.

- [ ] **Step 4: Make the canvas palette-driven**

Move the current hardcoded `specs` colors into `WAVEFORM_PALETTES`. Pass `state.settings.waveform_color` to the drawing function. Keep 3Band alpha values and use `lighter` compositing for RGB overlapping bands so red/green/blue energy can blend.

- [ ] **Step 5: Run tests and build**

Run: `cd frontend && npm test -- --run src/components/AudioPlayerFooter.test.tsx && npm run build`

Expected: PASS and successful build.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SettingsPanel.tsx frontend/src/components/AudioPlayerFooter.tsx frontend/src/components/AudioPlayerFooter.test.tsx
git commit -m "feat: add 3band and RGB waveform colors"
```
