import { describe, expect, it } from 'vitest'
import type { TimelineFrame } from './api'
import {
  bufferedTimelineFrames,
  nextReadyTimelineFrame,
  WEATHER_FRAME_LOOKAHEAD,
} from './playback'

function frame(index: number): TimelineFrame {
  return {
    runTime: '2026-07-22T06:00:00Z',
    validTime: `2026-07-22T${String(index).padStart(2, '0')}:00:00Z`,
    forecastHour: index,
    intervalStart: null,
    intervalEnd: null,
    timeKind: 'instant',
  }
}

describe('lossless forecast playback', () => {
  const times = Array.from({ length: 24 }, (_, index) => frame(index))

  it('buffers the active frame and twelve frames ahead in timeline order', () => {
    const buffered = bufferedTimelineFrames(times, times[20].validTime)

    expect(buffered).toHaveLength(WEATHER_FRAME_LOOKAHEAD + 1)
    expect(buffered.map((item) => item.validTime)).toEqual([
      ...times.slice(20).map((item) => item.validTime),
      ...times.slice(0, 9).map((item) => item.validTime),
    ])
  })

  it('waits for the immediate next frame instead of skipping to a later ready frame', () => {
    const laterFrameReady = new Set([
      times[7].validTime,
      times[8].validTime,
      times[9].validTime,
    ])

    expect(
      nextReadyTimelineFrame(times, times[5].validTime, laterFrameReady),
    ).toBeUndefined()

    laterFrameReady.add(times[6].validTime)
    expect(
      nextReadyTimelineFrame(times, times[5].validTime, laterFrameReady)
        ?.validTime,
    ).toBe(times[6].validTime)
  })
})
