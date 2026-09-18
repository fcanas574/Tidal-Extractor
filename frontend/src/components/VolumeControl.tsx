import { useState, useRef, useCallback } from 'react';
import { sliderToDb, formatDb } from '../utils/audioMath';

interface VolumeControlProps {
  sliderValue: number; // [0, 1]
  isMuted: boolean;
  onSliderChange: (value: number) => void;
  onToggleMute: () => void;
  className?: string;
  showReadout?: boolean;
}

export default function VolumeControl({
  sliderValue,
  isMuted,
  onSliderChange,
  onToggleMute,
  className = '',
  showReadout = false,
}: VolumeControlProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const sliderRef = useRef<HTMLInputElement>(null);

  const effectiveSlider = isMuted ? 0 : sliderValue;
  const fillPercent = Math.round(effectiveSlider * 100);
  const currentDb = isMuted ? -Infinity : sliderToDb(sliderValue);
  const formattedDb = formatDb(currentDb);
  const tooltipText = isMuted
    ? 'Muted (-inf dB)'
    : `${fillPercent}% (${formattedDb})`;

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        onToggleMute();
      }
    },
    [onToggleMute]
  );

  const trackBg = `linear-gradient(to right, var(--text-bright) 0%, var(--text-bright) ${fillPercent}%, rgba(255, 255, 255, 0.16) ${fillPercent}%, rgba(255, 255, 255, 0.16) 100%)`;

  return (
    <div
      className={`relative flex items-center gap-1.5 ${className}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Mute/Unmute button */}
      <button
        type="button"
        onClick={onToggleMute}
        className="p-1.5 rounded-full transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 shrink-0"
        style={{
          color: isMuted ? 'var(--danger, #E11D48)' : 'var(--text-muted)',
          background: 'transparent',
        }}
        aria-label={isMuted ? 'Unmute preview' : 'Mute preview'}
        aria-pressed={isMuted}
        title={isMuted ? 'Unmute preview (M)' : 'Mute preview (M)'}
      >
        {isMuted || effectiveSlider === 0 ? (
          /* Muted speaker with X */
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <line x1="23" y1="9" x2="17" y2="15" />
            <line x1="17" y1="9" x2="23" y2="15" />
          </svg>
        ) : effectiveSlider <= 0.5 ? (
          /* Low volume speaker */
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          </svg>
        ) : (
          /* High volume speaker */
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
        )}
      </button>

      {/* Slider container */}
      <div className="relative flex items-center">
        {/* Floating tooltip on hover / focus */}
        {(isHovered || isFocused) && (
          <div
            role="tooltip"
            className="absolute -top-7 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded text-[10px] font-mono whitespace-nowrap pointer-events-none shadow-md"
            style={{
              background: 'var(--graphite, #121214)',
              color: 'var(--text-bright, #FAFAFA)',
              border: '1px solid var(--glass-border, rgba(255,255,255,0.1))',
              zIndex: 60,
            }}
          >
            {tooltipText}
          </div>
        )}

        <input
          ref={sliderRef}
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={effectiveSlider}
          onChange={(e) => onSliderChange(parseFloat(e.target.value))}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          className="volume-slider w-16 sm:w-20 md:w-24"
          style={{ '--track-bg': trackBg } as React.CSSProperties}
          aria-label="Preview volume"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={fillPercent}
          aria-valuetext={tooltipText}
          title={tooltipText}
        />
      </div>

      {/* Optional persistent dB readout badge for audiophiles */}
      {showReadout && (
        <span
          className="font-mono text-[11px] shrink-0 min-w-[50px] text-right"
          style={{ color: 'var(--text-dim)' }}
        >
          {isMuted ? 'Muted' : formattedDb}
        </span>
      )}
    </div>
  );
}
