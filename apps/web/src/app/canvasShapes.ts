// Canvas shape library (Phase 13d).
//
// Excalidraw's toolbar ships five drawable primitives — rectangle, diamond,
// ellipse, arrow, line — plus text/image/frame. Everything a planning diagram
// actually wants (triangle, hexagon, cylinder, chevron, callout, swimlane…) has
// to be drawn by hand, every time. This module supplies those as *library
// items*: they show up in Excalidraw's own library panel and are dragged onto
// the canvas like any other library shape.
//
// ponytail: seeded into `initialData.libraryItems`, not a bespoke shape palette.
// The library panel is the native surface users already know, so this is data,
// not UI. It also keeps the canvas offline-first — no libraries.excalidraw.com
// fetch, matching the self-hosted-fonts stance in CanvasEditor.tsx.
//
// No Excalidraw import here on purpose — same reason as canvasCards.ts: this
// module stays jsdom-safe so the geometry can be unit-tested. CanvasEditor runs
// the skeletons through convertToExcalidrawElements.

/** A point in unit space: [0,0] top-left … [1,1] bottom-right of the shape box. */
export type UnitPoint = [number, number]

/** The subset of Excalidraw's element-skeleton shape we emit. */
export interface ShapeElement {
  type: 'line' | 'rectangle' | 'ellipse' | 'diamond'
  x: number
  y: number
  width: number
  height: number
  points?: UnitPoint[]
  backgroundColor?: string
  strokeColor?: string
  fillStyle?: string
  roundness?: { type: number } | null
  label?: { text: string; fontSize: number; strokeColor: string }
}

export type ShapeGroup = 'Basic' | 'Flowchart' | 'Arrows' | 'Annotation' | 'Planning'

export interface CanvasShape {
  key: string
  name: string
  group: ShapeGroup
  elements: ShapeElement[]
}

/** Default drawn size, in scene units, of a single-shape library item. */
export const SHAPE_SIZE = 100

const STROKE = '#1e1e1e'
const NOTE_COLORS: [string, string, string][] = [
  ['yellow', '#ffec99', '#f08c00'],
  ['blue', '#a5d8ff', '#1971c2'],
  ['green', '#b2f2bb', '#2f9e44'],
  ['pink', '#ffc9c9', '#e03131'],
]

// ── geometry ────────────────────────────────────────────────────────────────

/** Vertices of a regular n-gon inscribed in the unit box.
 *  `rotation` is in radians; the default puts the first vertex at the top. */
export function regularPolygon(sides: number, rotation = -Math.PI / 2): UnitPoint[] {
  const pts: UnitPoint[] = []
  for (let i = 0; i < sides; i++) {
    const a = rotation + (i * 2 * Math.PI) / sides
    pts.push([0.5 + 0.5 * Math.cos(a), 0.5 + 0.5 * Math.sin(a)])
  }
  return pts
}

/** Vertices of an n-pointed star; `innerRatio` is the valley radius as a
 *  fraction of the point radius. */
export function starPolygon(points: number, innerRatio = 0.42): UnitPoint[] {
  const pts: UnitPoint[] = []
  for (let i = 0; i < points * 2; i++) {
    const r = (i % 2 === 0 ? 0.5 : 0.5 * innerRatio)
    const a = -Math.PI / 2 + (i * Math.PI) / points
    pts.push([0.5 + r * Math.cos(a), 0.5 + r * Math.sin(a)])
  }
  return pts
}

/** Turn unit-space vertices into a closed Excalidraw `line` element.
 *
 *  Excalidraw stores line points *relative to the element origin*, so the ring
 *  is translated to start at [0,0]; width/height come from the point bounding
 *  box rather than the nominal box, because a polygon rarely fills its box
 *  (a triangle's ink is narrower than its bounds). The first vertex is repeated
 *  at the end — that closing segment is what makes the fill render. */
export function closedPolygon(
  unit: UnitPoint[],
  size = SHAPE_SIZE,
  style: Partial<ShapeElement> = {},
): ShapeElement {
  const scaled = unit.map(([x, y]) => [x * size, y * size] as UnitPoint)
  const xs = scaled.map((p) => p[0])
  const ys = scaled.map((p) => p[1])
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const points = scaled.map(([x, y]) => [x - minX, y - minY] as UnitPoint)
  points.push([points[0][0], points[0][1]])
  return {
    type: 'line',
    x: 0,
    y: 0,
    width: Math.max(...xs) - minX,
    height: Math.max(...ys) - minY,
    points,
    strokeColor: STROKE,
    backgroundColor: 'transparent',
    fillStyle: 'solid',
    ...style,
  }
}

