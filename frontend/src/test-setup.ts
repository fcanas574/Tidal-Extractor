import '@testing-library/jest-dom'
import { vi } from 'vitest'

// jsdom lacks HTMLAudioElement. Provide a mock `Audio` constructor that
// satisfies the surface `AudioPlayerFooter` touches: constructor records calls
// so tests may assert playback started; instances expose the media events and
// playback methods used by the component.
class MockAudioInstance {
  src: string = ''
  currentTime = 0
  duration = 0
  private listeners: Record<string, EventListener[]> = {}

  constructor(src?: string) {
    if (src !== undefined) this.src = src
  }

  addEventListener = (type: string, listener: EventListener) => {
    (this.listeners[type] ??= []).push(listener)
  }
  removeEventListener = () => {}
  play = () => Promise.resolve<void>(undefined)
  pause = () => {}
}

const AudioCtor = vi.fn(function (this: MockAudioInstance, src?: string) {
  return new MockAudioInstance(src)
}) as unknown as { new (src?: string): MockAudioInstance } & { mock: ReturnType<typeof vi.fn> }

// `vi.fn` wrapping a function that returns an object does not produce a
// constructable that records `new` calls the way we need; expose a dedicated
// recorder the tests can inspect.
const audioCalls: (string | undefined)[] = []
const TrackedAudio = vi.fn(function (this: unknown, src?: string) {
  audioCalls.push(src)
  return new MockAudioInstance(src)
}) as unknown as typeof AudioCtor
;(TrackedAudio as unknown as { __calls: (string | undefined)[] }).__calls = audioCalls

// Install on the global so component `new Audio(url)` resolves to the mock.
globalThis.Audio = TrackedAudio as unknown as typeof Audio

// jsdom canvas: return a permissive 2D context stub so `drawClubWaveform`
// (which calls many canvas-2d methods and properties) runs without enumerating
// each one. A Proxy returning a noop fn for any method access lets property
// writes and chained reads (e.g. measureText().width) resolve to undefined.
const stubCtx = new Proxy({}, {
  get: () => () => {},
}) as unknown as CanvasRenderingContext2D
HTMLCanvasElement.prototype.getContext = function () {
  return stubCtx
} as unknown as typeof HTMLCanvasElement.prototype.getContext

// jsdom lacks the Path2D constructor; `drawClubWaveform` builds waveform paths
// with `new Path2D()`. Mirror the ctx stub's strategy: a constructor whose
// instances are a Proxy returning a noop fn for any method access, so we never
// need to enumerate moveTo/lineTo/arc/closePath/etc.
const MockPath2D = function () {
  return new Proxy({}, { get: () => () => {} })
} as unknown as { new (): Path2D }
globalThis.Path2D = MockPath2D as unknown as typeof Path2D

// jsdom returns zero-size rects; give the waveform canvas a usable size so the
// canvas-draw effect proceeds in tests.
HTMLCanvasElement.prototype.getBoundingClientRect = function () {
  return { width: 600, height: 120, left: 0, top: 0, right: 600, bottom: 120, x: 0, y: 0 } as DOMRect
}
