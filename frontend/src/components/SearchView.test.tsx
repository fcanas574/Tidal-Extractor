// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProvider } from '../context/AppContext';
import type { AlbumDetailResult, AlbumResult, ArtistResult, QueueItem, SearchResult, TrackResult } from '../api';
import { queue, resolve, search } from '../api';
import SearchView from './SearchView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    search: { ...actual.search, query: vi.fn(), artist: vi.fn(), artistTracks: vi.fn(), albumTracks: vi.fn(), playlistTracks: vi.fn() },
    resolve: { ...actual.resolve, url: vi.fn() },
    queue: { ...actual.queue, add: vi.fn() },
  };
});

const track: TrackResult = {
  id: 7, title: 'Night Drive', artist: 'The Pilot', album: 'After Hours', album_id: 4,
  artist_id: 3,
  duration: 213, quality: 'high_lossless', explicit: false, isrc: null, url: 'tidal://7', cover_url: null,
  bpm: 128, key: 'C', key_scale: 'minor',
};

const enrichedTrack: TrackResult = {
  ...track,
  bpm: 128,
  key: null,
  key_scale: null,
  camelot: '8A',
  genre: 'electronic',
  bpm_source: 'freqblog',
  genre_source: 'freqblog',
};

const queueItem: QueueItem = {
  id: 9, tidal_id: '7', item_type: 'track', title: track.title, artist: track.artist, album: track.album,
  quality: 'high_lossless', format: 'FLAC', status: 'queued', progress: 0, error: null, revision: 1,
};

const album: AlbumResult = { id: 4, name: 'After Hours', artist: 'The Pilot', artist_id: 3, num_tracks: 10, release_date: '2024-01-01', release_type: 'ALBUM', quality: 'high_lossless', cover_url: null };
const artist: ArtistResult = { id: 3, name: 'The Pilot', image_url: null, bio: null };
const albumDetail: AlbumDetailResult = { album, tracks: [track] };

function result(overrides: Partial<SearchResult> = {}): SearchResult {
  return { tracks: [], artists: [], albums: [], playlists: [], offset: 0, limit: 50, has_more: false, ...overrides };
}

function renderSearch() {
  return render(<AppProvider><SearchView /></AppProvider>);
}

