// @vitest-environment jsdom

import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { expect, it } from 'vitest'

// Vitest stubs CSS imports; load the actual styles to exercise the cascade.
const require = createRequire(import.meta.url)
const maplibreStyles = readFileSync(
  require.resolve('maplibre-gl/dist/maplibre-gl.css'),
  'utf8',
)
const appStyles = readFileSync(require.resolve('./styles.css'), 'utf8')

it('keeps every forecast marker out of document flow so its pointer stays at the mapped coordinate', () => {
  // Match main.tsx: application styles load after MapLibre's positioning rules.
  const styles = [maplibreStyles, appStyles].map((css) => {
    const style = document.createElement('style')
    style.textContent = css
    return style
  })
  const container = document.createElement('div')
  container.className = 'maplibregl-canvas-container'
  const markers = ['Yarmouth', 'Halifax', 'Sydney'].map((name) => {
    const marker = document.createElement('article')
    marker.className = 'city-forecast-label maplibregl-marker'
    marker.textContent = name
    container.append(marker)
    return marker
  })
  document.head.append(...styles)
  document.body.append(container)

  try {
    for (const marker of markers) {
      const style = getComputedStyle(marker)
      expect(style.position).toBe('absolute')
      expect(style.top).toBe('0px')
      expect(style.left).toBe('0px')
    }
  } finally {
    for (const style of styles) style.remove()
    container.remove()
  }
})
