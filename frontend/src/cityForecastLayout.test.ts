import { describe, expect, it } from 'vitest'
import {
  forecastLeaderLine,
  layoutCityForecastLabels,
  type ForecastLabelAnchor,
  type ForecastLabelRect,
} from './cityForecastLayout'

const viewport = { width: 960, height: 550 }
const label = (
  id: string,
  x: number,
  y: number,
  height = 98,
): ForecastLabelAnchor => ({
  id,
  anchor: { x, y },
  width: 126,
  height,
})
const overlaps = (a: ForecastLabelRect, b: ForecastLabelRect) =>
  a.left < b.left + b.width &&
  a.left + a.width > b.left &&
  a.top < b.top + b.height &&
  a.top + a.height > b.top

function expectInsideAndSeparated(rects: ForecastLabelRect[]) {
  for (const [index, rect] of rects.entries()) {
    expect(rect.left).toBeGreaterThanOrEqual(8)
    expect(rect.top).toBeGreaterThanOrEqual(8)
    expect(rect.left + rect.width).toBeLessThanOrEqual(viewport.width - 8)
    expect(rect.top + rect.height).toBeLessThanOrEqual(viewport.height - 8)
    for (const other of rects.slice(index + 1))
      expect(overlaps(rect, other), JSON.stringify([rect, other])).toBe(false)
  }
}

