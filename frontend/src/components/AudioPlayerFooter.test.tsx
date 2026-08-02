import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { AppProvider, useApp } from '../context/AppContext'
import type { PreviewTrack } from '../context/AppContext'
import { preview } from '../api'
import AudioPlayerFooter from './AudioPlayerFooter'

// Helper to find the visible key/camelot label; nulls render nothing.
function keyBadgeText(): string | null {
  const el = screen.queryByText(/^[0-9]+[AB]$|^[0-9]+A$|^[0-9]+B$/);
  if (!el) return null;
  return el.textContent;
}

// Harness lets the test pick the preview track and resolve metadata manually
// without relying on real timers. `getStream`/`getMetadata` are mocked per-test.
function PreviewController({ track }: { track: PreviewTrack }) {
  const { dispatch } = useApp();
  void act(() => null);
  return (
    <button
      data-testid="select-preview"
      onClick={() => dispatch({ type: 'SET_PREVIEW', payload: track })}
    >
      select
    </button>
  );
}

function makeTrack(id: number, title: string): PreviewTrack {
  return { id, title, artist: `Artist ${id}`, cover_url: null, key: null, camelot: null };
}

const track7 = makeTrack(7, 'Seven');
const track8 = makeTrack(8, 'Eight');

describe('AudioPlayerFooter', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts audio from the stream response before metadata resolves', async () => {
    // getStream resolves immediately; getMetadata never resolves during the test.
    preview.getStream = vi.fn().mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    preview.getMetadata = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(
      <AppProvider>
        <AudioPlayerFooter />
        <PreviewController track={track7} />
      </AppProvider>
    );

    // Select the preview track — triggers the effect.
    await act(async () => {
      screen.getByTestId('select-preview').click();
      // allow microtasks (resolved getStream promise) to flush.
      await Promise.resolve();
      await Promise.resolve();
    });

    // Audio construction must have happened even though getMetadata is pending forever.
    expect(preview.getStream).toHaveBeenCalledWith(7);
    expect(preview.getMetadata).toHaveBeenCalled();
    // The mock Audio constructor records instantiation of `new Audio(url)`.
    const audioMock = globalThis.Audio as unknown as { __calls: (string | undefined)[] };
    expect(audioMock.__calls.some((u) => u === '/audio/7')).toBe(true);
  });

  it('ignores metadata belonging to a replaced preview', async () => {
    // Hold track 7 metadata pending (we will resolve it later with stale data);
    // track 8 metadata resolves quickly with track-8 content.
    let resolveTrack7: ((v: unknown) => void) | null = null;
    let resolveTrack8: ((v: unknown) => void) | null = null;
    preview.getStream = vi.fn().mockImplementation((id: number) =>
      Promise.resolve({ track_id: id, stream_url: `/audio/${id}`, duration: 240 })
    );
    preview.getMetadata = vi.fn().mockImplementation((id: number) => {
      if (id === 7) return new Promise((r) => { resolveTrack7 = r });
      return new Promise((r) => { resolveTrack8 = r });
    });

    let selectTrack: (t: PreviewTrack) => void = () => {};
    function Controller() {
      const { dispatch } = useApp();
      selectTrack = (t) => dispatch({ type: 'SET_PREVIEW', payload: t });
      return null;
    }

    render(
      <AppProvider>
        <AudioPlayerFooter />
        <Controller />
      </AppProvider>
    );

    // Preview track 7 first, then swap to track 8 (supersede).
    await act(async () => {
      selectTrack(track7);
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      selectTrack(track8);
      await Promise.resolve();
      await Promise.resolve();
    });

    // Track 8 stream resolves + metadata poll fired for track 8. Resolve
    // track 8 metadata as complete with track-8 waveform/key.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    await act(async () => {
      expect(resolveTrack8).not.toBeNull();
      resolveTrack8!({
        track_id: 8,
        status: 'complete',
        revision: 1,
        waveform: { bands: { low: [0.5], mid: [0.5], high: [0.5] }, colors: { low: '#0055e2', mid: '#f2aa3c', high: '#ffffff' }, duration: 240 },
        key: 'C# minor',
        camelot: '9A',
        bpm: 124,
        error: null,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    // Now the superseded track 7 metadata response finally lands, claiming
    // track_id: 7 with different key/waveform. This MUST be rejected.
    await act(async () => {
      expect(resolveTrack7).not.toBeNull();
      resolveTrack7!({
        track_id: 7,
        status: 'complete',
        revision: 1,
        waveform: { bands: { low: [0.9], mid: [0.9], high: [0.9] }, colors: { low: '#0055e2', mid: '#f2aa3c', high: '#ffffff' }, duration: 240 },
        key: 'G major',
        camelot: 'G', // invalid camelot shape; ignored
        bpm: 99,
        error: null,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    // The visible key badge must reflect track 8 ('9A'), not track 7 ('G').
    expect(keyBadgeText()).toBe('9A');
  });
});
