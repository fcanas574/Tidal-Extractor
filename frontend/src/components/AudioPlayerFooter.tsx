import { useEffect, useRef, useCallback, useState } from 'react';
import { useApp } from '../context/AppContext';
import { preview } from '../api';
import type { WaveformData } from '../api';

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function drawClubWaveform(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  bands: WaveformData['bands'],
  progress: number,
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
}

export default function AudioPlayerFooter() {
  const { state, dispatch } = useApp();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { previewTrack, previewPlaying } = state;
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [waveform, setWaveform] = useState<WaveformData | null>(null);

  useEffect(() => {
    if (!previewTrack) return;
    let cancelled = false;
    setCurrentTime(0);
    setDuration(0);
    setWaveform(null);

    preview.getUrl(previewTrack.id).then((r) => {
      if (cancelled) return;
      if (r.waveform?.bands) setWaveform(r.waveform);
      const audio = new Audio(r.stream_url);
      audioRef.current = audio;
      audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime));
      audio.addEventListener('loadedmetadata', () => setDuration(audio.duration));
      audio.addEventListener('ended', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.addEventListener('error', () => dispatch({ type: 'CLEAR_PREVIEW' }));
      audio.play().catch(() => dispatch({ type: 'CLEAR_PREVIEW' }));
    });

    return () => {
      cancelled = true;
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
    drawClubWaveform(ctx, rect.width, rect.height, waveform.bands, Math.min(1, progress));
  }, [currentTime, waveform, duration]);

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
