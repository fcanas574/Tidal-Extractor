import { useEffect, useRef, useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import { preview } from '../api';
import type { WaveformData } from '../api';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// Key badge with rainbow gradient animation when playing
function KeyBadge({ camelot, playing }: { camelot: string | null; playing: boolean }) {
  if (!camelot) return null;

  return (
    <div
      key={playing ? 'playing' : 'paused'}
      className="ml-3 px-2 py-0.5 rounded text-xs font-mono shrink-0"
      style={{
        background: playing
          ? 'linear-gradient(90deg, #ff0000, #ff7f00, #ffff00, #00ff00, #0000ff, #8b00ff, #ff0000)'
          : 'var(--accent-dim)',
        backgroundSize: '200% 100%',
        animation: playing ? 'rainbow 1.5s linear infinite' : 'none',
        color: playing ? '#000' : 'var(--text-bright)',
        border: `1px solid ${playing ? 'rgba(255,255,255,0.3)' : 'rgba(0, 229, 199, 0.2)'}`,
        textShadow: playing ? 'none' : '0 1px 2px rgba(0,0,0,0.3)',
      }}
    >
      {camelot}
    </div>
  );
}

// BPM badge - subtle display with beat animation
function BPMBadge({ bpm, playing }: { bpm: number | null; playing: boolean }) {
  if (!bpm) return null;

  // Calculate animation duration based on BPM (60 seconds / BPM = seconds per beat)
  const beatDuration = bpm > 0 ? 60 / bpm : 0;

  return (
    <div
      className="ml-2 px-2 py-0.5 rounded text-xs font-mono shrink-0 relative overflow-hidden"
      style={{
        background: 'var(--bg-surface)',
        color: 'var(--text-muted)',
        border: '1px solid rgba(255,255,255,0.1)',
      }}
    >
      {/* Animated beat line - rises from bottom on each beat */}
      {playing && beatDuration > 0 && (
        <div
          key="beat-animation"
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: '100%',
            background: 'linear-gradient(to top, rgba(0, 229, 199, 0.5), transparent)',
            animation: `beatPulse ${beatDuration}s ease-in-out infinite`,
            pointerEvents: 'none',
          }}
        />
      )}
      <span style={{ position: 'relative', zIndex: 1 }}>
        {Math.round(bpm)} BPM
      </span>
    </div>
  );
}

