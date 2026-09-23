// @vitest-environment jsdom
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AppIcon } from './AppIcon'

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const publicFile = (path: string) =>
  readFileSync(join(frontendRoot, 'public', path))
const iconPath = (size: number) => `/icons/crimson-sky-v1-${size}.png`

afterEach(cleanup)

describe('selected app artwork', () => {
  it('preserves the exact user-selected master', () => {
    const source = publicFile('/icons/crimson-sky-v1-source.png')
    expect(createHash('sha256').update(source).digest('hex')).toBe(
      '63033f7cc811c4c51bcf32aafa7c71bca53391d2f663b415193365ee6da0c285',
    )
  })

  it.each([16, 32, 48, 96, 152, 167, 180, 192, 512, 1024])(
    'ships the %s pixel PNG export at the declared dimensions',
    (size) => {
      const png = publicFile(iconPath(size))
      expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
      expect(png.toString('ascii', 12, 16)).toBe('IHDR')
      expect(png.readUInt32BE(16)).toBe(size)
      expect(png.readUInt32BE(20)).toBe(size)
    },
  )

  it('ships conventional browser and Apple discovery files', () => {
    expect(publicFile('/apple-touch-icon.png')).toEqual(
      publicFile(iconPath(180)),
    )
    const ico = publicFile('/favicon.ico')
    expect(ico.readUInt16LE(0)).toBe(0)
    expect(ico.readUInt16LE(2)).toBe(1)
    expect(ico.readUInt16LE(4)).toBeGreaterThan(0)
    expect(ico[6]).toBe(32)
    expect(ico[7]).toBe(32)
  })

  it('registers existing, size-matched favicon and Home Screen assets on every route', () => {
    const html = readFileSync(join(frontendRoot, 'index.html'), 'utf8')
    const head = new DOMParser().parseFromString(html, 'text/html').head
    for (const [rel, sizes] of [
      ['icon', [16, 32, 48]],
      ['apple-touch-icon', [152, 167, 180]],
    ] as const) {
      for (const size of sizes) {
        const link = head.querySelector(
          `link[rel="${rel}"][sizes="${size}x${size}"][href$=".png"]`,
        )
        expect(link?.getAttribute('href')).toBe(iconPath(size))
        expect(publicFile(iconPath(size)).length).toBeGreaterThan(0)
      }
    }
    expect(
      head.querySelector('link[rel="manifest"]')?.getAttribute('href'),
    ).toBe('/site.webmanifest?v=crimson-sky-v1')
    expect(
      head.querySelector('link[href^="/favicon.ico"]')?.getAttribute('href'),
    ).toContain('v=crimson-sky-v1')
    expect(html).not.toContain('weather-model-atlas-ios.png')
  })

  it('uses the same artwork in the app manifest without changing launch behavior', () => {
    const manifest = JSON.parse(
      publicFile('/site.webmanifest').toString('utf8'),
    )
    expect(manifest.icons).toEqual(
      [192, 512].map((size) => ({
        src: iconPath(size),
        sizes: `${size}x${size}`,
        type: 'image/png',
        purpose: 'any',
      })),
    )
    expect(manifest.start_url).toBeUndefined()
    expect(manifest.display).toBeUndefined()
  })

  it('renders a decorative header icon without changing its parent accessible name', () => {
    const { container } = render(<AppIcon />)
    const icon = container.querySelector('img')!
    expect(icon.getAttribute('src')).toBe(iconPath(96))
    expect(icon.getAttribute('alt')).toBe('')
    expect(icon.getAttribute('aria-hidden')).toBe('true')
    expect(icon.width).toBe(36)
    expect(icon.height).toBe(36)
  })
})
