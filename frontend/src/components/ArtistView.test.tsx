// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppProvider } from '../context/AppContext';
import type { AlbumResult, ArtistResult, TrackResult } from '../api';
import ArtistView from './ArtistView';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, queue: { ...actual.queue, add: vi.fn() } };
});

const artist: ArtistResult = { id: 3, name: 'The Pilot', image_url: null, bio: 'Electronic artist' };
const track: TrackResult = {
  id: 7,
  title: 'Night Drive',
  artist: 'The Pilot',
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
const release: AlbumResult = {
  id: 4,
  name: 'After Hours',
  artist: 'The Pilot',
  num_tracks: 10,
  release_date: '2025-02-01',
  release_type: 'EP',
  quality: 'high_lossless',
  cover_url: null,
};
const single: AlbumResult = {
  id: 5,
  name: 'Night Signal',
  artist: 'The Pilot',
  num_tracks: 1,
  release_date: '2025-04-01',
  release_type: 'SINGLE',
  quality: 'high_lossless',
  cover_url: null,
};

function renderArtist(overrides: Partial<React.ComponentProps<typeof ArtistView>> = {}) {
  return render(
    <AppProvider>
      <ArtistView artist={artist} topTracks={[track]} albums={[release, single]} {...overrides} />
    </AppProvider>,
  );
}

describe('ArtistView', () => {
  it('shows top tracks beside larger latest-release cards with download-only albums', () => {
    renderArtist();

    expect(screen.getByRole('heading', { name: 'Top tracks' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Latest releases' })).toBeInTheDocument();
    expect(screen.getByText('After Hours')).toBeInTheDocument();
    expect(screen.getByText('EP')).toBeInTheDocument();
    expect(screen.getByText('2025-02-01')).toBeInTheDocument();
    expect(screen.getByText('SINGLE')).toBeInTheDocument();
    expect(screen.getByText('2025-04-01')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Preview Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download album After Hours' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open album/i })).not.toBeInTheDocument();
  });

  it('shows no more than five top tracks', () => {
    const topTracks = Array.from({ length: 6 }, (_, index) => ({
      ...track,
      id: 70 + index,
      title: `Top Track ${index + 1}`,
    }));

    renderArtist({ topTracks });

    expect(screen.getByText('Top Track 5')).toBeInTheDocument();
    expect(screen.queryByText('Top Track 6')).not.toBeInTheDocument();
  });

  it('keeps the other section usable when one section reports an error', () => {
    renderArtist({ errors: { albums: 'Release service unavailable' } });

    expect(screen.getByRole('status')).toHaveTextContent('Release service unavailable');
    expect(screen.getByText('Top tracks')).toBeInTheDocument();
    expect(screen.getByText('Night Drive')).toBeInTheDocument();
  });
});
