const BASE = '/api';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export interface SearchResult {
  tracks: TrackResult[];
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}

export interface TrackResult {
  id: number;
  title: string;
  artist: string;
  album: string;
  album_id: number | null;
  duration: number;
  quality: string;
  explicit: boolean;
  isrc: string | null;
  url: string;
  cover_url: string | null;
}

export interface AlbumResult {
  id: number;
  name: string;
  artist: string;
  num_tracks: number;
  release_date: string | null;
  quality: string;
  cover_url: string | null;
}

export interface PlaylistResult {
  id: string;
  name: string;
  num_tracks: number;
  creator: string | null;
  cover_url: string | null;
}

export interface ArtistResult {
  id: number;
  name: string;
  image_url: string | null;
  bio: string | null;
}

export interface ResolveResult {
  artist: ArtistResult | null;
  top_tracks: TrackResult[];
  tracks: TrackResult[];
  albums: AlbumResult[];
  playlists: PlaylistResult[];
}

export interface QueueItem {
  id: number;
  tidal_id: string;
  item_type: string;
  title: string;
  artist: string;
  album: string;
  quality: string;
  format: string;
  status: 'queued' | 'downloading' | 'complete' | 'failed';
  progress: number;
  error: string | null;
}

export interface Settings {
  default_quality: string;
  default_format: string;
  output_dir: string;
}

export interface AuthStatus {
  authenticated: boolean;
  username: string | null;
}

export interface DeviceLink {
  url: string;
  code: string;
  expires_in: number;
}

export interface HistoryItem {
  id: number;
  tidal_id: string;
  item_type: string;
  title: string;
  artist: string;
  album: string | null;
  quality: string;
  format: string;
  file_size: number;
  downloaded_at: string;
}

export interface WsMessage {
  type: 'progress' | 'quality' | 'complete' | 'error' | 'queue_update';
  id: string;
  [key: string]: unknown;
}

export const auth = {
  getDeviceLink: () => request<DeviceLink>('/auth/device-link', { method: 'POST' }),
  verifyDeviceLink: () => request<{ authenticated: boolean }>('/auth/device-link/verify', { method: 'POST' }),
  getStatus: () => request<AuthStatus>('/auth/status'),
  logout: () => request<{ authenticated: boolean }>('/auth/logout', { method: 'POST' }),
};

export const search = {
  query: (q: string, type: string = 'track') =>
    request<SearchResult>(`/search?q=${encodeURIComponent(q)}&type=${type}`),
  albumTracks: (albumId: number) =>
    request<{ tracks: TrackResult[] }>(`/album/${albumId}/tracks`),
  playlistTracks: (playlistId: string) =>
    request<{ tracks: TrackResult[] }>(`/playlist/${playlistId}/tracks`),
};

export const queue = {
  list: () => request<QueueItem[]>('/queue'),
  add: (item: { tidal_id: string; item_type: string; title: string; artist?: string; album?: string; quality?: string; format?: string }) =>
    request<QueueItem>('/queue/add', { method: 'POST', body: JSON.stringify(item) }),
  remove: (id: number) => request<{ ok: boolean }>(`/queue/${id}`, { method: 'DELETE' }),
  removeBatch: (ids: number[]) =>
    request<{ removed: number }>('/queue/batch', { method: 'DELETE', body: JSON.stringify({ ids }) }),
  clearCompleted: () =>
    request<{ removed: number }>('/queue/completed', { method: 'DELETE' }),
  clearAll: () =>
    request<{ removed: number }>('/queue/all', { method: 'DELETE' }),
};

export const settings = {
  get: () => request<Settings>('/settings'),
  update: (s: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(s) }),
};

export const quality = {
  probe: () => request<{ preset: string; bitrate: number }>('/quality/probe', { method: 'POST' }),
  cache: () => request<{ preset: string; bitrate: number } | null>('/quality/cache'),
};

export const history = {
  list: (offset = 0, limit = 100) =>
    request<HistoryItem[]>(`/history?offset=${offset}&limit=${limit}`),

  reDownload: (item: {
    tidal_id: string;
    item_type?: string;
    title: string;
    artist?: string;
    album?: string;
    quality?: string;
    format?: string;
  }) => request<QueueItem>('/history/re-download', { method: 'POST', body: JSON.stringify(item) }),
};

export const resolve = {
  url: (url: string) => request<ResolveResult>(`/resolve?url=${encodeURIComponent(url)}`),
};

export interface WaveformData {
  bands: { low: number[]; mid: number[]; high: number[] };
  colors: { low: string; mid: string; high: string };
  duration: number;
}

export const preview = {
  getUrl: (trackId: number) => request<{ stream_url: string; waveform: WaveformData | null }>(`/preview/${trackId}`),
};
