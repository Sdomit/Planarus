// Pure card-model helpers for Phase 13 entity-binding canvas cards.
// No Excalidraw import here on purpose: this module stays jsdom-safe so its
// logic can be unit-tested (CanvasEditor.tsx itself can't be imported in tests
// because Excalidraw crashes jsdom at import time).
import type {
  Task, Decision, Risk, Milestone,
  Phase, Stage, Blocker, Todo, DocSummary, CalendarEvent,
} from '../api/client'

export type EntityKind =
  | 'task' | 'decision' | 'risk' | 'milestone'
  | 'phase' | 'stage' | 'blocker' | 'todo' | 'doc' | 'event'

/** The stable reference stored on a card element's customData. */
export interface EntityCardRef {
  kind: EntityKind
  id: string
}

/** A normalized, kind-agnostic view of an entity for rendering a card. */
export interface EntityRef extends EntityCardRef {
  title: string
  status: string
  meta?: string // task priority / risk severity
  detail?: string // description / decision text, for the details peek
}

export const CARD_KINDS: EntityKind[] = [
  'task', 'decision', 'risk', 'blocker', 'milestone',
  'phase', 'stage', 'todo', 'doc', 'event',
]

export const KIND_NAME: Record<EntityKind, string> = {
  task: 'Task',
  decision: 'Decision',
  risk: 'Risk',
  milestone: 'Milestone',
  phase: 'Phase',
  stage: 'Stage',
  blocker: 'Blocker',
  todo: 'Todo',
  doc: 'Doc',
  event: 'Event',
}

export const KIND_ICON: Record<EntityKind, string> = {
  task: '✔',
  decision: '◆',
  risk: '▲',
  milestone: '◇',
  phase: '▤',
  stage: '▥',
  blocker: '⊘',
  todo: '☑',
  doc: '▣',
  event: '◷',
}

// Light fill + darker stroke per kind (theme-neutral hex; Excalidraw needs hex).
export const CARD_STYLE: Record<EntityKind, { bg: string; stroke: string }> = {
  task: { bg: '#e8f0fe', stroke: '#3b6fb0' },
  decision: { bg: '#e9f6ec', stroke: '#3f8a4f' },
  risk: { bg: '#fdeceb', stroke: '#c0483f' },
  milestone: { bg: '#fff3e0', stroke: '#c07f2a' },
  phase: { bg: '#ede9fe', stroke: '#6d4aad' },
  stage: { bg: '#eef2ff', stroke: '#5b6ad0' },
  blocker: { bg: '#ffe3e3', stroke: '#a51111' },
  todo: { bg: '#e6fcf5', stroke: '#0b7285' },
  doc: { bg: '#f1f3f5', stroke: '#495057' },
  event: { bg: '#e3fafc', stroke: '#1098ad' },
}

export function taskToRef(t: Task): EntityRef {
  return { kind: 'task', id: t.id, title: t.title, status: t.status, meta: t.priority ?? undefined, detail: t.description ?? undefined }
}
export function decisionToRef(d: Decision): EntityRef {
  return { kind: 'decision', id: d.id, title: d.title, status: d.status, detail: d.decision || undefined }
}
export function riskToRef(r: Risk): EntityRef {
  return { kind: 'risk', id: r.id, title: r.title, status: r.status, meta: r.severity, detail: r.description ?? r.mitigation ?? undefined }
}
export function milestoneToRef(m: Milestone): EntityRef {
  return { kind: 'milestone', id: m.id, title: m.title, status: m.status, detail: m.description ?? m.target_date ?? undefined }
}
export function phaseToRef(p: Phase): EntityRef {
  return { kind: 'phase', id: p.id, title: p.title, status: p.status, detail: p.description ?? undefined }
}
export function stageToRef(s: Stage): EntityRef {
  return { kind: 'stage', id: s.id, title: s.title, status: s.status, detail: s.description ?? undefined }
}
export function blockerToRef(b: Blocker): EntityRef {
  return { kind: 'blocker', id: b.id, title: b.title, status: b.status, detail: b.description ?? undefined }
}
export function todoToRef(t: Todo): EntityRef {
  return { kind: 'todo', id: t.id, title: t.label, status: t.done ? 'done' : 'open' }
}
export function docToRef(d: DocSummary): EntityRef {
  // ponytail: no detail — DocSummary carries no body preview on this base.
  return { kind: 'doc', id: d.id, title: d.title, status: d.status, meta: d.doc_type }
}
export function eventToRef(e: CalendarEvent): EntityRef {
  return { kind: 'event', id: e.id, title: e.title, status: e.status, meta: e.start_at.slice(0, 10), detail: e.description ?? e.location ?? undefined }
}

/** Case-insensitive AND-of-tokens match over kind name, title, status and meta. */
export function filterEntities(entities: EntityRef[], query: string): EntityRef[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!tokens.length) return entities
  return entities.filter((e) => {
    const hay = `${KIND_NAME[e.kind]} ${e.title} ${e.status} ${e.meta ?? ''}`.toLowerCase()
    return tokens.every((t) => hay.includes(t))
  })
}

/** The baked, human-readable text drawn on a card element. */
export function cardLabel(ref: EntityRef): string {
  const sub = ref.meta ? `${ref.status} · ${ref.meta}` : ref.status
  return `${KIND_ICON[ref.kind]} ${KIND_NAME[ref.kind]}\n${ref.title}\n${sub}`
}

/** Read a card ref off an element's customData, or null if it isn't a card. */
export function readCardRef(customData: unknown): EntityCardRef | null {
  const c = customData as { approvoEntity?: { kind?: string; id?: string } } | undefined
  const e = c?.approvoEntity
  if (e && typeof e.id === 'string' && (CARD_KINDS as string[]).includes(e.kind ?? '')) {
    return { kind: e.kind as EntityKind, id: e.id }
  }
  return null
}

/** Read a review-pin's linked comment id off an element's customData, or null.
 * A review pin (Phase 13c) is an ordinary Excalidraw marker element whose
 * customData carries { reviewPin: { commentId } }, tying a canvas spot to a
 * polymorphic Comment on the canvas Doc. */
export function readReviewPin(customData: unknown): string | null {
  const c = customData as { reviewPin?: { commentId?: string } } | undefined
  const id = c?.reviewPin?.commentId
  return typeof id === 'string' && id ? id : null
}
