// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, waitFor, cleanup, screen } from '@testing-library/react';
import * as api from '../api';

let currentSettings: api.Settings = {
  default_quality: 'high_lossless',
  default_format: 'FLAC',
  output_dir: '~/Music/TidalDownloads',
  waveform_color: '3band',
};

vi.mock('../context/AppContext', () => ({
  useApp: () => ({
    state: {
      previewTrack: { id: 7, title: 'T', artist: 'A', cover_url: null },
      previewPlaying: true,
      settings: currentSettings,
    },
    dispatch: vi.fn(),
  }),
}));
vi.mock('../api', async (orig) => ({
  ...(await orig()),
  preview: {
    getUrl: vi.fn(),
    getStream: vi.fn(),
    getMetadata: vi.fn(),
  },
}));

import AudioPlayerFooter, { WAVEFORM_PALETTES } from './AudioPlayerFooter';

function PreviewHarness(props: { settings?: Partial<api.Settings> }) {
  if (props.settings) {
    currentSettings = { ...currentSettings, ...props.settings };
  }
  return <AudioPlayerFooter />;
}

describe('AudioPlayerFooter fast lifecycle', () => {
  afterEach(() => {
    currentSettings = {
      default_quality: 'high_lossless',
      default_format: 'FLAC',
      output_dir: '~/Music/TidalDownloads',
      waveform_color: '3band',
    };
    cleanup();
    vi.restoreAllMocks();
  });

  it('uses the 3Band palette by default', () => {
    expect(WAVEFORM_PALETTES['3band']).toEqual({ low: '#0054e2', mid: '#b3680a', high: '#f6ebd8' });
  });

  it('uses RGB colors without requesting new metadata', async () => {
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'complete', revision: 1,
      waveform: { bands: { low: [0.5], mid: [0.5], high: [0.5] }, colors: {}, duration: 240 },
      key: null, camelot: '8A', bpm: 128, error: null,
    });
    const callsBefore = vi.mocked(api.preview.getMetadata).mock.calls.length;
    render(<PreviewHarness settings={{ waveform_color: 'rgb' }} />);
    expect(screen.getByTestId('waveform-color-mode').textContent).toBe('rgb');
    expect(vi.mocked(api.preview.getMetadata).mock.calls.length).toBe(callsBefore);
  });

  it('starts audio from stream response before metadata resolves', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    const audioCtor = vi.spyOn(window, 'Audio');
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    let resolveMeta!: (v: any) => void;
    (api.preview.getMetadata as any).mockImplementation(
      () => new Promise((res) => { resolveMeta = res; }));
    render(<AudioPlayerFooter />);
    // Audio element constructed from the stream response while metadata still pending
    await waitFor(() => expect(api.preview.getMetadata).toHaveBeenCalledWith(7, expect.anything()), { timeout: 3000 });
    expect(audioCtor).toHaveBeenCalledWith('/audio/7');
    expect(resolveMeta).toBeDefined();
    expect(play).toHaveBeenCalled();
  });

  it('applies only metadata matching the active preview token', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    // First getMetadata resolves for an OLD track id (9) after the active one is 7;
    // component must not apply it because snapshot track_id mismatches active preview.
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 9, status: 'complete', revision: 2,
      waveform: { bands: { low: [0.9], mid: [0.9], high: [0.9] }, colors: {}, duration: 999 },
      key: null, camelot: null, bpm: null, error: null,
    });
    const { container } = render(<AudioPlayerFooter />);
    await waitFor(() => expect(play).toHaveBeenCalled());
    // Give any erroneous application a tick, then assert no waveform was drawn from track 9's data
    await new Promise((r) => setTimeout(r, 900));
    expect(container.querySelector('canvas')).toBeNull(); // shimmer placeholder still shown
  });

  it('retries polling after a transient metadata error and applies the later snapshot', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any)
      .mockRejectedValueOnce(new Error('transient network blip'))
      .mockResolvedValueOnce({
        track_id: 7, status: 'complete', revision: 1,
        waveform: { bands: { low: [0.5], mid: [0.5], high: [0.5] }, colors: {}, duration: 240 },
        key: null, camelot: '8A', bpm: 128, error: null,
      });
    const { container } = render(<AudioPlayerFooter />);
    // First tick fails; the next tick retries and the resolved waveform renders (canvas replaces shimmer)
    await waitFor(() => expect(container.querySelector('canvas')).toBeTruthy(), { timeout: 4000 });
    expect(api.preview.getMetadata).toHaveBeenCalledTimes(2);
    expect(play).toHaveBeenCalled();
  });

  it('shows a non-blocking unavailable state when the metadata snapshot fails', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'failed', revision: 3,
      waveform: null, key: null, camelot: null, bpm: null, error: 'decode died',
    });
    const { container } = render(<AudioPlayerFooter />);
    // Shimmer is replaced by muted text; audio keeps playing; polling stops
    await waitFor(() => expect(container.textContent).toContain('waveform unavailable'));
    expect(container.querySelector('.animate-pulse')).toBeNull();
    expect(api.preview.getMetadata).toHaveBeenCalledTimes(1);
    await new Promise((r) => setTimeout(r, 900));
    expect(api.preview.getMetadata).toHaveBeenCalledTimes(1); // no retry after terminal failure
    expect(play).toHaveBeenCalled();
  });

  it('aborts in-flight preview requests on unmount', async () => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    const signals: AbortSignal[] = [];
    (api.preview.getMetadata as any).mockImplementation(
      (_id: number, signal?: AbortSignal) => {
        if (signal) signals.push(signal);
        return new Promise(() => {}); // never resolves: request stays in flight
      });
    const { unmount } = render(<AudioPlayerFooter />);
    await waitFor(() => expect(signals.length).toBeGreaterThan(0));
    unmount();
    expect(signals[0].aborted).toBe(true);
  });
});
