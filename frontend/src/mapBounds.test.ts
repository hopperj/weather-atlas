import { describe, expect, it } from 'vitest'
import { cameraBounds } from './mapBounds'

describe('cameraBounds', () => {
  it('preserves an ordinary regional extent', () => {
    expect(cameraBounds([-141, 39, -42, 84])).toEqual([-141, 39, -42, 84])
  })

  it('clamps a global raster half-cell envelope for Web Mercator', () => {
    expect(cameraBounds([-180.075, -90.075, 179.925, 90.075])).toEqual([
      -180, -85.051129, 179.925, 85.051129,
    ])
  })

  it('rejects non-finite and collapsed extents', () => {
    expect(cameraBounds([Number.NaN, 39, -42, 84])).toBeNull()
    expect(cameraBounds([200, 10, 210, 20])).toBeNull()
  })
})
