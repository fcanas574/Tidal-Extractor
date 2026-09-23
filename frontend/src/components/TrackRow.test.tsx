// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TrackResult } from '../api';
import TrackRow from './TrackRow';

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

describe('TrackRow', () => {
  it('opens the related artist and album without owning download actions', () => {
    const onOpenArtist = vi.fn();
    const onOpenAlbum = vi.fn();
    const onDownload = vi.fn();

    render(
      <TrackRow
        track={track}
        isPreviewing={false}
        onPreview={vi.fn()}
        onDownload={onDownload}
        onOpenArtist={onOpenArtist}
        onOpenAlbum={onOpenAlbum}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open artist The Pilot' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));

    expect(onOpenArtist).toHaveBeenCalledWith(3);
    expect(onOpenAlbum).toHaveBeenCalledWith(4);
    expect(onDownload).not.toHaveBeenCalled();
  });

  it('keeps missing artist and album ids as readable non-interactive text', () => {
    render(
      <TrackRow
        track={{ ...track, artist_id: null, album_id: null }}
        isPreviewing={false}
        onPreview={vi.fn()}
        onDownload={vi.fn()}
        onOpenArtist={vi.fn()}
        onOpenAlbum={vi.fn()}
      />,
    );

    expect(screen.getByText('The Pilot')).toBeInTheDocument();
    expect(screen.getByText('After Hours')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open artist/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open album/i })).not.toBeInTheDocument();
  });

  it('renders optional genre and direct Camelot metadata', () => {
    render(
      <TrackRow
        track={{
          ...track,
          bpm: 128,
          key: null,
          key_scale: null,
          camelot: '8A',
          genre: 'electronic',
          bpm_source: 'freqblog',
          genre_source: 'freqblog',
        }}
        isPreviewing={false}
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.getByText('8A')).toBeInTheDocument();
    expect(screen.getByText('electronic')).toBeInTheDocument();
    expect(screen.getByLabelText(/FreqBlog metadata/i)).toBeInTheDocument();
  });

  it('renders legacy tracks without optional metadata', () => {
    render(
      <TrackRow
        track={track}
        isPreviewing={false}
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.getByText('Night Drive')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download Night Drive' })).toBeInTheDocument();
  });

  it('keeps technical DJ details and both track actions together and accessible', () => {
    render(
      <TrackRow
        track={track}
        isPreviewing={false}
        onPreview={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.getByText('3:33')).toBeInTheDocument();
    const technicalDetails = screen.getByRole('group', { name: 'Technical details for Night Drive' });
    expect(technicalDetails).toHaveTextContent('128 BPM');
    expect(technicalDetails).toHaveTextContent('5A');
    expect(technicalDetails).toHaveTextContent('high_lossless');
    expect(screen.getByRole('button', { name: 'Preview Night Drive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download Night Drive' })).toBeInTheDocument();
  });
});