/** A straight two-point line, in unit space. */
function segment(from: UnitPoint, to: UnitPoint, size = SHAPE_SIZE): ShapeElement {
  return {
    type: 'line',
    x: from[0] * size,
    y: from[1] * size,
    width: (to[0] - from[0]) * size,
    height: (to[1] - from[1]) * size,
    points: [
      [0, 0],
      [(to[0] - from[0]) * size, (to[1] - from[1]) * size],
    ],
    strokeColor: STROKE,
  }
}

function box(
  x: number, y: number, w: number, h: number,
  style: Partial<ShapeElement> = {},
  size = SHAPE_SIZE,
): ShapeElement {
  return {
    type: 'rectangle',
    x: x * size,
    y: y * size,
    width: w * size,
    height: h * size,
    strokeColor: STROKE,
    backgroundColor: 'transparent',
    fillStyle: 'solid',
    ...style,
  }
}

function oval(
  x: number, y: number, w: number, h: number,
  style: Partial<ShapeElement> = {},
  size = SHAPE_SIZE,
): ShapeElement {
  return { ...box(x, y, w, h, style, size), type: 'ellipse' }
}

const poly = (key: string, name: string, group: ShapeGroup, unit: UnitPoint[]): CanvasShape => ({
  key,
  name,
  group,
  elements: [closedPolygon(unit)],
})

// ── the library ─────────────────────────────────────────────────────────────

const BASIC: CanvasShape[] = [
  poly('triangle', 'Triangle', 'Basic', [[0.5, 0], [1, 1], [0, 1]]),
  poly('right-triangle', 'Right triangle', 'Basic', [[0, 0], [0, 1], [1, 1]]),
  poly('pentagon', 'Pentagon', 'Basic', regularPolygon(5)),
  poly('hexagon', 'Hexagon', 'Basic', regularPolygon(6, 0)),
  poly('octagon', 'Octagon', 'Basic', regularPolygon(8, -Math.PI / 8)),
  poly('star', 'Star', 'Basic', starPolygon(5)),
  poly('cross', 'Cross', 'Basic', [
    [0.35, 0], [0.65, 0], [0.65, 0.35], [1, 0.35], [1, 0.65], [0.65, 0.65],
    [0.65, 1], [0.35, 1], [0.35, 0.65], [0, 0.65], [0, 0.35], [0.35, 0.35],
  ]),
  poly('l-shape', 'L-shape', 'Basic', [
    [0, 0], [0.4, 0], [0.4, 0.6], [1, 0.6], [1, 1], [0, 1],
  ]),
]

const FLOWCHART: CanvasShape[] = [
  {
    key: 'terminator',
    name: 'Terminator (start/end)',
    group: 'Flowchart',
    // A stadium: a wide rectangle with Excalidraw's adaptive rounding.
    elements: [box(0, 0.25, 1, 0.5, { roundness: { type: 3 } })],
  },
  poly('data', 'Data / I-O', 'Flowchart', [[0.25, 0.15], [1, 0.15], [0.75, 0.85], [0, 0.85]]),
  poly('trapezoid', 'Manual operation', 'Flowchart', [[0.2, 0.15], [0.8, 0.15], [1, 0.85], [0, 0.85]]),
  poly('preparation', 'Preparation', 'Flowchart', [
    [0.15, 0.15], [0.85, 0.15], [1, 0.5], [0.85, 0.85], [0.15, 0.85], [0, 0.5],
  ]),
  poly('document', 'Document', 'Flowchart', [
    [0, 0.1], [1, 0.1], [1, 0.8], [0.75, 0.92], [0.5, 0.8], [0.25, 0.92], [0, 0.8],
  ]),
  poly('manual-input', 'Manual input', 'Flowchart', [[0, 0.25], [1, 0.1], [1, 0.9], [0, 0.9]]),
  {
    key: 'cylinder',
    name: 'Database',
    group: 'Flowchart',
    // Body first, then the cap on top, so the cap's stroke hides the seam.
    elements: [
      oval(0, 0.7, 1, 0.3),
      segment([0, 0.15], [0, 0.85]),
      segment([1, 0.15], [1, 0.85]),
      oval(0, 0, 1, 0.3, { backgroundColor: '#ffffff' }),
    ],
  },
  poly('cloud', 'Cloud', 'Flowchart', [
    [0.15, 0.78], [0.04, 0.66], [0.07, 0.5], [0.19, 0.42], [0.21, 0.27],
    [0.37, 0.18], [0.55, 0.21], [0.68, 0.13], [0.83, 0.24], [0.91, 0.4],
    [0.96, 0.56], [0.9, 0.72], [0.74, 0.8], [0.5, 0.82], [0.3, 0.81],
  ]),
]

