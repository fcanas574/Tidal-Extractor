// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AlbumResult } from '../api';
import AlbumCard from './AlbumCard';

const album: AlbumResult = {
  id: 4,
  name: 'After Hours',
  artist: 'The Pilot',
  artist_id: 3,
  num_tracks: 10,
  release_date: '2024-01-01',
  release_type: 'ALBUM',
  quality: 'high_lossless',
  cover_url: null,
};

describe('AlbumCard', () => {
  it('keeps album navigation separate from downloading', () => {
    const onOpen = vi.fn();
    const onDownload = vi.fn();

    render(<AlbumCard album={album} onOpen={onOpen} onDownload={onDownload} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open album After Hours' }));
    expect(onOpen).toHaveBeenCalledWith(album);
    expect(onDownload).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Download album After Hours' }));
    expect(onDownload).toHaveBeenCalledWith(album);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('preserves album identity, release metadata, and actions with a long title', () => {
    const longAlbum = {
      ...album,
      name: 'After Hours — Extended Club Reissue and Remastered Sessions',
    };
    const onOpen = vi.fn();
    const onDownload = vi.fn();

    render(<AlbumCard album={longAlbum} onOpen={onOpen} onDownload={onDownload} />);

    expect(screen.getByRole('button', { name: `Open album ${longAlbum.name}` })).toBeInTheDocument();
    expect(screen.getByText(/The Pilot · 10 tracks · 2024-01-01/)).toBeInTheDocument();
    expect(screen.getByText('high_lossless')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `Download album ${longAlbum.name}` })).toBeInTheDocument();
  });
});
