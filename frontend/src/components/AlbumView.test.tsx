// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppProvider, type CatalogDetail } from '../context/AppContext';
import { queue } from '../api';
import type { AlbumDetailResult, AlbumResult, QueueItem, TrackResult } from '../api';
import AlbumView from './AlbumView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, queue: { ...actual.queue, add: vi.fn() } };
});

const album: AlbumResult = {
  id: 4,
  name: 'After Hours',
  artist: 'The Pilot',
  artist_id: 3,
  num_tracks: 1,
  release_date: '2024-01-01',
  release_type: 'ALBUM',
  quality: 'high_lossless',
  cover_url: null,
};

const track: TrackResult = {
  id: 7,
  title: 'Night Drive',
  artist: 'The Pilot',
  artist_id: 3,
  album: 'After Hours',
  album_id: 4,
  duration: 213,
  quality: 'high_lossless',
  explicit: false,
  isrc: null,
  url: 'tidal://7',
  cover_url: null,
  bpm: 128,
  key: 'C',
  key_scale: 'minor',
};

const queueItem: QueueItem = {
  id: 9,
  tidal_id: '7',
  item_type: 'track',
  title: track.title,
  artist: track.artist,
  album: track.album,
  quality: track.quality,
  format: 'FLAC',
  status: 'queued',
  progress: 0,
  error: null,
  revision: 1,
};

const detailData: AlbumDetailResult = { album, tracks: [track] };

function detail(overrides: Partial<Extract<CatalogDetail, { kind: 'album' }>> = {}): Extract<CatalogDetail, { kind: 'album' }> {
  return { kind: 'album', id: album.id, status: 'success', data: detailData, error: null, ...overrides };
}

function renderAlbum(overrides: Partial<React.ComponentProps<typeof AlbumView>> = {}) {
  return render(
    <AppProvider>
      <AlbumView
        detail={detail()}
        onBack={vi.fn()}
        onRetry={vi.fn()}
        onOpenArtist={vi.fn()}
        onOpenAlbum={vi.fn()}
        {...overrides}
      />
    </AppProvider>,
  );
}

describe('AlbumView', () => {
  it('renders album metadata and keeps navigation, preview, and downloads distinct', () => {
    const onOpenArtist = vi.fn();
    const onOpenAlbum = vi.fn();
    vi.mocked(queue.add).mockResolvedValue(queueItem);
    renderAlbum({ onOpenArtist, onOpenAlbum });

    expect(screen.getByRole('heading', { name: 'After Hours' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download album After Hours' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download Night Drive' })).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Open artist The Pilot' })[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));
    fireEvent.click(screen.getByRole('button', { name: 'Download album After Hours' }));
    fireEvent.click(screen.getByRole('button', { name: 'Download Night Drive' }));

    expect(onOpenArtist).toHaveBeenCalledWith(3);
    expect(onOpenAlbum).toHaveBeenCalledWith(4);
    expect(queue.add).toHaveBeenCalledWith(expect.objectContaining({ tidal_id: '4', item_type: 'album' }));
    expect(queue.add).toHaveBeenCalledWith(expect.objectContaining({ tidal_id: '7', item_type: 'track' }));
  });

  it('renders stable loading state', () => {
    renderAlbum({ detail: detail({ status: 'loading', data: null }) });

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders retry and back actions for a detail error', () => {
    const onBack = vi.fn();
    const onRetry = vi.fn();
    renderAlbum({ detail: detail({ status: 'error', data: null, error: 'Album unavailable' }), onBack, onRetry });

    expect(screen.getByRole('alert')).toHaveTextContent('Album unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    fireEvent.click(screen.getByRole('button', { name: '← Back to search' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('keeps album actions available when the track list is empty', () => {
    renderAlbum({ detail: detail({ data: { album, tracks: [] } }) });

    expect(screen.getByRole('button', { name: 'Download album After Hours' })).toBeInTheDocument();
    expect(screen.getByText('No tracks found for this album.')).toBeInTheDocument();
  });
});