const ARROWS: CanvasShape[] = [
  poly('chevron', 'Chevron', 'Arrows', [
    [0, 0.15], [0.7, 0.15], [1, 0.5], [0.7, 0.85], [0, 0.85], [0.3, 0.5],
  ]),
  poly('block-arrow', 'Block arrow', 'Arrows', [
    [0, 0.3], [0.6, 0.3], [0.6, 0.08], [1, 0.5], [0.6, 0.92], [0.6, 0.7], [0, 0.7],
  ]),
  poly('double-arrow', 'Double arrow', 'Arrows', [
    [0, 0.5], [0.25, 0.1], [0.25, 0.32], [0.75, 0.32], [0.75, 0.1], [1, 0.5],
    [0.75, 0.9], [0.75, 0.68], [0.25, 0.68], [0.25, 0.9],
  ]),
]

const ANNOTATION: CanvasShape[] = [
  {
    key: 'speech-bubble',
    name: 'Speech bubble',
    group: 'Annotation',
    elements: [
      closedPolygon([
        [0, 0], [1, 0], [1, 0.72], [0.42, 0.72], [0.22, 1], [0.24, 0.72], [0, 0.72],
      ], SHAPE_SIZE, { backgroundColor: '#ffffff' }),
    ],
  },
  poly('banner', 'Banner', 'Annotation', [
    [0, 0.25], [0.85, 0.25], [1, 0.5], [0.85, 0.75], [0, 0.75], [0.12, 0.5],
  ]),
  {
    key: 'actor',
    name: 'Actor',
    group: 'Annotation',
    elements: [
      oval(0.35, 0, 0.3, 0.3),
      segment([0.5, 0.3], [0.5, 0.66]),
      segment([0.18, 0.44], [0.82, 0.44]),
      segment([0.5, 0.66], [0.26, 1]),
      segment([0.5, 0.66], [0.74, 1]),
    ],
  },
  poly('warning', 'Warning', 'Annotation', [[0.5, 0.05], [1, 0.9], [0, 0.9]]),
]

const stickies: CanvasShape[] = NOTE_COLORS.map(([name, bg, stroke]) => ({
  key: `sticky-${name}`,
  name: `Sticky note (${name})`,
  group: 'Planning' as const,
  elements: [
    box(0, 0, 1, 1, {
      backgroundColor: bg,
      strokeColor: stroke,
      roundness: null, // square corners, like a real sticky
      label: { text: 'Note', fontSize: 20, strokeColor: STROKE },
    }, 160),
  ],
}))

const PLANNING: CanvasShape[] = [
  ...stickies,
  {
    key: 'kanban',
    name: 'Kanban board (3 columns)',
    group: 'Planning',
    elements: ['To do', 'Doing', 'Done'].flatMap((title, i) => {
      const left = i * 0.35
      return [
        box(left, 0, 0.3, 1, { backgroundColor: '#f1f3f5' }, 320),
        box(left, 0, 0.3, 0.12, {
          backgroundColor: '#dee2e6',
          label: { text: title, fontSize: 16, strokeColor: STROKE },
        }, 320),
      ]
    }),
  },
  {
    key: 'matrix',
    name: '2×2 matrix',
    group: 'Planning',
    elements: [
      box(0, 0, 0.5, 0.5, { backgroundColor: '#e8f0fe' }, 260),
      box(0.5, 0, 0.5, 0.5, { backgroundColor: '#e9f6ec' }, 260),
      box(0, 0.5, 0.5, 0.5, { backgroundColor: '#fff3e0' }, 260),
      box(0.5, 0.5, 0.5, 0.5, { backgroundColor: '#fdeceb' }, 260),
    ],
  },
  {
    key: 'swimlane',
    name: 'Swimlane',
    group: 'Planning',
    elements: [
      box(0, 0, 1, 1, {}, 320),
      box(0, 0, 0.14, 1, {
        backgroundColor: '#dee2e6',
        label: { text: 'Lane', fontSize: 14, strokeColor: STROKE },
      }, 320),
    ],
  },
]

/** Every shape offered in the canvas library panel. */
export const CANVAS_SHAPES: CanvasShape[] = [
  ...BASIC,
  ...FLOWCHART,
  ...ARROWS,
  ...ANNOTATION,
  ...PLANNING,
]

export const SHAPE_GROUPS: ShapeGroup[] = ['Basic', 'Flowchart', 'Arrows', 'Annotation', 'Planning']
