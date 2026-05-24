import { useState, useEffect, useRef, useCallback } from 'react';
import { beatport, queue } from '../api';
import { useApp } from '../context/AppContext';
import type { BeatportGenre, BeatportTrack, MatchResult, MatchCandidate } from '../api';
import MatchConfirmDialog from './MatchConfirmDialog';

export default function BeatportView() {
  const { state, dispatch } = useApp();
  const [genres, setGenres] = useState<BeatportGenre[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<number | null>(null);
  const [tracks, setTracks] = useState<BeatportTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [beatportAuth, setBeatportAuth] = useState<boolean | null>(null);
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [previewTrackId, setPreviewTrackId] = useState<number | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [matchingTrackId, setMatchingTrackId] = useState<number | null>(null);
  const [confirmTrack, setConfirmTrack] = useState<BeatportTrack | null>(null);
  const [confirmCandidates, setConfirmCandidates] = useState<MatchCandidate[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Check Beatport auth on mount
  useEffect(() => {
    beatport.authStatus().then((r) => setBeatportAuth(r.authenticated));
  }, []);

  // Load genres
  useEffect(() => {
    beatport
      .genres()
      .then((r) => {
        setGenres(r.genres);
        if (r.genres.length > 0) setSelectedGenre(r.genres[0].id);
        setLoading(false);
      })
      .catch(() => {
        setError('Failed to load genres');
        setLoading(false);
      });
  }, []);

  // Load tracks when genre changes
  useEffect(() => {
    if (selectedGenre === null) return;
    setLoading(true);
    setError(null);
    beatport
      .tracks(selectedGenre)
      .then((r) => {
        setTracks(r.tracks);
        setLoading(false);
      })
      .catch(() => {
        setError('Failed to load tracks');
        setLoading(false);
      });
  }, [selectedGenre]);

  const handlePreview = useCallback(async (track: BeatportTrack) => {
    if (previewTrackId === track.id) {
      audioRef.current?.pause();
      setPreviewTrackId(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewTrackId(track.id);
    try {
      const r = await beatport.preview(track.id);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(r.stream_url);
      audioRef.current = audio;
      audio.play();
      audio.onended = () => setPreviewTrackId(null);
      audio.onerror = () => {
        setPreviewTrackId(null);
        dispatch({
          type: 'ADD_TOAST',
          payload: { id: `prev-err-${Date.now()}`, type: 'error', title: 'Preview failed' },
        });
      };
    } catch {
      setPreviewTrackId(null);
      dispatch({
        type: 'ADD_TOAST',
        payload: { id: `prev-err-${Date.now()}`, type: 'error', title: 'Preview unavailable' },
      });
    } finally {
      setPreviewLoading(false);
    }
  }, [previewTrackId, dispatch]);

  const handleDownload = useCallback(async (track: BeatportTrack) => {
    setMatchingTrackId(track.id);
    try {
      const result: MatchResult = await beatport.match({
        id: track.id,
        name: track.name,
        mix_name: track.mix_name,
        artists: track.artists,
        remixers: track.remixers,
        isrc: track.isrc,
        length_ms: track.length_ms,
      });

      if (result.auto_matched && result.candidates.length > 0) {
        const t = result.candidates[0].tidal_track;
        await queue.add({
          tidal_id: String(t.id),
          item_type: 'track',
          title: t.title,
          artist: t.artist,
          album: t.album,
          quality: state.settings.default_quality,
          format: state.settings.default_format,
        });
        dispatch({
          type: 'ADD_TOAST',
          payload: {
            id: `add-${Date.now()}-${t.id}`,
            type: 'info',
            title: 'Added to queue',
            detail: t.title,
          },
        });
      } else if (result.candidates.length > 0) {
        setConfirmTrack(track);
        setConfirmCandidates(result.candidates);
      } else {
        dispatch({
          type: 'ADD_TOAST',
          payload: {
            id: `nomatch-${Date.now()}`,
            type: 'error',
            title: 'Not on Tidal',
            detail: track.name,
          },
        });
      }
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `match-err-${Date.now()}`,
          type: 'error',
          title: 'Match failed',
          detail: track.name,
        },
      });
    } finally {
      setMatchingTrackId(null);
    }
  }, [state.settings, dispatch]);

  const handleConfirmSelect = useCallback(async (candidate: MatchCandidate) => {
    if (!confirmTrack) return;
    const t = candidate.tidal_track;
    try {
      await queue.add({
        tidal_id: String(t.id),
        item_type: 'track',
        title: t.title,
        artist: t.artist,
        album: t.album,
        quality: state.settings.default_quality,
        format: state.settings.default_format,
      });
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-${Date.now()}-${t.id}`,
          type: 'info',
          title: 'Added to queue',
          detail: t.title,
        },
      });
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: `add-err-${Date.now()}`,
          type: 'error',
          title: 'Failed to add to queue',
          detail: t.title,
        },
      });
    }
    setConfirmTrack(null);
    setConfirmCandidates([]);
  }, [confirmTrack, state.settings, dispatch]);

  const handleBeatportLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    try {
      await beatport.login(authUsername, authPassword);
      setBeatportAuth(true);
    } catch {
      dispatch({
        type: 'ADD_TOAST',
        payload: { id: `bplogin-${Date.now()}`, type: 'error', title: 'Beatport login failed' },
      });
    } finally {
      setAuthLoading(false);
    }
  };

  // Auth gate
  if (beatportAuth === false) {
    return (
      <div className="max-w-md mx-auto px-6 py-16 animate-fade-in">
        <div
          className="p-6 rounded-lg"
          style={{
            background: 'var(--bg-mid)',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius)',
          }}
        >
          <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-bright)' }}>
            Beatport Login
          </h2>
          <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
            Enter your Beatport account credentials to access genre charts and previews.
          </p>
          <form onSubmit={handleBeatportLogin} className="space-y-3">
            <input
              type="text"
              value={authUsername}
              onChange={(e) => setAuthUsername(e.target.value)}
              placeholder="Username or email"
              required
              className="w-full bg-transparent border rounded-md px-3 py-2 text-sm"
              style={{
                borderColor: 'var(--glass-border)',
                color: 'var(--text-bright)',
              }}
            />
            <input
              type="password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              placeholder="Password"
              required
              className="w-full bg-transparent border rounded-md px-3 py-2 text-sm"
              style={{
                borderColor: 'var(--glass-border)',
                color: 'var(--text-bright)',
              }}
            />
            <button type="submit" disabled={authLoading} className="btn-primary w-full text-sm py-2">
              {authLoading ? 'Logging in...' : 'Login'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (beatportAuth === null) {
    return (
      <div className="text-center py-24">
        <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto" />
      </div>
    );
  }

  // Genres loading
  if (loading && genres.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
        <div className="mb-8 flex gap-2 overflow-hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-8 rounded-full shrink-0"
              style={{
                width: `${60 + Math.random() * 40}px`,
                background: 'var(--bg-surface)',
              }}
            />
          ))}
        </div>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-16 rounded-lg"
              style={{
                background: 'var(--bg-surface)',
                opacity: 1 - i * 0.15,
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      {/* Genre selector */}
      <div className="mb-6 flex gap-1.5 overflow-x-auto pb-2 scrollbar-thin">
        {genres.map((g) => (
          <button
            key={g.id}
            onClick={() => setSelectedGenre(g.id)}
            className="shrink-0 px-3.5 py-1.5 rounded-full text-sm transition-all duration-200"
            style={{
              color: selectedGenre === g.id ? 'var(--accent-primary)' : 'var(--text-dim)',
              background: selectedGenre === g.id ? 'var(--accent-dim)' : 'var(--bg-surface)',
              border: selectedGenre === g.id
                ? '1px solid rgba(0, 229, 199, 0.3)'
                : '1px solid transparent',
            }}
          >
            {g.name}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-16">
          <p className="text-sm mb-3" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
          <button
            onClick={() => {
              setError(null);
              setLoading(true);
              beatport
                .tracks(selectedGenre!)
                .then((r) => { setTracks(r.tracks); setLoading(false); })
                .catch(() => { setError('Failed to load tracks'); setLoading(false); });
            }}
            className="btn-primary text-sm px-4 py-1.5"
          >
            Retry
          </button>
        </div>
      )}

      {/* Track list */}
      {!error && !loading && (
        <div className="space-y-2">
          {tracks.map((track, i) => {
            const artistStr = track.artists.join(', ');
            const isPreviewing = previewTrackId === track.id;
            const isMatching = matchingTrackId === track.id;

            return (
              <div
                key={track.id}
                className="glass glass-hover p-4 flex items-center justify-between transition-all duration-200"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  {track.cover_url ? (
                    <img
                      src={track.cover_url}
                      alt=""
                      className="w-10 h-10 rounded-md object-cover shrink-0"
                      style={{ border: '1px solid var(--glass-border)' }}
                    />
                  ) : (
                    <div
                      className="w-10 h-10 rounded-md shrink-0 flex items-center justify-center text-sm"
                      style={{ background: 'var(--bg-surface)', color: 'var(--text-dim)' }}
                    >
                      &#9835;
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: 'var(--text-bright)' }}>
                      {track.name}
                      {track.mix_name ? (
                        <span style={{ color: 'var(--text-muted)' }}> ({track.mix_name})</span>
                      ) : null}
                    </p>
                    <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {artistStr}
                      {track.bpm > 0 ? ` · ${track.bpm} BPM` : ''}
                      {track.key ? ` · ${track.key}` : ''}
                      {track.length ? ` · ${track.length}` : ''}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <button
                    onClick={() => handlePreview(track)}
                    disabled={previewLoading && isPreviewing}
                    className="text-xs px-2.5 py-1.5 rounded-md transition-all duration-200 shrink-0 flex items-center gap-1"
                    style={{
                      color: isPreviewing ? 'var(--accent-primary)' : 'var(--text-dim)',
                      background: isPreviewing ? 'var(--accent-dim)' : 'var(--bg-surface)',
                      border: `1px solid ${isPreviewing ? 'rgba(0, 229, 199, 0.3)' : 'var(--glass-border)'}`,
                    }}
                  >
                    {previewLoading && isPreviewing ? (
                      <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : isPreviewing ? (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <rect x="1" y="0" width="3" height="10" rx="0.5" />
                        <rect x="6" y="0" width="3" height="10" rx="0.5" />
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                        <polygon points="1,0 9,5 1,10" />
                      </svg>
                    )}
                  </button>
                  <button
                    onClick={() => handleDownload(track)}
                    disabled={isMatching}
                    className="btn-primary text-xs px-3 py-1.5 shrink-0"
                  >
                    {isMatching ? (
                      <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin inline-block" />
                    ) : (
                      <>&#8595; Download</>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
          {tracks.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm" style={{ color: 'var(--text-dim)' }}>No tracks found for this genre</p>
            </div>
          )}
        </div>
      )}

      {/* Confirmation dialog */}
      {confirmTrack && (
        <MatchConfirmDialog
          beatportTrack={confirmTrack}
          candidates={confirmCandidates}
          onSelect={handleConfirmSelect}
          onCancel={() => { setConfirmTrack(null); setConfirmCandidates([]); }}
        />
      )}
    </div>
  );
}
