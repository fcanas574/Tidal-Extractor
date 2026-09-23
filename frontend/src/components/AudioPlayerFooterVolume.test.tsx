// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { fireEvent, render, waitFor, cleanup, screen, act } from '@testing-library/react';
import * as api from '../api';
import AudioPlayerFooter from './AudioPlayerFooter';
import { sliderToGain } from '../utils/audioMath';

const testSettings: api.Settings = {
  default_quality: 'high_lossless',
  default_format: 'FLAC',
  output_dir: '~/Music/TidalDownloads',
  waveform_color: '3band',
};

vi.mock('../context/AppContext', () => ({
  useApp: () => ({
    state: {
      previewTrack: { id: 7, title: 'Sample Song', artist: 'Sample Artist', artist_id: null, cover_url: null },
      previewPlaying: true,
      settings: testSettings,
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

describe('AudioPlayerFooter Volume Control with Psychoacoustic Mapping', () => {
  beforeEach(() => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  });

  afterEach(() => {
    localStorage.clear();
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders the volume slider and mute button with proper accessibility', () => {
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));
    render(<AudioPlayerFooter />);

    const sliders = screen.getAllByRole('slider', { name: 'Preview volume' });
    expect(sliders.length).toBeGreaterThan(0);
    const slider = sliders[0];
    expect(slider.getAttribute('aria-valuenow')).toBe('80'); // safe default 0.8 (80%)

    const muteButtons = screen.getAllByRole('button', { name: 'Mute preview' });
    expect(muteButtons.length).toBeGreaterThan(0);
  });

  it('preserves user volume selection across page reloads/remounts', async () => {
    // User had previously lowered their volume to 0.35 (35%)
    localStorage.setItem('tidal_preview_volume', '0.35');
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));

    const { unmount } = render(<AudioPlayerFooter />);
    let slider = screen.getAllByRole('slider', { name: 'Preview volume' })[0];
    expect(slider.getAttribute('aria-valuenow')).toBe('35');

    // Simulate closing page and reopening
    unmount();
    render(<AudioPlayerFooter />);
    slider = screen.getAllByRole('slider', { name: 'Preview volume' })[0];
    expect(slider.getAttribute('aria-valuenow')).toBe('35');
  });


  it('initializes audio element volume using the non-linear curve from saved preference', async () => {
    let capturedAudio: HTMLAudioElement | null = null;
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const el = document.createElement('audio');
      if (url) el.src = url;
      capturedAudio = el;
      return el as any;
    });

    localStorage.setItem('tidal_preview_volume', '0.8');
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'complete', revision: 1,
      waveform: null, key: null, camelot: null, bpm: null, error: null,
    });

    render(<AudioPlayerFooter />);
    await waitFor(() => expect(capturedAudio).toBeTruthy());

    // Verified: volume is mapped using psychoacoustic curve (approx 0.251), NOT linear 0.8
    expect(capturedAudio!.volume).toBeCloseTo(sliderToGain(0.8), 4);
    expect(capturedAudio!.volume).not.toBeCloseTo(0.8, 1);
  });

  it('updates audio element volume non-linearly when slider is adjusted', async () => {
    let capturedAudio: HTMLAudioElement | null = null;
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const el = document.createElement('audio');
      if (url) el.src = url;
      capturedAudio = el;
      return el as any;
    });

    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'complete', revision: 1,
      waveform: null, key: null, camelot: null, bpm: null, error: null,
    });

    render(<AudioPlayerFooter />);
    await waitFor(() => expect(capturedAudio).toBeTruthy());

    const slider = screen.getAllByRole('slider', { name: 'Preview volume' })[0];

    // Drag slider to 50% (0.5 position)
    fireEvent.change(slider, { target: { value: '0.5' } });

    // In a linear slider, 0.5 would be 0.5 amplitude.
    // In our non-linear slider (60 dB range), 0.5 is -30 dB = ~0.0316 amplitude.
    await waitFor(() => expect(capturedAudio!.volume).toBeCloseTo(sliderToGain(0.5), 4));
    expect(capturedAudio!.volume).toBeCloseTo(0.03162, 3);
    expect(localStorage.getItem('tidal_preview_volume')).toBe('0.5');

    // Drag slider to 10% (0.1 position)
    fireEvent.change(slider, { target: { value: '0.1' } });
    await waitFor(() => expect(capturedAudio!.volume).toBeCloseTo(sliderToGain(0.1), 4));
    expect(capturedAudio!.volume).toBeCloseTo(0.001995, 4);
    expect(localStorage.getItem('tidal_preview_volume')).toBe('0.1');

    // Drag slider to 0% (true silence)
    fireEvent.change(slider, { target: { value: '0' } });
    await waitFor(() => expect(capturedAudio!.volume).toBe(0));
    expect(localStorage.getItem('tidal_preview_volume')).toBe('0');
  });

  it('supports muting and unmuting, restoring previous volume level', async () => {
    let capturedAudio: HTMLAudioElement | null = null;
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const el = document.createElement('audio');
      if (url) el.src = url;
      capturedAudio = el;
      return el as any;
    });

    localStorage.setItem('tidal_preview_volume', '0.75');
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'complete', revision: 1,
      waveform: null, key: null, camelot: null, bpm: null, error: null,
    });

    render(<AudioPlayerFooter />);
    await waitFor(() => expect(capturedAudio).toBeTruthy());

    // Initial volume check
    expect(capturedAudio!.volume).toBeCloseTo(sliderToGain(0.75), 4);

    // Mute
    const muteBtn = screen.getAllByRole('button', { name: 'Mute preview' })[0];
    fireEvent.click(muteBtn);

    await waitFor(() => expect(capturedAudio!.volume).toBe(0));
    expect(localStorage.getItem('tidal_preview_muted')).toBe('true');

    // Unmute restores to 0.75 non-linear gain
    const unmuteBtn = screen.getAllByRole('button', { name: 'Unmute preview' })[0];
    fireEvent.click(unmuteBtn);

    await waitFor(() => expect(capturedAudio!.volume).toBeCloseTo(sliderToGain(0.75), 4));
    expect(localStorage.getItem('tidal_preview_muted')).toBe('false');

    // Mute via custom event preview-toggle-mute
    act(() => {
      window.dispatchEvent(new Event('preview-toggle-mute'));
    });
    await waitFor(() => expect(capturedAudio!.volume).toBe(0));
  });
});
