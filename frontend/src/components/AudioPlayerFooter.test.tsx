// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { fireEvent, render, waitFor, cleanup, screen } from '@testing-library/react';
import * as api from '../api';

const { mockDispatch, mockPreviewTrack, previewEnabled } = vi.hoisted(() => ({
  mockDispatch: vi.fn(),
  previewEnabled: { value: true },
  mockPreviewTrack: {
    id: 7,
    title: 'T',
    artist: 'A',
    artist_id: 3 as number | null,
    cover_url: null as string | null,
    key: null,
    camelot: null,
  },
}));

let currentSettings: api.Settings = {
  default_quality: 'high_lossless',
  default_format: 'FLAC',
  output_dir: '~/Music/TidalDownloads',
  waveform_color: '3band',
};

vi.mock('../context/AppContext', () => ({
  useApp: () => ({
    state: {
      previewTrack: previewEnabled.value ? mockPreviewTrack : null,
      previewPlaying: true,
      settings: currentSettings,
    },
    dispatch: mockDispatch,
  }),
}));
vi.mock('../api', async (orig) => ({
  ...(await orig()),
  preview: {
    getUrl: vi.fn(),
    getStream: vi.fn(),
    getMetadata: vi.fn(),
    retryAnalysis: vi.fn(),
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
    mockPreviewTrack.id = 7;
    mockPreviewTrack.title = 'T';
    mockPreviewTrack.artist = 'A';
    mockPreviewTrack.artist_id = 3;
    mockPreviewTrack.cover_url = null;
    previewEnabled.value = true;
    vi.mocked((api.preview as any).retryAnalysis).mockReset();
    mockDispatch.mockClear();
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uses the 3Band palette by default', () => {
    expect(WAVEFORM_PALETTES['3band']).toEqual({ low: '#0054e2', mid: '#b3680a', high: '#f6ebd8' });
  });

  it('keeps hook order stable when the player enters, exits, and reopens', async () => {
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));
    previewEnabled.value = false;
    const view = render(<AudioPlayerFooter />);
    expect(screen.queryByRole('region', { name: /Preview player/ })).not.toBeInTheDocument();

    previewEnabled.value = true;
    view.rerender(<AudioPlayerFooter />);
    expect(screen.getByRole('region', { name: 'Preview player: Playing T by A' })).toBeInTheDocument();

    previewEnabled.value = false;
    view.rerender(<AudioPlayerFooter />);
    await waitFor(() => expect(screen.queryByRole('region', { name: /Preview player/ })).not.toBeInTheDocument(), { timeout: 400 });

    previewEnabled.value = true;
    view.rerender(<AudioPlayerFooter />);
    expect(screen.getByRole('region', { name: 'Preview player: Playing T by A' })).toBeInTheDocument();
  });

  it('exposes an understandable compact player to assistive technology', () => {
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));
    render(<AudioPlayerFooter />);

    expect(screen.getByRole('region', { name: 'Preview player: Playing T by A' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Pause preview' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'Close preview player' })).toBeTruthy();
    const detailsToggle = screen.getByRole('button', { name: 'Show preview details' });
    expect(detailsToggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(detailsToggle);
    expect(screen.getByRole('button', { name: 'Hide preview details' }).getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('T')).toBeTruthy();
    expect(screen.getByText('A')).toBeTruthy();
  });

  it('expands inline from a larger up/down control over the cover on hover', () => {
    mockPreviewTrack.cover_url = '/covers/7.jpg';
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));
    render(<AudioPlayerFooter />);

    const player = screen.getByRole('region', { name: 'Preview player: Playing T by A' });
    const expandButton = screen.getByRole('button', { name: 'Expand preview player' });
    const artworkCluster = expandButton.parentElement;
    const artwork = document.querySelector('.preview-player-artwork');
    const playerMain = document.getElementById('preview-player-main');
    const playerDetails = document.getElementById('preview-player-details');
    const arrow = expandButton.querySelector('svg');

    expect(artworkCluster).toHaveClass('preview-player-artwork-cluster');
    expect(expandButton).toHaveClass('preview-player-artwork-overlay');
    expect(artworkCluster?.firstElementChild).toBe(artwork);
    expect(artworkCluster?.lastElementChild).toBe(expandButton);
    expect(playerDetails?.parentElement).toBe(playerMain);
    expect(playerDetails).toHaveClass('hidden');
    expect(arrow).toHaveAttribute('width', '22');
    expect(arrow).toHaveAttribute('height', '22');
    expect(arrow).toHaveAttribute('data-direction', 'up');
    expect(expandButton).toHaveAttribute('aria-expanded', 'false');
    expect(player).not.toHaveClass('is-expanded');

    fireEvent.click(expandButton);

    const collapseButton = screen.getByRole('button', { name: 'Collapse preview player' });
    expect(collapseButton).toHaveAttribute('aria-expanded', 'true');
    expect(collapseButton).toHaveAttribute('aria-controls', 'preview-player-main preview-player-details');
    expect(collapseButton.querySelector('svg')).toHaveAttribute('data-direction', 'down');
    expect(playerDetails).toHaveClass('block');
    expect(player).toHaveClass('is-expanded');
    expect(screen.getByRole('button', { name: 'Pause preview' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(collapseButton);

    expect(screen.getByRole('button', { name: 'Expand preview player' })).toHaveAttribute('aria-expanded', 'false');
    expect(playerDetails).toHaveClass('hidden');
    expect(player).not.toHaveClass('is-expanded');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the preview artist through the shared catalog detail request', () => {
    (api.preview.getStream as any).mockImplementation(() => new Promise(() => {}));
    render(<AudioPlayerFooter />);

    fireEvent.click(screen.getByRole('button', { name: 'Open artist A' }));

    expect(mockDispatch).toHaveBeenCalledWith({ type: 'REQUEST_ARTIST_DETAIL', payload: 3 });
  });

  it('keeps a failed stream recoverable instead of silently dismissing the player', async () => {
    (api.preview.getStream as any)
      .mockRejectedValueOnce(new Error('stream unavailable'))
      .mockImplementationOnce(() => new Promise(() => {}));
    render(<AudioPlayerFooter />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Preview unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry preview' }));
    await waitFor(() => expect(api.preview.getStream).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('region', { name: /Preview player/ })).toBeInTheDocument();
  });

  it('keeps BPM and Camelot visible as static metadata while playing and retains keyboard seeking', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const capturedAudio: { current: HTMLAudioElement | null } = { current: null };
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      capturedAudio.current = audio;
      return audio as any;
    });
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 240 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7, status: 'complete', revision: 1,
      waveform: { bands: { low: [0.5, 0.4], mid: [0.4, 0.3], high: [0.3, 0.2] }, colors: {}, duration: 240 },
      key: null, camelot: '8A', bpm: 128, error: null,
    });
    render(<AudioPlayerFooter />);

    const camelot = await screen.findByTestId('camelot-key', {}, { timeout: 2500 });
    const bpm = await screen.findByTestId('bpm-badge', {}, { timeout: 2500 });
    expect(camelot).toHaveTextContent('8A');
    expect(bpm).toHaveTextContent('128 BPM');
    expect(camelot.style.animation).toBe('');
    expect(bpm.style.animation).toBe('');
    expect(screen.getByRole('button', { name: 'Pause preview' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('preview-artwork-fallback')).toBeInTheDocument();

    const seekSlider = await screen.findByRole('slider', { name: 'Seek preview: T' });
    fireEvent.keyDown(seekSlider, { key: 'ArrowRight' });
    expect(capturedAudio.current?.currentTime).toBe(5);
    expect(play).toHaveBeenCalled();
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

  it('renders_analysis_states_and_provider_source', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      return audio as any;
    });
    const waveform = {
      bands: { low: [0.5], mid: [0.4], high: [0.3] },
      colors: {},
      duration: 20,
    };
    const base = {
      track_id: 7,
      revision: 1,
      waveform_status: 'complete',
      waveform,
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis_error: null,
      key_source: null,
      bpm_source: null,
      provider_key: null,
      provider_camelot: null,
      provider_bpm: null,
      analysis: {
        key: { key: 'C', camelot: '8B', status: 'reliable' },
        rhythm: {
          bpm: 120,
          beats: [],
          downbeats: [],
          status: 'reliable',
          grid: {
            bpm: 120,
            period_seconds: 0.5,
            origin_seconds: 0,
            meter: '4/4',
            first_downbeat_beat: 0,
            status: 'reliable',
          },
        },
      },
    };
    const scenarios = [
      [{ ...base, status: 'processing', analysis_status: 'processing' }, 'Analyzing'],
      [{ ...base, status: 'complete', analysis_status: 'complete' }, 'Ready'],
      [{
        ...base,
        status: 'complete',
        analysis_status: 'complete',
        camelot: '8A',
        key_source: 'provider',
        bpm: 111,
        bpm_source: 'provider',
        provider_camelot: '8A',
        provider_bpm: 111,
        analysis: {
          key: { key: null, camelot: null, status: 'unknown' },
          rhythm: {
            bpm: null,
            beats: [],
            downbeats: [],
            status: 'needs_review',
            grid: {
              bpm: 127.5,
              period_seconds: 60 / 127.5,
              origin_seconds: 0,
              meter: '4/4',
              first_downbeat_beat: 0,
              status: 'needs_review',
            },
          },
        },
      }, 'Needs review'],
      [{ ...base, status: 'partial', analysis_status: 'failed' }, 'Analysis unavailable'],
      [{ ...base, status: 'partial', analysis_status: 'unknown' }, 'Unknown'],
    ] as const;

    for (const [snapshot, expectedState] of scenarios) {
      (api.preview.getStream as any).mockResolvedValueOnce({ track_id: 7, stream_url: '/audio/7', duration: 20 });
      (api.preview.getMetadata as any).mockResolvedValueOnce(snapshot);
      const view = render(<AudioPlayerFooter />);

      expect(await screen.findByText(expectedState, {}, { timeout: 2500 })).toBeInTheDocument();
      expect(screen.getByTestId('preview-analysis-status')).toHaveAttribute('role', 'status');
      expect(screen.getByTestId('preview-analysis-status')).toHaveAttribute('aria-live', 'polite');
      expect(play).toHaveBeenCalled();

      if (expectedState === 'Needs review') {
        expect(screen.getByTestId('camelot-key')).toHaveTextContent('8A');
        expect(screen.getByTestId('bpm-badge')).toHaveTextContent('111 BPM');
        expect(screen.getByText('Key from provider')).toBeInTheDocument();
        expect(screen.getByText('BPM from provider')).toBeInTheDocument();
        expect(screen.queryByText('127.5')).not.toBeInTheDocument();
      }

      view.unmount();
    }
  });

  it('draws_beats_and_downbeats_without_blocking_seek', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const capturedAudio: { current: HTMLAudioElement | null } = { current: null };
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      capturedAudio.current = audio;
      return audio as any;
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0, top: 0, right: 200, bottom: 44, width: 200, height: 44, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 20 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7,
      status: 'complete',
      revision: 1,
      waveform_status: 'complete',
      analysis_status: 'complete',
      waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis: {
        key: { key: null, camelot: null, status: 'unknown' },
        rhythm: {
          bpm: 120,
          beats: [1, 2, 3],
          downbeats: [1, 3],
          status: 'needs_review',
          grid: { bpm: null, period_seconds: null, origin_seconds: null, meter: null, first_downbeat_beat: null, status: 'needs_review' },
        },
      },
    });
    const { container } = render(<AudioPlayerFooter />);

    const markers = await screen.findAllByTestId(/^(beat|downbeat)-marker$/);
    expect(markers).toHaveLength(3);
    expect(markers.map((marker) => marker.getAttribute('data-time'))).toEqual(['1', '2', '3']);
    expect(markers.map((marker) => marker.getAttribute('data-marker-kind'))).toEqual(['downbeat', 'beat', 'downbeat']);
    expect(markers[0].getAttribute('aria-hidden')).toBe('true');
    expect(markers[0].parentElement).toHaveStyle({ pointerEvents: 'none' });

    const canvas = screen.getByRole('slider', { name: 'Seek preview: T' });
    fireEvent.click(canvas, { clientX: 100 });
    expect(capturedAudio.current?.currentTime).toBe(10);
    expect(play).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="preview-analysis-status"]')).toHaveTextContent('Needs review');
  });

  it('coalesces_markers_with_downbeat_priority', async () => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      return audio as any;
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0, top: 0, right: 100, bottom: 44, width: 100, height: 44, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 10 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7,
      status: 'complete',
      revision: 1,
      waveform_status: 'complete',
      analysis_status: 'complete',
      waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 10 },
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis: {
        key: { key: null, camelot: null, status: 'unknown' },
        rhythm: {
          bpm: 120,
          beats: [0.5, 0.52, 1],
          downbeats: [0.52],
          status: 'needs_review',
          grid: { bpm: null, period_seconds: null, origin_seconds: null, meter: null, first_downbeat_beat: null, status: 'needs_review' },
        },
      },
    });

    const { container } = render(<AudioPlayerFooter />);
    await screen.findAllByTestId(/^(beat|downbeat)-marker$/);
    const markers = Array.from(container.querySelectorAll('[data-marker-kind]'));
    expect(markers).toHaveLength(2);
    expect(markers[0]).toHaveAttribute('data-marker-kind', 'downbeat');
    expect(markers[0]).toHaveAttribute('data-time', '0.52');
    expect(markers[1]).toHaveAttribute('data-time', '1');
  });

  it('retries_analysis_unavailable', async () => {
    const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    const pause = vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    const capturedAudio: { current: HTMLAudioElement | null } = { current: null };
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      capturedAudio.current = audio;
      return audio as any;
    });
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 20 });
    (api.preview.getMetadata as any)
      .mockResolvedValueOnce({
        track_id: 7,
        status: 'partial',
        revision: 1,
        waveform_status: 'complete',
        analysis_status: 'failed',
        waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
        key: null,
        camelot: null,
        bpm: null,
        error: null,
        analysis_error: 'model unavailable',
        analysis: null,
      })
      .mockResolvedValueOnce({
        track_id: 7,
        status: 'complete',
        revision: 3,
        waveform_status: 'complete',
        analysis_status: 'complete',
        waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
        key: null,
        camelot: null,
        bpm: null,
        error: null,
        analysis: {
          key: { key: 'C', camelot: '8B', status: 'reliable' },
          rhythm: { bpm: 120, beats: [], downbeats: [], status: 'reliable', grid: { bpm: 120, period_seconds: 0.5, origin_seconds: 0, meter: '4/4', first_downbeat_beat: 0, status: 'reliable' } },
        },
      });
    (api.preview as any).retryAnalysis.mockResolvedValue({
      track_id: 7,
      status: 'processing',
      revision: 2,
      waveform_status: 'complete',
      analysis_status: 'queued',
      waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis: null,
    });

    render(<AudioPlayerFooter />);
    expect(await screen.findByText('Analysis unavailable', {}, { timeout: 2500 })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(api.preview.getMetadata).toHaveBeenCalledTimes(1);
    const retry = screen.getByRole('button', { name: 'Retry analysis' });
    const seekSlider = screen.getByRole('slider', { name: 'Seek preview: T' });
    expect(seekSlider).toBeInTheDocument();
    fireEvent.keyDown(seekSlider, { key: 'ArrowRight' });
    expect(capturedAudio.current?.currentTime).toBe(5);
    fireEvent.click(retry);

    expect((api.preview as any).retryAnalysis).toHaveBeenCalledWith(7, expect.anything());
    expect(await screen.findByText('Ready', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(api.preview.getMetadata).toHaveBeenCalledTimes(2);
    expect(play).toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
  });

  it('does_not_offer_retry_for_unusable_analysis_without_failed_components', async () => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      return audio as any;
    });
    (api.preview.getStream as any).mockResolvedValue({ track_id: 7, stream_url: '/audio/7', duration: 20 });
    (api.preview.getMetadata as any).mockResolvedValue({
      track_id: 7,
      status: 'partial',
      revision: 2,
      waveform_status: 'complete',
      analysis_status: 'failed',
      waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis_error: 'local analysis returned no usable key or rhythm',
      analysis: {
        key: { key: null, camelot: null, status: 'unknown' },
        rhythm: {
          bpm: null,
          beats: [],
          downbeats: [],
          status: 'needs_review',
          grid: { bpm: null, period_seconds: null, origin_seconds: null, status: 'needs_review' },
        },
      },
    });

    render(<AudioPlayerFooter />);

    expect(await screen.findByText('Analysis unavailable', {}, { timeout: 2500 })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry analysis' })).not.toBeInTheDocument();
    expect(api.preview.retryAnalysis).not.toHaveBeenCalled();
  });

  it('ignores_snapshot_for_previous_preview', async () => {
    vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    vi.spyOn(window, 'Audio').mockImplementation((url?: string) => {
      const audio = document.createElement('audio');
      if (url) audio.src = url;
      return audio as any;
    });
    (api.preview.getStream as any).mockImplementation(async (trackId: number) => ({
      track_id: trackId,
      stream_url: `/audio/${trackId}`,
      duration: 20,
    }));
    const resolveSnapshot: Record<number, (snapshot: any) => void> = {};
    (api.preview.getMetadata as any).mockImplementation((trackId: number) => new Promise((resolve) => {
      resolveSnapshot[trackId] = resolve;
    }));

    const view = render(<AudioPlayerFooter />);
    await waitFor(() => expect(resolveSnapshot[7]).toBeDefined(), { timeout: 2500 });
    mockPreviewTrack.id = 8;
    mockPreviewTrack.title = 'Next';
    view.rerender(<AudioPlayerFooter />);
    await waitFor(() => expect(resolveSnapshot[8]).toBeDefined(), { timeout: 2500 });

    resolveSnapshot[7]({
      track_id: 7,
      status: 'partial',
      revision: 2,
      waveform_status: 'complete',
      analysis_status: 'failed',
      waveform: { bands: { low: [0.9], mid: [0.9], high: [0.9] }, colors: {}, duration: 99 },
      key: 'old',
      camelot: '8A',
      bpm: 99,
      error: null,
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText('Analysis unavailable')).not.toBeInTheDocument();
    expect(screen.queryByTestId('camelot-key')).not.toBeInTheDocument();

    resolveSnapshot[8]({
      track_id: 8,
      status: 'complete',
      revision: 1,
      waveform_status: 'complete',
      analysis_status: 'complete',
      waveform: { bands: { low: [0.5], mid: [0.4], high: [0.3] }, colors: {}, duration: 20 },
      key: null,
      camelot: null,
      bpm: null,
      error: null,
      analysis: {
        key: { key: 'C', camelot: '8B', status: 'reliable' },
        rhythm: { bpm: 120, beats: [], downbeats: [], status: 'reliable', grid: { bpm: 120, period_seconds: 0.5, origin_seconds: 0, meter: '4/4', first_downbeat_beat: 0, status: 'reliable' } },
      },
    });
    expect(await screen.findByText('Ready', {}, { timeout: 1000 })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Preview player: Playing Next by A' })).toBeInTheDocument();
  });

  it('retry_analysis_uses_authenticated_preview_route', async () => {
    const snapshot = {
      track_id: 7,
      status: 'processing',
      revision: 2,
      waveform: null,
      key: null,
      camelot: null,
      bpm: null,
      error: null,
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot });
    vi.stubGlobal('fetch', fetchMock);
    const actualApi = await vi.importActual<typeof import('../api')>('../api');
    const retry = (actualApi.preview as any).retryAnalysis;

    expect(retry).toBeTypeOf('function');
    await expect(retry(7)).resolves.toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith('/api/preview/7/analysis/retry', expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
    }));
  });
});
