// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider } from '../context/AppContext';
import type { AlbumResult, QueueItem, TrackResult } from '../api';
import { queue, resolve, search } from '../api';
import SearchView from './SearchView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    search: { ...actual.search, query: vi.fn(), albumTracks: vi.fn(), playlistTracks: vi.fn() },
    resolve: { ...actual.resolve, url: vi.fn() },
    queue: { ...actual.queue, add: vi.fn() },
  };
});

const track: TrackResult = {
  id: 7, title: 'Night Drive', artist: 'The Pilot', album: 'After Hours', album_id: 4,
  duration: 213, quality: 'high_lossless', explicit: false, isrc: null, url: 'tidal://7', cover_url: null,
  bpm: 128, key: 'C', key_scale: 'minor',
};

const queueItem: QueueItem = {
  id: 9, tidal_id: '7', item_type: 'track', title: track.title, artist: track.artist, album: track.album,
  quality: 'high_lossless', format: 'FLAC', status: 'queued', progress: 0, error: null, revision: 1,
};

const album: AlbumResult = { id: 4, name: 'After Hours', artist: 'The Pilot', num_tracks: 10, release_date: '2024-01-01', quality: 'high_lossless', cover_url: null };

function renderSearch() {
  return render(<AppProvider><SearchView /></AppProvider>);
}

afterEach(() => vi.clearAllMocks());

describe('SearchView', () => {
  it('keeps the short search prompt and exposes URL detection', () => {
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    expect(input).toHaveAttribute('placeholder', 'Search tracks, artists, albums, or paste a Tidal link');
    fireEvent.change(input, { target: { value: 'https://listen.tidal.com/track/7' } });
    expect(screen.getByRole('status')).toHaveTextContent('Tidal link detected');
  });

  it('opens Refine and renders removable DJ filter chips', () => {
    renderSearch();
    fireEvent.click(screen.getByRole('button', { name: /^Refine$/ }));
    fireEvent.change(screen.getByLabelText('Minimum BPM'), { target: { value: '120' } });
    fireEvent.change(screen.getByLabelText('Genre'), { target: { value: 'House' } });
    expect(screen.getByRole('button', { name: 'Remove Min 120 BPM filter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove House filter' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove Min 120 BPM filter' }));
    expect(screen.queryByRole('button', { name: 'Remove Min 120 BPM filter' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.queryByRole('button', { name: 'Remove House filter' })).not.toBeInTheDocument();
  });

  it('keeps download primary, preview secondary, and track pagination semantics', async () => {
    vi.mocked(search.query)
      .mockResolvedValueOnce({ tracks: [track], albums: [], playlists: [] })
      .mockResolvedValueOnce({ tracks: [{ ...track, id: 8, title: 'Second Track' }], albums: [], playlists: [] });
    vi.mocked(queue.add).mockResolvedValue(queueItem);
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Preview Night Drive' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Download Night Drive' }));
    expect(queue.add).toHaveBeenCalledWith(expect.objectContaining({ tidal_id: '7', item_type: 'track' }));
    fireEvent.click(screen.getByRole('button', { name: 'Load more results' }));
    await waitFor(() => expect(screen.getByText('Second Track')).toBeInTheDocument());
    expect(search.query).toHaveBeenLastCalledWith('Night Drive', 'track', expect.objectContaining({ offset: 1, limit: 50 }));
  });

  it('shows a retryable request error while preserving the query', async () => {
    vi.mocked(search.query)
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce({ tracks: [track], albums: [], playlists: [] });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable'));
    expect(input).toHaveValue('Night Drive');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());
    expect(search.query).toHaveBeenCalledTimes(2);
  });

  it('renders resolved artist details and a return path without another request', async () => {
    vi.mocked(resolve.url).mockResolvedValue({ artist: { id: 3, name: 'The Pilot', image_url: null, bio: null }, top_tracks: [track], tracks: [], albums: [album], playlists: [] });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'https://tidal.com/artist/3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));
    await waitFor(() => expect(screen.getByText('Artist details')).toBeInTheDocument());
    expect(screen.getByText('Top tracks')).toBeInTheDocument();
    expect(screen.getByText('Albums')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '← Back to search' }));
    expect(screen.getByText('Search the catalog or paste a Tidal link to begin.')).toBeInTheDocument();
    expect(resolve.url).toHaveBeenCalledTimes(1);
  });
});
