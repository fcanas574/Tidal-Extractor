import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolve, search } from './api'

describe('search API contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
      tracks: [{
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
        key: null,
        key_scale: null,
        camelot: '8A',
        genre: 'electronic',
        bpm_source: 'freqblog',
        genre_source: 'freqblog',
      }],
      artists: [],
      albums: [{ id: 42, name: 'After Hours', artist: 'The Pilot', artist_id: 3, num_tracks: 1, release_date: '2025-01-01', release_type: 'ALBUM', quality: 'LOSSLESS', cover_url: null }],
        playlists: [],
        offset: 20,
        limit: 10,
        has_more: false,
      }),
    }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('encodes typed search filters and forwards cancellation', async () => {
    const controller = new AbortController()

    const response = await search.query('Mitski', 'artist', {
      offset: 20,
      limit: 10,
      refresh: true,
      bpmMin: 90,
      bpmMax: 120,
      key: '8A',
      keyCompatible: true,
      genre: 'House',
    }, controller.signal)

    expect(fetch).toHaveBeenCalledWith(
      '/api/search?q=Mitski&type=artist&offset=20&limit=10&refresh=true&bpm_min=90&bpm_max=120&key=8A&key_compatible=true&genre=House',
      expect.objectContaining({ signal: controller.signal }),
    )
    expect(response.tracks[0]).toMatchObject({ camelot: '8A', genre: 'electronic', bpm_source: 'freqblog' })
  })

  it('supports artist lookup and cancellable URL resolution', async () => {
    const controller = new AbortController()

    await search.artist(42, controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/artist/42/summary',
      expect.objectContaining({ signal: controller.signal }),
    )

    await search.artistTracks(42, controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/artist/42/tracks',
      expect.objectContaining({ signal: controller.signal }),
    )

    await resolve.url('https://listen.tidal.com/artist/42', controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/resolve?url=https%3A%2F%2Flisten.tidal.com%2Fartist%2F42',
      expect.objectContaining({ signal: controller.signal }),
    )
  })

  it('loads album metadata and tracks with cancellation support', async () => {
    const controller = new AbortController()

    await search.albumTracks(42, controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/album/42/tracks',
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
