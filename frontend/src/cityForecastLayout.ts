type Point = { x: number; y: number }
type Size = { width: number; height: number }

export type ForecastLabelRect = Size & { left: number; top: number }
export type ForecastLabelAnchor = Size & { id: string; anchor: Point }
export type ForecastLabelPlacement = ForecastLabelRect & {
  id: string
  offset: [number, number]
}

const GAP = 8
const EDGE_PADDING = 8

function rectAt(point: Point, size: Size): ForecastLabelRect {
  return {
    left: point.x - size.width / 2,
    top: point.y - size.height / 2,
    width: size.width,
    height: size.height,
  }
}

function overlapArea(a: ForecastLabelRect, b: ForecastLabelRect, gap = GAP) {
  const width =
    Math.min(a.left + a.width + gap, b.left + b.width) -
    Math.max(a.left - gap, b.left)
  const height =
    Math.min(a.top + a.height + gap, b.top + b.height) -
    Math.max(a.top - gap, b.top)
  return width > 1e-7 && height > 1e-7 ? width * height : 0
}

/** Keep cards on their towns whenever possible, otherwise use the closest
 * available rectangle. Positions are deterministic, including across periods. */
export function layoutCityForecastLabels(
  labels: readonly ForecastLabelAnchor[],
  viewport: Size,
  obstacles: readonly ForecastLabelRect[] = [],
): ForecastLabelPlacement[] {
  const placed = new Map<string, ForecastLabelPlacement>()
  // Preserve geographic ordering while reserving every other town's pointer.
  const ordered = [...labels].sort(
    (a, b) =>
      a.anchor.x - b.anchor.x ||
      a.anchor.y - b.anchor.y ||
      a.id.localeCompare(b.id),
  )

  // A few relaxation passes let earlier cards reclaim closer space and resolve
  // packing conflicts once the whole cluster has been placed.
  let gap = GAP
  for (let pass = 0; pass < 4; pass += 1) {
    let changed = false
    for (const label of ordered) {
      const previous = placed.get(label.id)
      placed.delete(label.id)
      const halfWidth = label.width / 2
      const halfHeight = label.height / 2
      const insetX = Math.min(viewport.width / 2, halfWidth + EDGE_PADDING)
      const insetY = Math.min(viewport.height / 2, halfHeight + EDGE_PADDING)
      const clampX = (x: number) =>
        Math.max(insetX, Math.min(viewport.width - insetX, x))
      const clampY = (y: number) =>
        Math.max(insetY, Math.min(viewport.height - insetY, y))
      // Never place a card over another town's pointer when there is free space.
      const fixed = obstacles
      const pointers = labels
        .filter((other) => other.id !== label.id)
        .map((other) => rectAt(other.anchor, { width: 8, height: 8 }))
      const cards = [...placed.values()]
      const blocked = [...fixed, ...cards, ...pointers]
      const xs = new Set(
        [
          label.anchor.x,
          insetX,
          viewport.width - insetX,
          ...blocked.flatMap((rect) => [
            rect.left - halfWidth - gap,
            rect.left + rect.width + halfWidth + gap,
          ]),
        ].map(clampX),
      )
      const ys = new Set(
        [
          label.anchor.y,
          insetY,
          viewport.height - insetY,
          ...blocked.flatMap((rect) => [
            rect.top - halfHeight - gap,
            rect.top + rect.height + halfHeight + gap,
          ]),
        ].map(clampY),
      )
      // The nearest feasible position lies at the anchor, an obstacle edge, or a
      // viewport edge. Test their intersections instead of snapping to a grid.
      const candidates = [...xs]
        .flatMap((x) =>
          [...ys].map((y) => ({
            x,
            y,
            distance: (x - label.anchor.x) ** 2 + (y - label.anchor.y) ** 2,
          })),
        )
        .sort((a, b) => a.distance - b.distance || a.y - b.y || a.x - b.x)

      let best = candidates[0]
      let bestFixedOverlap = Infinity
      let bestCardOverlap = Infinity
      let bestPointerOverlap = Infinity
      for (const candidate of candidates) {
        const rect = rectAt(candidate, label)
        const fixedOverlap = fixed.reduce(
          (sum, item) => sum + overlapArea(rect, item, gap),
          0,
        )
        const cardOverlap = cards.reduce(
          (sum, item) => sum + overlapArea(rect, item, gap),
          0,
        )
        const pointerOverlap = pointers.reduce(
          (sum, item) => sum + overlapArea(rect, item, gap),
          0,
        )
        if (fixedOverlap === 0 && cardOverlap === 0 && pointerOverlap === 0) {
          best = candidate
          break
        }
        // A tiny viewport may not fit every card: minimize overlap rather than
        // dropping forecasts or sending them outside the map.
        if (
          fixedOverlap < bestFixedOverlap ||
          (fixedOverlap === bestFixedOverlap &&
            (cardOverlap < bestCardOverlap ||
              (cardOverlap === bestCardOverlap &&
                pointerOverlap < bestPointerOverlap)))
        ) {
          best = candidate
          bestFixedOverlap = fixedOverlap
          bestCardOverlap = cardOverlap
          bestPointerOverlap = pointerOverlap
        }
      }
      placed.set(label.id, {
        id: label.id,
        ...rectAt(best, label),
        offset: [best.x - label.anchor.x, best.y - label.anchor.y],
      })
      if (
        !previous ||
        Math.abs(previous.left - (best.x - halfWidth)) > 0.01 ||
        Math.abs(previous.top - (best.y - halfHeight)) > 0.01
      )
        changed = true
    }
    const cards = [...placed.values()]
    if (
      gap > 0 &&
      cards.some((card, index) =>
        cards.slice(index + 1).some((other) => overlapArea(card, other, 0) > 0),
      )
    ) {
      // Compact spacing only when the overview is too crowded for normal gaps.
      gap = pass >= 2 ? 0 : gap / 2
      changed = true
    }
    if (!changed) break
  }
  // Improve the assignment globally: a late card should not be sent across
  // the province just because a nearer slot was occupied earlier. Swaps keep
  // cards separated while shortening their total distance from their towns.
  for (let pass = 0; pass < ordered.length; pass += 1) {
    let changed = false
    for (const [index, a] of ordered.entries()) {
      for (const b of ordered.slice(index + 1)) {
        const oldA = placed.get(a.id)!
        const oldB = placed.get(b.id)!
        // Do not trade away a card that already contains its own town.
        const onTown = (card: ForecastLabelPlacement) =>
          Math.abs(card.offset[0]) <= card.width / 2 &&
          Math.abs(card.offset[1]) <= card.height / 2
        if (onTown(oldA) || onTown(oldB)) continue
        const centreA = {
          x: oldA.left + oldA.width / 2,
          y: oldA.top + oldA.height / 2,
        }
        const centreB = {
          x: oldB.left + oldB.width / 2,
          y: oldB.top + oldB.height / 2,
        }
        const offsetA: [number, number] = [
          centreB.x - a.anchor.x,
          centreB.y - a.anchor.y,
        ]
        const offsetB: [number, number] = [
          centreA.x - b.anchor.x,
          centreA.y - b.anchor.y,
        ]
        const cost = (offset: [number, number]) =>
          offset[0] ** 2 + offset[1] ** 2
        if (
          cost(offsetA) + cost(offsetB) >=
          cost(oldA.offset) + cost(oldB.offset) - 0.01
        )
          continue
        const nextA = { id: a.id, ...rectAt(centreB, a), offset: offsetA }
        const nextB = { id: b.id, ...rectAt(centreA, b), offset: offsetB }
        const blocked = [
          ...obstacles,
          ...[...placed.values()].filter(
            (card) => card.id !== a.id && card.id !== b.id,
          ),
        ]
        const fits = (card: ForecastLabelPlacement) =>
          card.left >= EDGE_PADDING &&
          card.top >= EDGE_PADDING &&
          card.left + card.width <= viewport.width - EDGE_PADDING &&
          card.top + card.height <= viewport.height - EDGE_PADDING &&
          blocked.every((other) => overlapArea(card, other, 0) === 0)
        if (!fits(nextA) || !fits(nextB) || overlapArea(nextA, nextB, 0) > 0)
          continue
        placed.set(a.id, nextA)
        placed.set(b.id, nextB)
        changed = true
      }
    }
    if (!changed) break
  }
  return labels.map((label) => placed.get(label.id)!)
}

export function forecastLeaderLine(offset: [number, number], size: Size) {
  const anchor = { x: -offset[0], y: -offset[1] }
  const edgeScale = Math.min(
    anchor.x === 0 ? 1 : size.width / 2 / Math.abs(anchor.x),
    anchor.y === 0 ? 1 : size.height / 2 / Math.abs(anchor.y),
    1,
  )
  const start = { x: anchor.x * edgeScale, y: anchor.y * edgeScale }
  const dx = anchor.x - start.x
  const dy = anchor.y - start.y
  return {
    anchor,
    start,
    length: Math.hypot(dx, dy),
    angle: Math.atan2(dy, dx),
  }
}