beforeEach(() => {
  vi.mocked(search.artistTracks).mockResolvedValue({ tracks: [] });
});

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
      .mockResolvedValueOnce(result({ tracks: [track], has_more: true }))
      .mockResolvedValueOnce(result({ tracks: [{ ...track, id: 8, title: 'Second Track' }], offset: 1 }));
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
    expect(search.query).toHaveBeenLastCalledWith('Night Drive', 'track', expect.objectContaining({ offset: 1, limit: 50 }), expect.any(AbortSignal));
  });

  it('renders enriched metadata while keeping track actions available', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [enrichedTrack] }));
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());
    expect(screen.getByText('8A')).toBeInTheDocument();
    expect(screen.getByText('electronic')).toBeInTheDocument();
    expect(screen.getByLabelText(/FreqBlog metadata/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open artist The Pilot' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open album After Hours' })).toBeInTheDocument();
  });

  it('opens an artist from a track result without replacing the committed search', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [track] }));
    vi.mocked(search.artist).mockResolvedValue({ artist, top_tracks: [track], tracks: [], albums: [album], playlists: [] });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Open artist The Pilot' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open artist The Pilot' }));

    await waitFor(() => expect(screen.getByText('Artist details')).toBeInTheDocument());
    expect(search.artist).toHaveBeenCalledWith(3, expect.any(AbortSignal));
    expect(search.query).toHaveBeenCalledTimes(1);
  });

  it('renders the artist overview before the full track catalog finishes loading', async () => {
    let resolveTracks!: (value: { tracks: TrackResult[] }) => void;
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [track] }));
    vi.mocked(search.artist).mockResolvedValue({ artist, top_tracks: [track], tracks: [], albums: [album], playlists: [] });
    vi.mocked(search.artistTracks).mockImplementation(() => new Promise((resolve) => { resolveTracks = resolve; }));
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Open artist The Pilot' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open artist The Pilot' }));

    await waitFor(() => expect(screen.getByText('Top tracks')).toBeInTheDocument());
    expect(screen.getByText('Loading the full artist catalog…')).toBeInTheDocument();
    expect(search.artistTracks).toHaveBeenCalledWith(3, expect.any(AbortSignal));

    resolveTracks({ tracks: [{ ...track, id: 8, title: 'Deep Cut' }] });
    await waitFor(() => expect(screen.getByText('Deep Cut')).toBeInTheDocument());
  });

  it('opens an album from a track result and renders its detail view', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [track] }));
    vi.mocked(search.albumTracks).mockResolvedValue(albumDetail);
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Open album After Hours' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'After Hours' })).toBeInTheDocument());
    expect(search.albumTracks).toHaveBeenCalledWith(4, expect.any(AbortSignal));
  });

  it('shows a retryable request error while preserving the query', async () => {
    vi.mocked(search.query)
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce(result({ tracks: [track] }));
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable'));
    expect(input).toHaveValue('Night Drive');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());
    expect(search.query).toHaveBeenCalledTimes(2);
    expect(search.query).toHaveBeenLastCalledWith('Night Drive', 'track', expect.objectContaining({ offset: 0, limit: 50, refresh: true }), expect.any(AbortSignal));
  });

  it('renders resolved artist details and a return path without another request', async () => {
    vi.mocked(resolve.url).mockResolvedValue({ artist, top_tracks: [track], tracks: [], albums: [album], playlists: [] });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'https://tidal.com/artist/3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));
    await waitFor(() => expect(screen.getByText('Artist details')).toBeInTheDocument());
    expect(screen.getByText('Top tracks')).toBeInTheDocument();
    expect(screen.getByText('Latest releases')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '← Back to search' }));
    expect(screen.getByText('Search the catalog or paste a Tidal link to begin.')).toBeInTheDocument();
    expect(resolve.url).toHaveBeenCalledTimes(1);
  });

  it('renders the full artist track catalog below the artist overview', async () => {
    const catalogTrack = { ...track, id: 80, title: 'Deep Cut' };
    vi.mocked(resolve.url).mockResolvedValue({ artist, top_tracks: [track], tracks: [catalogTrack], albums: [album], playlists: [] });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'https://tidal.com/artist/3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'All tracks' })).toBeInTheDocument());
    expect(screen.getByText('Deep Cut')).toBeInTheDocument();
  });

  it('surfaces partial artist errors without hiding the successful section', async () => {
    vi.mocked(resolve.url).mockResolvedValue({ artist, top_tracks: [track], tracks: [], albums: [], playlists: [], errors: { albums: 'Releases unavailable' } });
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'https://tidal.com/artist/3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());
    expect(screen.getByText(/Releases unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Top tracks')).toBeInTheDocument();
  });

  it('searches artists and opens the selected artist by id', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ artists: [artist] }));
    vi.mocked(search.artist).mockResolvedValue({ artist, top_tracks: [track], tracks: [], albums: [album], playlists: [] });
    renderSearch();

    fireEvent.click(screen.getByRole('button', { name: 'Artists' }));
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'The Pilot' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByText('The Pilot')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open artist The Pilot' }));

    await waitFor(() => expect(screen.getByText('Artist details')).toBeInTheDocument());
    expect(search.artist).toHaveBeenCalledWith(3, expect.any(AbortSignal));
  });

  it('opens album results while keeping their download action independent', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ albums: [album] }));
    vi.mocked(search.albumTracks).mockResolvedValue(albumDetail);
    vi.mocked(queue.add).mockResolvedValue({ ...queueItem, item_type: 'album', title: album.name, artist: album.artist });
    renderSearch();
    fireEvent.click(screen.getByRole('button', { name: 'Albums' }));
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'After Hours' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Open album After Hours' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Download album After Hours' }));
    expect(queue.add).toHaveBeenCalledWith(expect.objectContaining({ tidal_id: '4', item_type: 'album' }));
    expect(search.albumTracks).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'After Hours' })).toBeInTheDocument());
    expect(search.albumTracks).toHaveBeenCalledWith(4, expect.any(AbortSignal));
  });

  it('opens an album URL as album detail instead of a download-only result', async () => {
    vi.mocked(resolve.url).mockResolvedValue({ artist: null, top_tracks: [], tracks: [], albums: [album], playlists: [] });
    vi.mocked(search.albumTracks).mockResolvedValue(albumDetail);
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'https://tidal.com/album/4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'After Hours' })).toBeInTheDocument());
    expect(search.albumTracks).toHaveBeenCalledWith(4, expect.any(AbortSignal));
    expect(search.query).not.toHaveBeenCalled();
  });

  it('restores the existing results after going back from an album detail', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ albums: [album] }));
    vi.mocked(search.albumTracks).mockResolvedValue(albumDetail);
    renderSearch();
    fireEvent.click(screen.getByRole('button', { name: 'Albums' }));
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'After Hours' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open album After Hours' })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'After Hours' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '← Back to search' }));

    expect(screen.getByRole('button', { name: 'Open album After Hours' })).toBeInTheDocument();
    expect(input).toHaveValue('After Hours');
    expect(search.query).toHaveBeenCalledTimes(1);
  });

  it('ignores an older album detail response after a newer detail completes', async () => {
    const firstAlbum = { ...album, name: 'First Album' };
    const secondAlbum = { ...album, id: 5, name: 'Second Album' };
    const firstDetail = { album: firstAlbum, tracks: [{ ...track, album: firstAlbum.name, album_id: firstAlbum.id }] };
    const secondDetail = { album: secondAlbum, tracks: [{ ...track, id: 8, title: 'Second Track', album: secondAlbum.name, album_id: secondAlbum.id }] };
    const detailResolvers: Array<(value: AlbumDetailResult) => void> = [];
    vi.mocked(search.query)
      .mockResolvedValueOnce(result({ albums: [firstAlbum] }))
      .mockResolvedValueOnce(result({ albums: [secondAlbum] }));
    vi.mocked(search.albumTracks).mockImplementation(() => new Promise((resolve) => detailResolvers.push(resolve)));
    renderSearch();
    fireEvent.click(screen.getByRole('button', { name: 'Albums' }));
    const input = screen.getByRole('textbox', { name: /Search tracks/i });

    fireEvent.change(input, { target: { value: 'First Album' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open album First Album' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open album First Album' }));

    fireEvent.change(input, { target: { value: 'Second Album' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Open album Second Album' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Open album Second Album' }));
    await waitFor(() => expect(detailResolvers).toHaveLength(2));

    detailResolvers[1](secondDetail);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Second Album' })).toBeInTheDocument());
    detailResolvers[0](firstDetail);
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'First Album' })).not.toBeInTheDocument());
  });

  it('restores the committed query and results after SearchView remounts', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [track] }));
    function Shell({ visible }: { visible: boolean }) {
      return <AppProvider>{visible && <SearchView />}</AppProvider>;
    }

    const view = render(<Shell visible />);
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());

    view.rerender(<Shell visible={false} />);
    view.rerender(<Shell visible />);

    expect(screen.getByRole('textbox', { name: /Search tracks/i })).toHaveValue('Night Drive');
    expect(screen.getByText('Night Drive')).toBeInTheDocument();
  });

  it('ignores an older deferred response after a newer search completes', async () => {
    const resolvers: Array<(value: SearchResult) => void> = [];
    vi.mocked(search.query).mockImplementation(() => new Promise((resolve) => resolvers.push(resolve)));
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });

    fireEvent.change(input, { target: { value: 'Old query' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    fireEvent.change(input, { target: { value: 'New query' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(resolvers).toHaveLength(2));

    resolvers[1](result({ tracks: [{ ...track, title: 'New result' }] }));
    await waitFor(() => expect(screen.getByText('New result')).toBeInTheDocument());
    resolvers[0](result({ tracks: [{ ...track, title: 'Old result' }] }));
    await waitFor(() => expect(screen.queryByText('Old result')).not.toBeInTheDocument());
  });

  it('restarts filtered searches at offset zero', async () => {
    vi.mocked(search.query).mockResolvedValue(result({ tracks: [track] }));
    renderSearch();
    const input = screen.getByRole('textbox', { name: /Search tracks/i });
    fireEvent.change(input, { target: { value: 'Night Drive' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(screen.getByText('Night Drive')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /^Refine$/ }));
    fireEvent.change(screen.getByLabelText('Minimum BPM'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(search.query).toHaveBeenLastCalledWith(
      'Night Drive',
      'track',
      expect.objectContaining({ offset: 0, limit: 50, bpmMin: 120 }),
      expect.any(AbortSignal),
    ));
  });

});
