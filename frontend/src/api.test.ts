import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolve, search } from './api'

describe('search API contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tracks: [],
        artists: [],
        albums: [],
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

    await search.query('Mitski', 'artist', {
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
  })

  it('supports artist lookup and cancellable URL resolution', async () => {
    const controller = new AbortController()

    await search.artist(42, controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/artist/42',
      expect.objectContaining({ signal: controller.signal }),
    )

    await resolve.url('https://listen.tidal.com/artist/42', controller.signal)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/resolve?url=https%3A%2F%2Flisten.tidal.com%2Fartist%2F42',
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
