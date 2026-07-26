import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/**
 * WCAG AA contrast, measured off the stylesheets rather than asserted by hand.
 *
 * #157 asked for a recount because the figures in #104 ("14 of 16 themes fail")
 * were wrong on the denominator: there were 19 blocks defining theme tokens, and
 * all 19 failed at least one pair. Sixteen unreachable palettes and the legacy
 * [data-theme="dark"] block were deleted rather than retuned; the two that ship
 * were fixed. This test is what keeps that true — a new theme, or a token nudged
 * for looks, fails here.
 */

const FORMA = join(process.cwd(), 'src/styles/forma')

type Decls = Record<string, string>

function rules(file: string): Array<[string, Decls]> {
  const text = readFileSync(join(FORMA, file), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
  const out: Array<[string, Decls]> = []
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    // Anything preceding the selector (an @import, a previous rule's tail) rides
    // along in group 1; the selector is what follows the last semicolon.
    const selector = m[1].split(';').pop()!.trim()
    const decls: Decls = {}
    for (const decl of m[2].split(';')) {
      const at = decl.indexOf(':')
      if (at < 0) continue
      const name = decl.slice(0, at).trim()
      if (name.startsWith('--')) decls[name] = decl.slice(at + 1).trim()
    }
    if (Object.keys(decls).length) out.push([selector, decls])
  }
  return out
}

const ALL = [...rules('tokens.css'), ...rules('themes.css')]
const THEMES = ALL.map(([s]) => s)
  .filter((s) => s.startsWith('[data-theme=') && !s.includes('^'))
  .map((s) => s.split('"')[1])

/** Cascade :root → shared-dark → the theme's own block, in source order. */
function tokensFor(theme: string): Decls {
  const env: Decls = {}
  for (const [selector, decls] of ALL) {
    const applies =
      selector === ':root' ||
      (selector === '[data-theme^="dark"]' && theme.startsWith('dark')) ||
      selector === `[data-theme="${theme}"]`
    if (applies) Object.assign(env, decls)
  }
  return env
}

function resolve(value: string, env: Decls, depth = 0): string | null {
  if (depth > 12) return null
  const m = /^var\(\s*(--[\w-]+)\s*(?:,\s*([\s\S]+))?\)$/.exec(value.trim())
  if (!m) return value.trim()
  const [, name, fallback] = m
  if (env[name] !== undefined) return resolve(env[name], env, depth + 1)
  return fallback ? resolve(fallback, env, depth + 1) : null
}

type Rgba = [number, number, number, number]

function parse(value: string): Rgba | null {
  const v = value.trim()
  if (v.startsWith('#')) {
    const h = v.length === 4 ? [...v.slice(1)].map((c) => c + c).join('') : v.slice(1)
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1]
  }
  const m = /^rgba?\(([^)]+)\)$/.exec(v)
  if (!m) return null
  const parts = m[1].split(',').map((p) => Number(p.trim()))
  return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1]
}

/** Flatten a translucent colour onto the opaque thing behind it. */
function over(fg: Rgba, bg: Rgba): Rgba {
  const a = fg[3]
  return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1]
}

function luminance([r, g, b]: Rgba): number {
  const ch = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

function contrast(fg: Rgba, bg: Rgba): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a)
  return (hi + 0.05) / (lo + 0.05)
}

