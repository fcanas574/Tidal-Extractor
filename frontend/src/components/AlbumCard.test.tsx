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
});