function drawClubWaveform(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  bands: WaveformData['bands'],
  progress: number,
  hoverFraction: number | null,
  wfDuration: number,
) {
  ctx.clearRect(0, 0, w, h);

  const centerY = h / 2;
  const scale = (h / 2) * 0.85;
  const end = bands.low.length;
  if (end === 0) return;
  const playedIdx = Math.floor(progress * end);

  const specs: Record<string, { color: string; alpha: number; blend: GlobalCompositeOperation }> = {
    low:  { color: '#0055e2', alpha: 0.85, blend: 'source-over' },
    mid:  { color: '#f2aa3c', alpha: 0.70, blend: 'lighter' },
    high: { color: '#ffffff', alpha: 0.90, blend: 'lighter' },
  };

  const buildPath = (data: number[], toIdx: number) => {
    const p = new Path2D();
    p.moveTo(0, centerY);
    for (let i = 0; i <= toIdx; i++) {
      p.lineTo((i / end) * w, centerY - data[i] * scale);
    }
    p.lineTo((toIdx / end) * w, centerY);
    for (let i = toIdx; i >= 0; i--) {
      p.lineTo((i / end) * w, centerY - (-data[i]) * scale);
    }
    p.closePath();
    return p;
  };

  // 1. Draw full waveform (dim)
  for (const key of ['low', 'mid', 'high']) {
    const data = bands[key as keyof typeof bands];
    if (!data?.length) continue;
    ctx.globalAlpha = 0.15;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = specs[key].color;
    ctx.fill(buildPath(data, end - 1));
    ctx.strokeStyle = specs[key].color;
    ctx.lineWidth = 0.5;
    ctx.stroke(buildPath(data, end - 1));
  }

  // 2. Draw played portion (bright) — clipped
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
      ctx.fillStyle = s.color;
      ctx.fill(buildPath(data, Math.min(playedIdx, end - 1)));
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 0.5;
      ctx.stroke(buildPath(data, Math.min(playedIdx, end - 1)));
    }
    ctx.restore();
  }

  // Reset
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';

  // 3. Center line
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  ctx.lineTo(w, centerY);
  ctx.stroke();

  // 4. Playhead
  if (playedIdx >= 0) {
    const px = (playedIdx / end) * w;
    ctx.strokeStyle = 'rgba(255,255,255,0.60)';
    ctx.lineWidth = 1;
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
  // Monotonic preview token: each preview-effect run captures its own value so a
  // /metadata response arriving after the preview was superseded is rejected.
  const previewTokenRef = useRef(0);
  const { previewTrack, previewPlaying } = state;
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [waveform, setWaveform] = useState<WaveformData | null>(null);
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [keyCamelot, setKeyCamelot] = useState<string | null>(null);
  const [bpm, setBpm] = useState<number | null>(null);

  useEffect(() => {
    if (!previewTrack) return;
    const trackId = previewTrack.id;
    // Monotonic preview token: each effect run captures its own token so a
    // metadata response for a superseded track is rejected before it reaches
    // state. Increment on every run.
    previewTokenRef.current += 1;
    const token = previewTokenRef.current;

    let cancelled = false;
    const streamAbort = new AbortController();
    const metadataAbort = new AbortController();

    setCurrentTime(0);
    setDuration(0);
    setWaveform(null);
    setKeyCamelot(null);
    setBpm(null);

    // Start audio IMMEDIATELY from the fast /stream response. The slow analysis
    // (waveform/key/bpm) arrives later via /metadata polling and is applied as
    // it lands — playback must never block on it.
    preview.getStream(trackId).then((r) => {
      if (cancelled || streamAbort.signal.aborted) return;
      if (r.stream_url == null) {
        dispatch({ type: 'CLEAR_PREVIEW' });
        dispatch({
          type: 'ADD_TOAST',
          payload: {
            id: `preview-err-${trackId}`,
            type: 'error',
            title: 'Preview unavailable',
            detail: 'No stream URL returned',
          },
        });
        return;
      }
      const audio = new Audio(r.stream_url);
      audioRef.current = audio;
      audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime));
      audio.addEventListener('loadedmetadata', () => setDuration(audio.duration));
      audio.addEventListener('ended', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.addEventListener('error', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.play().catch(() => dispatch({ type: 'CLEAR_PREVIEW' }));
    }).catch((err: unknown) => {
      if (cancelled) return;
      streamAbort.abort();
      dispatch({ type: 'CLEAR_PREVIEW' });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `preview-err-${trackId}`,
          type: 'error',
          title: 'Preview unavailable',
          detail: err instanceof Error ? err.message : 'Stream request failed',
        },
      });
    });

    // Poll /metadata every 750ms while status is non-terminal. Apply a
    // snapshot ONLY when the run is not cancelled, its track_id still matches
    // the active preview, and the local token matches (guards against a
    // superseding preview whose stale /metadata response arrives late).
    const poll = async () => {
      while (!cancelled && !metadataAbort.signal.aborted) {
        try {
          const snap = await preview.getMetadata(trackId);
          if (cancelled || metadataAbort.signal.aborted) return;
          // Reject stale responses: superseded track (previewTrack changed) or
          // a response from a prior token attempting to apply.
          if (previewTrack?.id !== trackId || token !== previewTokenRef.current) return;
          if (snap.track_id !== trackId || token !== previewTokenRef.current) return;
          if (snap.waveform?.bands) setWaveform(snap.waveform);
          if (snap.camelot) setKeyCamelot(snap.camelot);
          if (snap.bpm != null) setBpm(snap.bpm);
          if (snap.status === 'complete' || snap.status === 'failed') {
            return;
          }
        } catch (err: unknown) {
          if (cancelled) return;
          // Metadata failure is non-blocking: leave audio playing, surface a
          // non-blocking error toast, and stop polling.
          dispatch({
            type: 'ADD_TOAST',
            payload: {
              id: `preview-metadata-err-${trackId}`,
              type: 'error',
              title: 'Preview metadata unavailable',
              detail: err instanceof Error ? err.message : 'Metadata request failed',
            },
          });
          return;
        }
        await new Promise<void>((resolve) => {
          const id = setTimeout(resolve, 750);
          metadataAbort.signal.addEventListener('abort', () => {
            clearTimeout(id);
            resolve();
          }, { once: true });
        });
        if (cancelled || metadataAbort.signal.aborted) return;
      }
    };
    void poll();

    return () => {
      cancelled = true;
      streamAbort.abort();
      metadataAbort.abort();
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
    drawClubWaveform(ctx, rect.width, rect.height, waveform.bands, Math.min(1, progress), hoverFraction, wfDuration);
  }, [currentTime, waveform, duration, hoverFraction]);

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

  const close = useCallback(() => {
    dispatch({ type: 'CLEAR_PREVIEW' });
  }, [dispatch]);

  const seek = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas) return;
    const wfDuration = waveform?.duration || duration;
    if (!wfDuration) return;
    const rect = canvas.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    audio.currentTime = fraction * wfDuration;
  }, [duration, waveform]);

  if (!previewTrack) return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-50 px-4 py-2"
      style={{
        background: '#060f24',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        backdropFilter: 'blur(16px)',
      }}
    >
      <canvas
        ref={canvasRef}
        onClick={seek}
        onMouseMove={(e) => {
          const c = canvasRef.current;
          if (!c) return;
          const r = c.getBoundingClientRect();
          setHoverFraction(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)));
        }}
        onMouseLeave={() => setHoverFraction(null)}
        className="w-full mb-2 cursor-pointer"
        style={{ display: 'block', height: '56px' }}
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {previewTrack.cover_url ? (
            <img
              src={previewTrack.cover_url}
              alt=""
              className="w-9 h-9 rounded object-cover shrink-0"
              style={{ border: '1px solid var(--glass-border)' }}
            />
          ) : (
            <div
              className="w-9 h-9 rounded shrink-0 flex items-center justify-center"
              style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
            >
              &#9835;
            </div>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
              {previewTrack.title}
            </p>
            <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
              {previewTrack.artist}
            </p>
          </div>
          <KeyBadge camelot={keyCamelot} playing={previewPlaying} />
          <BPMBadge bpm={bpm} playing={previewPlaying} />
        </div>

        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="mono text-xs" style={{ color: 'var(--text-dim)' }}>
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <button
            onClick={togglePlay}
            className="p-2 rounded-full transition-all duration-200"
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
            onClick={close}
            className="p-2 rounded-full transition-all duration-200"
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
