import { useEffect, useLayoutEffect, useRef, useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import { preview } from '../api';
import type { WaveformData } from '../api';
import VolumeControl from './VolumeControl';
import { sliderToGain } from '../utils/audioMath';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function KeyBadge({ camelot }: { camelot: string | null }) {
  if (!camelot) return null;

  return (
    <span data-testid="camelot-key" className="preview-key-badge">
      {camelot}
    </span>
  );
}

function BPMBadge({ bpm }: { bpm: number | null }) {
  if (!bpm) return null;

  return (
    <span data-testid="bpm-badge" className="preview-bpm-badge">{Math.round(bpm)} BPM</span>
  );
}

export type WaveformMode = '3band' | 'rgb';

export interface WaveformPalette {
  low: string;
  mid: string;
  high: string;
}

export const WAVEFORM_PALETTES: Record<WaveformMode, WaveformPalette> = {
  '3band': { low: '#0054e2', mid: '#b3680a', high: '#f6ebd8' },
  rgb: { low: '#ff0844', mid: '#00e676', high: '#00b0ff' },
};

function drawClubWaveform(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  bands: WaveformData['bands'],
  progress: number,
  hoverFraction: number | null,
  wfDuration: number,
  mode: WaveformMode = '3band',
  palette: WaveformPalette = WAVEFORM_PALETTES[mode] || WAVEFORM_PALETTES['3band'],
) {
  // Clear and fill with pitch black background (genuine Rekordbox deck)
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, w, h);

  const centerY = h / 2;
  const scale = (h / 2) * 0.90;
  const end = bands.low.length;
  if (end === 0) return;
  const playedIdx = Math.floor(progress * end);

  const isRgb = mode === 'rgb';
  // Genuine Rekordbox 3Band:
  // - Low (Blue #0054e2): wide bass foundation (scale 1.0)
  // - Mid (Amber #b3680a): musical mid core (scale 0.68)
  // - High (Cream #f6ebd8): sharp transient spikes & continuous core (scale 0.85, min 1.5px)
  // Stacked solidly with source-over — no washed-out muddy bleeds.
  const specs: Record<string, { color: string; scale: number; minHeight: number; alpha: number; blend: GlobalCompositeOperation }> = isRgb
    ? {
        low:  { color: palette.low, scale: 1.00, minHeight: 0, alpha: 0.88, blend: 'source-over' },
        mid:  { color: palette.mid, scale: 0.85, minHeight: 0, alpha: 0.78, blend: 'lighter' },
        high: { color: palette.high, scale: 0.90, minHeight: 0, alpha: 0.82, blend: 'lighter' },
      }
    : {
        low:  { color: palette.low, scale: 1.00, minHeight: 0, alpha: 1.00, blend: 'source-over' },
        mid:  { color: palette.mid, scale: 0.68, minHeight: 0, alpha: 1.00, blend: 'source-over' },
        high: { color: palette.high, scale: 0.85, minHeight: 1.5, alpha: 1.00, blend: 'source-over' },
      };

  const buildPath = (data: number[], toIdx: number, bandScale: number = 1.0, minH: number = 0) => {
    const p = new Path2D();
    p.moveTo(0, centerY);
    const effScale = scale * bandScale;
    for (let i = 0; i <= toIdx; i++) {
      const val = Math.max(minH, data[i] * effScale);
      p.lineTo((i / end) * w, centerY - val);
    }
    p.lineTo((toIdx / end) * w, centerY);
    for (let i = toIdx; i >= 0; i--) {
      const val = Math.max(minH, data[i] * effScale);
      p.lineTo((i / end) * w, centerY + val);
    }
    p.closePath();
    return p;
  };

  // 1. Draw full waveform (dim background preview)
  for (const key of ['low', 'mid', 'high']) {
    const data = bands[key as keyof typeof bands];
    if (!data?.length) continue;
    const s = specs[key];
    ctx.globalAlpha = isRgb ? 0.20 : 0.28;
    ctx.globalCompositeOperation = isRgb ? 'lighter' : 'source-over';
    const path = buildPath(data, end - 1, s.scale, s.minHeight);
    ctx.fillStyle = s.color;
    ctx.fill(path);
  }

  // 2. Draw played portion (bright foreground) — clipped
  if (playedIdx > 0) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, (playedIdx / end) * w, h);
    ctx.clip();
    for (const key of ['low', 'mid', 'high']) {
      const s = specs[key];
      const data = bands[key as keyof typeof bands];
      if (!data?.length) continue;
      ctx.globalAlpha = s.alpha;
      ctx.globalCompositeOperation = s.blend;
      const path = buildPath(data, Math.min(playedIdx, end - 1), s.scale, s.minHeight);
      ctx.fillStyle = s.color;
      ctx.fill(path);
    }
    ctx.restore();
  }

  // Reset
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';

  // 3. Playhead
  if (playedIdx >= 0) {
    const px = (playedIdx / end) * w;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, h);
    ctx.stroke();
  }

  // 5. Hover: highlight region from playhead to cursor
  if (hoverFraction !== null && wfDuration > 0) {
    const hx = hoverFraction * w;
    const px = (playedIdx / end) * w;
    const left = Math.min(px, hx);
    const right = Math.max(px, hx);

    // Subtle brighten on the segment between playhead and cursor
    if (Math.abs(hx - px) > 2) {
      ctx.fillStyle = 'rgba(255,255,255,0.06)';
      ctx.fillRect(left, 0, right - left, h);
    }

    // Dashed guide line at cursor
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(hx, 0);
    ctx.lineTo(hx, h);
    ctx.stroke();
    ctx.setLineDash([]);

    const time = hoverFraction * wfDuration;
    const mins = Math.floor(time / 60);
    const secs = Math.floor(time % 60);
    const label = `${mins}:${secs.toString().padStart(2, '0')}`;

    ctx.font = '11px "JetBrains Mono", monospace';
    const textW = ctx.measureText(label).width + 8;
    const textH = 18;
    let tx = hx - textW / 2;
    tx = Math.max(2, Math.min(tx, w - textW - 2));
    const ty = 2;

    ctx.fillStyle = 'rgba(0,0,0,0.85)';
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(tx, ty, textW, textH, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, tx + textW / 2, ty + textH / 2);
  }
}

