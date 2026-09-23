import type { TimelineFrame } from './api'

export const WEATHER_FRAME_LOOKAHEAD = 12

export function bufferedTimelineFrames(
  times: TimelineFrame[],
  activeValidTime: string,
  lookahead = WEATHER_FRAME_LOOKAHEAD,
) {
  if (times.length === 0) return []
  const activeIndex = Math.max(
    0,
    times.findIndex((item) => item.validTime === activeValidTime),
  )
  const count = Math.min(times.length, Math.max(0, lookahead) + 1)
  return Array.from(
    { length: count },
    (_, offset) => times[(activeIndex + offset) % times.length],
  )
}

export function nextReadyTimelineFrame(
  times: TimelineFrame[],
  activeValidTime: string,
  readyFrameIds: ReadonlySet<string>,
) {
  if (times.length < 2) return undefined
  const activeIndex = Math.max(
    0,
    times.findIndex((item) => item.validTime === activeValidTime),
  )
  const next = times[(activeIndex + 1) % times.length]
  return readyFrameIds.has(next.validTime) ? next : undefined
}
