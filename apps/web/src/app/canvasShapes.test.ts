import { describe, it, expect } from 'vitest'
import {
  CANVAS_SHAPES,
  SHAPE_GROUPS,
  SHAPE_SIZE,
  closedPolygon,
  regularPolygon,
  starPolygon,
} from './canvasShapes'

describe('canvasShapes geometry', () => {
  it('builds a regular n-gon with n vertices on the inscribed circle', () => {
    for (const n of [5, 6, 8]) {
      const pts = regularPolygon(n)
      expect(pts).toHaveLength(n)
      // every vertex sits at radius 0.5 from the unit box centre
      for (const [x, y] of pts) {
        expect(Math.hypot(x - 0.5, y - 0.5)).toBeCloseTo(0.5, 6)
      }
    }
    // default rotation puts the first vertex at top-centre
    expect(regularPolygon(6)[0]).toEqual([expect.closeTo(0.5, 6), expect.closeTo(0, 6)])
  })

  it('alternates point and valley radii on a star', () => {
    const pts = starPolygon(5, 0.4)
    expect(pts).toHaveLength(10)
    const radii = pts.map(([x, y]) => Math.hypot(x - 0.5, y - 0.5))
    radii.forEach((r, i) => expect(r).toBeCloseTo(i % 2 === 0 ? 0.5 : 0.2, 6))
  })

  it('closes the ring, normalizes to the origin, and sizes from the bounding box', () => {
    // a triangle: ink spans the full box, but the apex means points start at y=0
    const el = closedPolygon([[0.5, 0], [1, 1], [0, 1]])
    expect(el.type).toBe('line')
    // 3 vertices + the repeated first vertex that closes (and so fills) the shape
    expect(el.points).toHaveLength(4)
    expect(el.points![3]).toEqual(el.points![0])
    // translated so the top-left of the ink is the element origin
    expect(Math.min(...el.points!.map((p) => p[0]))).toBe(0)
    expect(Math.min(...el.points!.map((p) => p[1]))).toBe(0)
    expect(el.width).toBe(SHAPE_SIZE)
    expect(el.height).toBe(SHAPE_SIZE)
  })

  it('sizes from the ink, not the nominal box, when a shape is inset', () => {
    // a shape occupying only the middle half horizontally
    const el = closedPolygon([[0.25, 0], [0.75, 0], [0.75, 1], [0.25, 1]])
    expect(el.width).toBe(SHAPE_SIZE / 2)
    expect(el.height).toBe(SHAPE_SIZE)
  })
})

describe('canvasShapes library', () => {
  it('exposes a usable set with unique keys in known groups', () => {
    expect(CANVAS_SHAPES.length).toBeGreaterThanOrEqual(20)
    const keys = CANVAS_SHAPES.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
    for (const s of CANVAS_SHAPES) {
      expect(SHAPE_GROUPS).toContain(s.group)
      expect(s.name.trim()).not.toBe('')
      expect(s.elements.length).toBeGreaterThan(0)
    }
  })

  // The real hazard: one bad vertex list yields NaN coordinates, and Excalidraw
  // renders that as an invisible or scene-corrupting element rather than failing.
  it('emits only finite geometry', () => {
    for (const shape of CANVAS_SHAPES) {
      for (const el of shape.elements) {
        for (const [field, v] of Object.entries({ x: el.x, y: el.y, w: el.width, h: el.height })) {
          expect(Number.isFinite(v), `${shape.key}.${field}`).toBe(true)
        }
        // A straight segment is flat on one axis by definition (the cylinder's
        // sides are vertical, so width 0 is correct); it just may not be a
        // zero-length point. Everything else must have real extent on both axes.
        if (el.points?.length === 2) {
          expect(el.width || el.height, `${shape.key} segment`).not.toBe(0)
        } else {
          expect(el.width, `${shape.key} width`).toBeGreaterThan(0)
          expect(el.height, `${shape.key} height`).toBeGreaterThan(0)
        }
        for (const p of el.points ?? []) {
          expect(Number.isFinite(p[0]) && Number.isFinite(p[1]), `${shape.key} point`).toBe(true)
        }
      }
    }
  })

  it('closes every polygon so filled shapes actually fill', () => {
    for (const shape of CANVAS_SHAPES) {
      for (const el of shape.elements) {
        // segments (2 points) are open by design; rings must return to the start
        if (!el.points || el.points.length <= 2) continue
        expect(el.points[el.points.length - 1], `${shape.key} ring`).toEqual(el.points[0])
      }
    }
  })
})
