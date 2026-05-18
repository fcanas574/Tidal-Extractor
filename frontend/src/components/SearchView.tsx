import { useState } from 'react';
import { search, queue } from '../api';
import { useApp } from '../context/AppContext';
import type { TrackResult, AlbumResult, PlaylistResult } from '../api';

export default function SearchView() {
  const { state } = useApp();
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState<'track' | 'album' | 'playlist'>('track');
  const [results, setResults] = useState<{
    tracks: TrackResult[];
    albums: AlbumResult[];
    playlists: PlaylistResult[];
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await search.query(query, searchType);
      setResults(r);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddToQueue = async (
    tidal_id: string | number,
    item_type: string,
    title: string,
    artist: string = '',
    album: string = '',
  ) => {
    await queue.add({
      tidal_id: String(tidal_id),
      item_type,
      title,
      artist,
      album,
      quality: state.settings.default_quality,
      format: state.settings.default_format,
    });
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const typeButtons: { key: typeof searchType; label: string }[] = [
    { key: 'track', label: 'Tracks' },
    { key: 'album', label: 'Albums' },
    { key: 'playlist', label: 'Playlists' },
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <form onSubmit={handleSearch} className="mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tracks, albums, playlists..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold px-6 py-2 rounded-lg transition-colors"
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        <div className="flex gap-2 mt-3">
          {typeButtons.map((btn) => (
            <button
              key={btn.key}
              type="button"
              onClick={() => setSearchType(btn.key)}
              className={`px-3 py-1 rounded-md text-sm transition-colors ${
                searchType === btn.key
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </form>

      {results && (
        <div className="space-y-2">
          {results.tracks.map((track) => (
            <div
              key={track.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{track.title}</p>
                <p className="text-gray-400 text-sm truncate">
                  {track.artist} &middot; {track.album} &middot; {formatDuration(track.duration)} &middot;
                  <span className="text-gray-500 ml-1">{track.quality}</span>
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(track.id, 'track', track.title, track.artist, track.album)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.albums.map((album) => (
            <div
              key={album.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{album.name}</p>
                <p className="text-gray-400 text-sm truncate">
                  {album.artist} &middot; {album.num_tracks} tracks
                  {album.release_date && ` &middot; ${album.release_date}`}
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(album.id, 'album', album.name, album.artist)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.playlists.map((pl) => (
            <div
              key={pl.id}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium truncate">{pl.name}</p>
                <p className="text-gray-400 text-sm truncate">
                  {pl.creator || 'Unknown'} &middot; {pl.num_tracks} tracks
                </p>
              </div>
              <button
                onClick={() =>
                  handleAddToQueue(pl.id, 'playlist', pl.name)
                }
                className="ml-3 bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors shrink-0"
              >
                Download
              </button>
            </div>
          ))}

          {results.tracks.length === 0 && results.albums.length === 0 && results.playlists.length === 0 && (
            <p className="text-gray-500 text-center py-8">No results found</p>
          )}
        </div>
      )}
    </div>
  );
}