export default function AudioPlayerFooter() {
  const { state, dispatch } = useApp();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const artworkRef = useRef<HTMLDivElement | null>(null);
  const trackCopyRef = useRef<HTMLDivElement | null>(null);
  const previewDetailsRef = useRef<HTMLDivElement | null>(null);
  const previousLayoutRectsRef = useRef<{
    artwork: DOMRect | null;
    trackCopy: DOMRect | null;
    details: DOMRect | null;
  } | null>(null);
  const previewTokenRef = useRef(0);
  const { previewTrack, previewPlaying } = state;
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [waveform, setWaveform] = useState<WaveformData | null>(null);
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [keyCamelot, setKeyCamelot] = useState<string | null>(null);
  const [bpm, setBpm] = useState<number | null>(null);
  const DEFAULT_VOLUME = 0.8;
  const [waveformFailed, setWaveformFailed] = useState(false);
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [expandedPreviewTrackId, setExpandedPreviewTrackId] = useState<number | null>(null);
  const [volumeSlider, setVolumeSlider] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('tidal_preview_volume');
      if (saved !== null) {
        const val = parseFloat(saved);
        if (!isNaN(val) && val >= 0 && val <= 1) return val;
      }
    } catch {}
    return DEFAULT_VOLUME;
  });
  const [isMuted, setIsMuted] = useState<boolean>(() => {
    try {
      return localStorage.getItem('tidal_preview_muted') === 'true';
    } catch {
      return false;
    }
  });
  const prevVolumeRef = useRef<number>(volumeSlider > 0 ? volumeSlider : DEFAULT_VOLUME);

  useEffect(() => {
    if (!previewTrack) return;
    const trackId = previewTrack.id;
    const token = ++previewTokenRef.current;
    const abort = new AbortController();
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    setCurrentTime(0); setDuration(0); setWaveform(null); setWaveformFailed(false);
    setKeyCamelot(null); setBpm(null);

    const active = () => !cancelled && token === previewTokenRef.current;

    const poll = () => {
      pollTimer = setTimeout(async () => {
        if (!active()) return;
        try {
          const meta = await preview.getMetadata(trackId, abort.signal);
          if (!active()) return;
          if (meta.track_id !== trackId) return; // stale/mismatched snapshot: stop polling
          if (meta.waveform?.bands) setWaveform(meta.waveform);
          if (meta.camelot) setKeyCamelot(meta.camelot);
          if (meta.bpm) setBpm(meta.bpm);
          if (meta.status === 'failed') { setWaveformFailed(true); return; } // terminal failure
          if (meta.status === 'complete') return; // terminal: stop polling
          poll();
        } catch { /* transient error: retry next tick, keep placeholder */ poll(); }
      }, 750);
    };

    preview.getStream(trackId, abort.signal).then((r) => {
      if (!active()) return;
      const audio = new Audio(r.stream_url);
      audioRef.current = audio;
      const initialGain = isMuted ? 0 : sliderToGain(volumeSlider);
      audio.volume = Math.min(1, Math.max(0, initialGain));
      audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime));
      audio.addEventListener('loadedmetadata', () => setDuration(audio.duration));
      audio.addEventListener('ended', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.addEventListener('error', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.play().catch(() => dispatch({ type: 'CLEAR_PREVIEW' }));
      poll();
    }).catch(() => {
      if (active()) dispatch({ type: 'CLEAR_PREVIEW' });
    });

    return () => {
      cancelled = true;
      abort.abort(); // cancel any in-flight preview requests on track change/close
      if (pollTimer) clearTimeout(pollTimer);
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [previewTrack?.id]);

  useEffect(() => {
    if (!previewTrack) {
      audioRef.current?.pause();
      audioRef.current = null;
    }
  }, [previewTrack]);

  useEffect(() => {
    setMobileExpanded(false);
  }, [previewTrack?.id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !waveform?.bands) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    canvas.width = rect.width;
    canvas.height = rect.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const wfDuration = waveform.duration || duration;
    const progress = wfDuration > 0 ? currentTime / wfDuration : 0;
    const mode = (state.settings?.waveform_color as WaveformMode) || '3band';
    drawClubWaveform(ctx, rect.width, rect.height, waveform.bands, Math.min(1, progress), hoverFraction, wfDuration, mode);
  }, [currentTime, waveform, duration, hoverFraction, state.settings?.waveform_color]);

  useEffect(() => {
    if (audioRef.current) {
      const currentGain = isMuted ? 0 : sliderToGain(volumeSlider);
      audioRef.current.volume = Math.min(1, Math.max(0, currentGain));
    }
  }, [volumeSlider, isMuted]);

  const handleVolumeChange = useCallback((newVal: number) => {
    const clamped = Math.max(0, Math.min(1, newVal));
    setVolumeSlider(clamped);
    try {
      localStorage.setItem('tidal_preview_volume', String(clamped));
    } catch {}
    if (clamped > 0) {
      prevVolumeRef.current = clamped;
      if (isMuted) {
        setIsMuted(false);
        try {
          localStorage.setItem('tidal_preview_muted', 'false');
        } catch {}
      }
    }
  }, [isMuted]);

  const toggleMute = useCallback(() => {
    if (isMuted) {
      setIsMuted(false);
      try {
        localStorage.setItem('tidal_preview_muted', 'false');
      } catch {}
      if (volumeSlider === 0) {
        const restored = prevVolumeRef.current > 0 ? prevVolumeRef.current : 0.8;
        setVolumeSlider(restored);
        try {
          localStorage.setItem('tidal_preview_volume', String(restored));
        } catch {}
      }
    } else {
      if (volumeSlider > 0) {
        prevVolumeRef.current = volumeSlider;
      }
      setIsMuted(true);
      try {
        localStorage.setItem('tidal_preview_muted', 'true');
      } catch {}
    }
  }, [isMuted, volumeSlider]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play();
      dispatch({ type: 'SET_PREVIEW_PLAYING', payload: true });
    } else {
      audio.pause();
      dispatch({ type: 'SET_PREVIEW_PLAYING', payload: false });
    }
  }, [dispatch]);

  // Keyboard shortcut support
  useEffect(() => {
    const handler = () => togglePlay();
    window.addEventListener('preview-toggle-play', handler);
    return () => window.removeEventListener('preview-toggle-play', handler);
  }, [togglePlay]);

  useEffect(() => {
    const handler = () => toggleMute();
    window.addEventListener('preview-toggle-mute', handler);
    return () => window.removeEventListener('preview-toggle-mute', handler);
  }, [toggleMute]);

  const close = useCallback(() => {
    dispatch({ type: 'CLEAR_PREVIEW' });
  }, [dispatch]);

  const seekToFraction = useCallback((fraction: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const wfDuration = waveform?.duration || duration;
    if (!wfDuration) return;
    audio.currentTime = Math.max(0, Math.min(1, fraction)) * wfDuration;
  }, [duration, waveform]);

  const seek = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    seekToFraction((e.clientX - rect.left) / rect.width);
  }, [seekToFraction]);

  const seekWithKeyboard = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const wfDuration = waveform?.duration || duration;
    if (!wfDuration) return;

    let nextTime: number | null = null;
    if (e.key === 'ArrowLeft') nextTime = currentTime - 5;
    if (e.key === 'ArrowRight') nextTime = currentTime + 5;
    if (e.key === 'Home') nextTime = 0;
    if (e.key === 'End') nextTime = wfDuration;
    if (nextTime === null) return;

    e.preventDefault();
    seekToFraction(nextTime / wfDuration);
  }, [currentTime, duration, seekToFraction, waveform]);

  const playerExpanded = !!previewTrack && expandedPreviewTrackId === previewTrack.id;

  useLayoutEffect(() => {
    const previousRects = previousLayoutRectsRef.current;
    previousLayoutRectsRef.current = null;
    if (!previousRects || typeof Element === 'undefined' || typeof Element.prototype.animate !== 'function') return;

    const reducedMotion = typeof window !== 'undefined'
      ? window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
      : true;
    if (reducedMotion) return;

    const animateFromPreviousPosition = (element: HTMLDivElement | null, previousRect: DOMRect | null) => {
      if (!element || !previousRect || previousRect.width === 0 || previousRect.height === 0) return;

      const nextRect = element.getBoundingClientRect();
      if (nextRect.width === 0 || nextRect.height === 0) return;

      element.animate([
        {
          transform: `translate3d(${previousRect.left - nextRect.left}px, ${previousRect.top - nextRect.top}px, 0)`,
          width: `${previousRect.width}px`,
          height: `${previousRect.height}px`,
        },
        {
          transform: 'translate3d(0, 0, 0)',
          width: `${nextRect.width}px`,
          height: `${nextRect.height}px`,
        },
      ], {
        duration: 240,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      });
    };

    animateFromPreviousPosition(artworkRef.current, previousRects.artwork);
    animateFromPreviousPosition(trackCopyRef.current, previousRects.trackCopy);
    animateFromPreviousPosition(previewDetailsRef.current, previousRects.details);
  }, [playerExpanded]);

  if (!previewTrack) return null;

  const waveformMode = (state.settings?.waveform_color as WaveformMode) || '3band';
  const totalDuration = waveform?.duration || duration;
  const detailVisibility = playerExpanded || mobileExpanded ? 'block' : 'hidden md:block';
  const secondaryVisibility = playerExpanded || mobileExpanded ? 'flex' : 'hidden md:flex';

  const toggleExpandedPreview = () => {
    const reducedMotion = typeof window !== 'undefined'
      ? window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
      : true;
    const canAnimate = !reducedMotion
      && typeof Element !== 'undefined'
      && typeof Element.prototype.animate === 'function';

    previousLayoutRectsRef.current = canAnimate ? {
      artwork: artworkRef.current?.getBoundingClientRect() ?? null,
      trackCopy: trackCopyRef.current?.getBoundingClientRect() ?? null,
      details: previewDetailsRef.current?.getBoundingClientRect() ?? null,
    } : null;

    setMobileExpanded(false);
    setExpandedPreviewTrackId(playerExpanded ? null : previewTrack.id);
  };

  return (
    <div
      role="region"
      aria-label={`Preview player: ${previewPlaying ? 'Playing' : 'Paused'} ${previewTrack.title} by ${previewTrack.artist}`}
      className={`preview-player fixed bottom-0 left-0 right-0 z-50 px-3 py-2 sm:px-4${playerExpanded ? ' is-expanded' : ''}`}
      style={{
        background: 'var(--glass-bg)',
        borderTop: '1px solid var(--glass-border)',
        boxShadow: '0 -12px 32px rgba(11, 13, 18, 0.24)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <span data-testid="waveform-color-mode" className="hidden">{waveformMode}</span>
      <div id="preview-player-main" className="preview-player-main">
      <div id="preview-player-details" ref={previewDetailsRef} className={`preview-player-details ${detailVisibility}`}>
        <div className="preview-player-instrument">
          <div className="preview-player-waveform">
            {waveform ? (
              <canvas
                ref={canvasRef}
                role="slider"
                tabIndex={0}
                aria-label={`Seek preview: ${previewTrack.title}`}
                aria-valuemin={0}
                aria-valuemax={totalDuration}
                aria-valuenow={Math.min(currentTime, totalDuration)}
                aria-valuetext={`${formatTime(currentTime)} of ${formatTime(totalDuration)}`}
                onClick={seek}
                onKeyDown={seekWithKeyboard}
                onMouseMove={(e) => {
                  const c = canvasRef.current;
                  if (!c) return;
                  const r = c.getBoundingClientRect();
                  setHoverFraction(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)));
                }}
                onMouseLeave={() => setHoverFraction(null)}
                className="preview-waveform-canvas w-full cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-offset-2"
                style={{ display: 'block', height: '44px', background: '#000000', border: '1px solid rgba(255,255,255,0.06)' }}
              />
            ) : waveformFailed ? (
              <div className="preview-waveform-placeholder" role="status" aria-live="polite">
                <span>waveform unavailable</span>
              </div>
            ) : (
              <div className="preview-waveform-placeholder animate-pulse" aria-label="Loading waveform" role="status" />
            )}
          </div>
          <div id="preview-player-secondary" className={`preview-player-meta ${secondaryVisibility} items-center shrink-0`}>
            <KeyBadge camelot={keyCamelot} />
            <BPMBadge bpm={bpm} />
          </div>
        </div>
        <div className="preview-player-mobile-volume sm:hidden">
          <span className="text-xs font-mono" style={{ color: 'var(--text-dim)' }}>Volume</span>
          <VolumeControl
            sliderValue={volumeSlider}
            isMuted={isMuted}
            onSliderChange={handleVolumeChange}
            onToggleMute={toggleMute}
            showReadout={true}
          />
        </div>
      </div>
          {previewTrack.cover_url ? (
            <div ref={artworkRef} className="preview-player-artwork-cluster">
              <img
                src={previewTrack.cover_url}
                alt=""
                className="preview-player-artwork w-9 h-9 rounded object-cover shrink-0"
                style={{ border: '1px solid var(--glass-border)' }}
              />
              <button
                type="button"
                className="preview-player-expand-button preview-player-artwork-overlay"
                onClick={toggleExpandedPreview}
                aria-label={`${playerExpanded ? 'Collapse' : 'Expand'} preview player`}
                aria-expanded={playerExpanded}
                aria-controls="preview-player-main preview-player-details"
                title={`${playerExpanded ? 'Collapse' : 'Expand'} preview player`}
              >
                <svg
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  data-direction={playerExpanded ? 'down' : 'up'}
                  aria-hidden="true"
                >
                  {playerExpanded ? (
                    <path d="M12 5v14m-7-7 7 7 7-7" />
                  ) : (
                    <path d="M12 19V5m-7 7 7-7 7 7" />
                  )}
                </svg>
              </button>
            </div>
          ) : (
            <div
              ref={artworkRef}
              data-testid="preview-artwork-fallback"
              className="preview-player-artwork-cluster preview-player-artwork w-9 h-9 rounded shrink-0 flex items-center justify-center"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
            >
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9.5 11.5V3l4-1v8.5" /><path d="M9.5 5 13.5 4" /><ellipse cx="6" cy="12" rx="2" ry="1.5" /><ellipse cx="12" cy="10.5" rx="2" ry="1.5" /></svg>
            </div>
          )}
          <div ref={trackCopyRef} className="preview-player-track-copy">
            <p className="preview-player-track-title text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
              {previewTrack.title}
            </p>
            {typeof previewTrack.artist_id === 'number' ? (
              <button
                type="button"
                className="preview-player-track-artist preview-player-track-artist-link text-xs truncate"
                aria-label={`Open artist ${previewTrack.artist}`}
                onClick={() => dispatch({ type: 'REQUEST_ARTIST_DETAIL', payload: previewTrack.artist_id! })}
              >
                {previewTrack.artist}
              </button>
            ) : (
              <p className="preview-player-track-artist text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                {previewTrack.artist}
              </p>
            )}
          </div>

        <div className="preview-player-controls">
          <VolumeControl
            sliderValue={volumeSlider}
            isMuted={isMuted}
            onSliderChange={handleVolumeChange}
            onToggleMute={toggleMute}
            className="preview-player-desktop-volume hidden sm:flex"
          />
          {/* Quick mute button on mobile */}
          <button
            type="button"
            onClick={toggleMute}
            className="preview-player-mute sm:hidden p-2 rounded transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{ color: isMuted ? 'var(--danger, #E11D48)' : 'var(--text-muted)' }}
            aria-label={isMuted ? 'Unmute preview' : 'Mute preview'}
            aria-pressed={isMuted}
            title={isMuted ? 'Unmute preview (M)' : 'Mute preview (M)'}
          >
            {isMuted || volumeSlider === 0 ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <line x1="23" y1="9" x2="17" y2="15" />
                <line x1="17" y1="9" x2="23" y2="15" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
            )}
          </button>
          <span className={`preview-player-time ${mobileExpanded ? 'inline' : 'hidden md:inline'} mono text-xs`} style={{ color: 'var(--text-dim)' }} aria-label={`Preview time ${formatTime(currentTime)} of ${formatTime(duration)}`}>
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <span className="sr-only" aria-live="polite">
            {previewPlaying ? 'Playing preview' : 'Preview paused'}
          </span>
          {!playerExpanded && (
            <button
              type="button"
              onClick={() => setMobileExpanded((expanded) => !expanded)}
              className="preview-player-details-toggle md:hidden p-2 rounded transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-2"
              aria-label={mobileExpanded ? 'Hide preview details' : 'Show preview details'}
              aria-expanded={mobileExpanded}
              aria-controls="preview-player-details preview-player-secondary"
              style={{ color: 'var(--text-muted)', background: mobileExpanded ? 'var(--accent-dim)' : 'transparent' }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <polyline points={mobileExpanded ? '3,9 7,5 11,9' : '3,5 7,9 11,5'} />
              </svg>
            </button>
          )}
          <button
            type="button"
            onClick={togglePlay}
            className="preview-player-play p-2 rounded-full transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2"
            aria-label={previewPlaying ? 'Pause preview' : 'Play preview'}
            aria-pressed={previewPlaying}
            style={{
              color: 'var(--text-bright)',
              background: 'var(--accent-dim)',
              border: '1px solid rgba(0, 229, 199, 0.2)',
            }}
          >
            {previewPlaying ? (
              <svg width="14" height="14" viewBox="0 0 10 10" fill="currentColor">
                <rect x="1" y="0" width="3" height="10" rx="0.5" />
                <rect x="6" y="0" width="3" height="10" rx="0.5" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 10 10" fill="currentColor">
                <polygon points="1,0 9,5 1,10" />
              </svg>
            )}
          </button>
          <button
            type="button"
            onClick={close}
            className="preview-player-close p-2 rounded-full transition-all duration-200 focus-visible:outline-2 focus-visible:outline-offset-2"
            aria-label="Close preview player"
            style={{ color: 'var(--text-dim)' }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="3" y1="3" x2="11" y2="11" />
              <line x1="11" y1="3" x2="3" y2="11" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