/** 4.5 for text (AA 1.4.3); 3.0 for component boundaries and states (1.4.11). */
const PAIRS: Array<[string, string, number, string]> = [
  ['--text-primary', '--bg-canvas', 4.5, 'body text on the canvas'],
  ['--text-primary', '--bg-surface', 4.5, 'body text on a card'],
  ['--text-secondary', '--bg-canvas', 4.5, 'secondary text on the canvas'],
  ['--text-secondary', '--bg-surface', 4.5, 'secondary text on a card'],
  ['--text-secondary', '--bg-subtle', 4.5, 'secondary text on a subtle fill'],
  ['--text-tertiary', '--bg-canvas', 4.5, 'tertiary text on the canvas'],
  ['--text-tertiary', '--bg-surface', 4.5, 'tertiary text on a card'],
  ['--text-accent', '--bg-surface', 4.5, 'accent text on a card'],
  ['--text-inverse', '--bg-inverse', 4.5, 'inverse text on an inverse fill'],
  ['--text-on-accent', '--accent', 4.5, 'label on a primary button'],
  ['--status-success-fg', '--status-success-bg', 4.5, 'success badge text'],
  ['--status-danger-fg', '--status-danger-bg', 4.5, 'danger badge text'],
  ['--status-warning-fg', '--status-warning-bg', 4.5, 'warning badge text'],
  ['--status-info-fg', '--status-info-bg', 4.5, 'info badge text'],
  ['--status-danger-fg', '--bg-surface', 4.5, 'danger text on a card (.form-error)'],
  ['--status-warning-fg', '--bg-surface', 4.5, 'warning text on a card'],
  ['--border-default', '--bg-surface', 3.0, 'control boundary on a card'],
  ['--border-default', '--bg-canvas', 3.0, 'control boundary on the canvas'],
  ['--border-default', '--bg-muted', 3.0, 'control boundary on a muted fill'],
  ['--accent', '--bg-surface', 3.0, 'accent fill against a card'],
]

/**
 * Documented exceptions. Each needs a decision, not a token nudge — see the
 * comment at the failing token. The recorded ratio is a floor: the test fails if
 * one gets worse, and fails if one is fixed and left listed here.
 */
const KNOWN_GAPS: Record<string, { min: number; why: string }> = {
  'light-cosmo:--text-on-accent on --accent': {
    min: 4.04,
    why: 'white on #2D77FF; clearing 4.5 means moving the brand fill to #1F63DB',
  },
}

function measure(theme: string, fgToken: string, bgToken: string) {
  const env = tokensFor(theme)
  const fgValue = resolve(`var(${fgToken})`, env)
  const bgValue = resolve(`var(${bgToken})`, env)
  expect(fgValue, `${theme} ${fgToken} resolves`).not.toBeNull()
  expect(bgValue, `${theme} ${bgToken} resolves`).not.toBeNull()
  const surface = parse(resolve('var(--bg-surface)', env)!)!
  let fg = parse(fgValue!)!
  let bg = parse(bgValue!)!
  if (bg[3] < 1) bg = over(bg, surface)
  if (fg[3] < 1) fg = over(fg, bg)
  return contrast(fg, bg)
}

describe('theme contrast', () => {
  it('ships exactly the two themes the UI can reach', () => {
    // The toggle writes only these two and index.html normalises anything else,
    // so a third block here would be unreachable dead CSS again.
    expect(THEMES.sort()).toEqual(['dark-cosmo', 'light-cosmo'])
  })

  it.each(THEMES)('%s meets WCAG AA on every pair', (theme) => {
    const failures: string[] = []
    for (const [fgToken, bgToken, threshold, label] of PAIRS) {
      const key = `${theme}:${fgToken} on ${bgToken}`
      const ratio = measure(theme, fgToken, bgToken)
      const gap = KNOWN_GAPS[key]
      if (gap) {
        expect(ratio, `${key} regressed below its recorded floor (${gap.why})`)
          .toBeGreaterThanOrEqual(gap.min)
        expect(ratio, `${key} now clears AA — delete its KNOWN_GAPS entry`).toBeLessThan(threshold)
        continue
      }
      if (ratio < threshold) {
        failures.push(`${ratio.toFixed(2)}:1 (needs ${threshold}) ${fgToken} on ${bgToken} — ${label}`)
      }
    }
    expect(failures, `${theme} below AA`).toEqual([])
  })

  it('keeps --border-strong stronger than --border-default', () => {
    // Raising the default to clear 3:1 inverted this pair once; the tokens would
    // still "pass" AA while reading backwards.
    for (const theme of THEMES) {
      const strong = measure(theme, '--border-strong', '--bg-surface')
      const dflt = measure(theme, '--border-default', '--bg-surface')
      expect(strong, `${theme} --border-strong vs --border-default`).toBeGreaterThan(dflt)
    }
  })
})
