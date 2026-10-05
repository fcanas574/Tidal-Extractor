import type { QueueItem } from '../api';

export type DownloadStatus = QueueItem['status'] | 'idle';

function DownloadIcon() {
  return <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10 2.5v9m0 0 3.2-3.2M10 11.5 6.8 8.3M3.5 14.5v2h13v-2" /></svg>;
}

function PendingIcon() {
  return <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="10" cy="10" r="7" /><path d="M10 6v4l2.5 1.5" /></svg>;
}

function CheckIcon() {
  return <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="10" cy="10" r="7.2" /><path d="m6.5 10 2.2 2.2 4.8-5" /></svg>;
}

function ProgressIcon({ progress }: { progress: number }) {
  const value = Math.max(0, Math.min(100, progress));
  const radius = 11;
  const circumference = 2 * Math.PI * radius;
  return (
    <span className="download-progress-icon" aria-hidden="true">
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" strokeLinecap="round">
        <circle cx="16" cy="16" r={radius} stroke="currentColor" strokeOpacity=".2" strokeWidth="2.4" />
        <circle cx="16" cy="16" r={radius} stroke="currentColor" strokeWidth="2.4" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - value / 100)} transform="rotate(-90 16 16)" />
      </svg>
      <span>{Math.round(value)}</span>
    </span>
  );
}

export default function DownloadButton({
  title,
  status = 'idle',
  progress = 0,
  error,
  onDownload,
  className = '',
}: {
  title: string;
  status?: DownloadStatus;
  progress?: number;
  error?: string | null;
  onDownload: () => void;
  className?: string;
}) {
  const active = status === 'queued' || status === 'downloading';
  const label = status === 'complete'
    ? `Download complete for ${title}`
    : status === 'queued'
      ? `Download queued for ${title}`
      : status === 'downloading'
        ? `Downloading ${title}, ${Math.round(progress)} percent`
        : status === 'failed'
          ? `Retry download ${title}`
          : `Download ${title}`;

  return (
    <button
      type="button"
      className={`download-control download-control-${status}${className ? ` ${className}` : ''}`}
      onClick={(event) => { event.stopPropagation(); onDownload(); }}
      disabled={active || status === 'complete'}
      aria-label={label}
      title={error && status === 'failed' ? `${error}. Retry download` : label}
      aria-busy={active || undefined}
    >
      {status === 'queued' && <PendingIcon />}
      {status === 'downloading' && <ProgressIcon progress={progress} />}
      {status === 'complete' && <CheckIcon />}
      {status === 'failed' && <span aria-hidden="true" className="download-retry-glyph">↻</span>}
      {status === 'idle' && <DownloadIcon />}
      <span className="sr-only">{status === 'failed' ? 'Download failed. ' : ''}{label}</span>
    </button>
  );
}