describe('location-first forecast card layout', () => {
  it('puts a single card on its town, not at the centre of the map', () => {
    const [placed] = layoutCityForecastLabels(
      [label('Halifax', 830, 180)],
      viewport,
    )
    expect(placed.offset).toEqual([0, 0])
    expect(placed.left + placed.width / 2).toBe(830)
    expect(placed.top + placed.height / 2).toBe(180)
  })

  it('keeps separated towns directly anchored', () => {
    const placed = layoutCityForecastLabels(
      [label('West', 200, 200), label('East', 700, 350)],
      viewport,
    )
    expect(placed.map((item) => item.offset)).toEqual([
      [0, 0],
      [0, 0],
    ])
  })

  it('uses nearby free space for clustered towns without hiding their pointers', () => {
    const labels = [
      label('A', 450, 250),
      label('B', 470, 270),
      label('C', 490, 240),
    ]
    const placed = layoutCityForecastLabels(labels, viewport)
    expectInsideAndSeparated(placed)
    for (const card of placed) {
      expect(Math.hypot(...card.offset)).toBeLessThan(220)
      for (const other of labels.filter((item) => item.id !== card.id)) {
        expect(
          overlaps(card, {
            left: other.anchor.x - 4,
            top: other.anchor.y - 4,
            width: 8,
            height: 8,
          }),
        ).toBe(false)
      }
    }
  })

  it('moves only as far as needed to clear the edge or a map control', () => {
    const [edge] = layoutCityForecastLabels([label('Edge', 4, 5)], viewport)
    expect(edge.left).toBe(8)
    expect(edge.top).toBe(8)
    const control = { left: 300, top: 10, width: 226, height: 48 }
    const [nearControl] = layoutCityForecastLabels(
      [label('Town', 400, 40)],
      viewport,
      [control],
    )
    expect(nearControl.left + nearControl.width / 2).toBe(400)
    expect(nearControl.top).toBe(66)
    expect(overlaps(nearControl, control)).toBe(false)
  })

  it('uses measured card heights and is stable when API feature order changes', () => {
    const labels = [label('Tall', 410, 250, 160), label('Short', 420, 350, 80)]
    const placed = layoutCityForecastLabels(labels, viewport)
    expectInsideAndSeparated(placed)
    const reversed = layoutCityForecastLabels([...labels].reverse(), viewport)
    expect([...reversed].reverse()).toEqual(placed)
  })

  it('returns cards to their towns when zooming separates the anchors', () => {
    const close = layoutCityForecastLabels(
      [label('A', 400, 250), label('B', 420, 250)],
      viewport,
    )
    expect(close.some((card) => Math.hypot(...card.offset) > 0)).toBe(true)
    const spread = layoutCityForecastLabels(
      [label('A', 250, 250), label('B', 700, 250)],
      viewport,
    )
    expect(spread.map((card) => card.offset)).toEqual([
      [0, 0],
      [0, 0],
    ])
  })

  it('fits the 23-town provincial overview around the map controls', () => {
    const coordinates = [
      [-65.51, 44.74],
      [-61.99, 45.62],
      [-63.92, 45.38],
      [-63.28, 45.36],
      [-63.29, 45.71],
      [-64.33, 45.41],
      [-64.21, 45.83],
      [-65.76, 44.62],
      [-61.5, 45.39],
      [-62.53, 44.92],
      [-63.6, 44.65],
      [-64.14, 44.99],
      [-60.97, 46.64],
      [-61.36, 45.62],
      [-64.5, 45.08],
      [-64.32, 44.38],
      [-62.64, 45.59],
      [-64.72, 44.04],
      [-60.88, 45.66],
      [-65.32, 43.76],
      [-60.18, 46.13],
      [-60.75, 46.1],
      [-66.12, 43.84],
    ]
    const labels = coordinates.map(([longitude, latitude], index) =>
      label(
        String(index),
        480 + (longitude + 63.1) * 80,
        275 - (latitude - 45.24) * 113,
      ),
    )
    const controls = [
      { left: 14, top: 14, width: 244, height: 30 },
      { left: 367, top: 14, width: 226, height: 50 },
      { left: 918, top: 10, width: 30, height: 90 },
      { left: 600, top: 510, width: 348, height: 28 },
    ]
    const placed = layoutCityForecastLabels(labels, viewport, controls)
    expectInsideAndSeparated(placed)
    for (const card of placed) {
      for (const control of controls)
        expect(overlaps(card, control)).toBe(false)
    }
    const meanDistance =
      placed.reduce((sum, card) => sum + Math.hypot(...card.offset), 0) /
      placed.length
    expect(meanDistance).toBeLessThan(180)
  })

  it('keeps all forecasts and finite positions when a small viewport cannot fit them', () => {
    const placed = layoutCityForecastLabels(
      Array.from({ length: 5 }, (_, index) =>
        label(String(index), 90 + index, 60),
      ),
      { width: 200, height: 120 },
    )
    expect(placed).toHaveLength(5)
    for (const card of placed) {
      expect(card.offset.every(Number.isFinite)).toBe(true)
      expect(card.left).toBeGreaterThanOrEqual(8)
      expect(card.left + card.width).toBeLessThanOrEqual(192)
      expect(card.top).toBeGreaterThanOrEqual(8)
      expect(card.top + card.height).toBeLessThanOrEqual(112)
    }
  })
})

describe('forecast pointer geometry', () => {
  it('hides the pointer when the town is on or inside its own card', () => {
    expect(forecastLeaderLine([0, 0], { width: 126, height: 98 }).length).toBe(
      0,
    )
    expect(
      forecastLeaderLine([20, -10], { width: 126, height: 98 }).length,
    ).toBe(0)
  })

  it.each<[number, number]>([
    [0, 150],
    [0, -150],
    [200, 0],
    [-200, 0],
    [200, 150],
    [-200, -150],
  ])(
    'connects the measured card edge back to the exact town at offset %s, %s',
    (x, y) => {
      const line = forecastLeaderLine([x, y], { width: 126, height: 160 })
      expect(Math.abs(line.start.x) <= 63 && Math.abs(line.start.y) <= 80).toBe(
        true,
      )
      expect(
        Math.abs(line.start.x) === 63 || Math.abs(line.start.y) === 80,
      ).toBe(true)
      expect(line.start.x + Math.cos(line.angle) * line.length).toBeCloseTo(-x)
      expect(line.start.y + Math.sin(line.angle) * line.length).toBeCloseTo(-y)
    },
  )
})
