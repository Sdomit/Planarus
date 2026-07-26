import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'


/**
 * Guard against phantom CSS custom properties: a `var(--x)` whose `--x` is
 * defined in no stylesheet and set by no component.
 *
 * These fail silently. With a fallback the site renders one frozen value and
 * ignores the theme; without one the whole declaration is invalid at
 * computed-value time and the property silently reverts to its initial value.
 * Six of them had accumulated (#157) — two of which were hidden by fallbacks
 * that made the reference look deliberate, and one of which (`--space-9`) was
 * zeroing the padding that keeps input text clear of its icon.
 */

// Under jsdom `import.meta.url` is an http:// URL, so the path comes from the
// runner's cwd (the `apps/web` package root) instead. The first test below
// fails loudly if that ever stops resolving to the real source tree.
const SRC = join(process.cwd(), 'src')
const SCANNED = ['.css', '.ts', '.tsx']

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return SCANNED.some((ext) => name.endsWith(ext)) ? [path] : []
  })
}

/** `--x: value` in CSS, `'--x': value` in a style object, and setProperty('--x', …). */
const DEFINITION = /(?:^|[\s;{'"])(--[A-Za-z0-9-]+)\s*['"]?\s*:/gm
const SET_PROPERTY = /setProperty\(\s*['"`](--[A-Za-z0-9-]+)/g
const REFERENCE = /var\(\s*(--[A-Za-z0-9-]+)/g

function matches(text: string, re: RegExp): string[] {
  return [...text.matchAll(re)].map((m) => m[1])
}

describe('CSS custom properties', () => {
  const files = sourceFiles(SRC).map((path) => ({ path, text: readFileSync(path, 'utf8') }))

  it('scans the whole web source tree', () => {
    // A broken walk would make every assertion below vacuously true.
    expect(files.length).toBeGreaterThan(50)
    expect(files.some((f) => f.path.endsWith('forma/tokens.css'))).toBe(true)
  })

  it('never references a token that nothing defines', () => {
    const defined = new Set(
      files.flatMap((f) => [...matches(f.text, DEFINITION), ...matches(f.text, SET_PROPERTY)]),
    )

    const phantom = new Map<string, string[]>()
    for (const { path, text } of files) {
      for (const token of new Set(matches(text, REFERENCE))) {
        if (defined.has(token)) continue
        phantom.set(token, [...(phantom.get(token) ?? []), path.slice(SRC.length)])
      }
    }

    const report = [...phantom.entries()].map(([t, at]) => `${t} → ${at.join(', ')}`)
    expect(report, 'referenced but defined nowhere').toEqual([])
  })
})
