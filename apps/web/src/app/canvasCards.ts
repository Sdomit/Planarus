// Pure card-model helpers for Phase 13 entity-binding canvas cards.
// No Excalidraw import here on purpose: this module stays jsdom-safe so its
// logic can be unit-tested (CanvasEditor.tsx itself can't be imported in tests
// because Excalidraw crashes jsdom at import time).
import type { Task, Decision, Risk, Milestone } from '../api/client'

export type EntityKind = 'task' | 'decision' | 'risk' | 'milestone'

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

export const CARD_KINDS: EntityKind[] = ['task', 'decision', 'risk', 'milestone']

export const KIND_NAME: Record<EntityKind, string> = {
  task: 'Task',
  decision: 'Decision',
  risk: 'Risk',
  milestone: 'Milestone',
}

const KIND_ICON: Record<EntityKind, string> = {
  task: '✔',
  decision: '◆',
  risk: '▲',
  milestone: '◇',
}

// Light fill + darker stroke per kind (theme-neutral hex; Excalidraw needs hex).
export const CARD_STYLE: Record<EntityKind, { bg: string; stroke: string }> = {
  task: { bg: '#e8f0fe', stroke: '#3b6fb0' },
  decision: { bg: '#e9f6ec', stroke: '#3f8a4f' },
  risk: { bg: '#fdeceb', stroke: '#c0483f' },
  milestone: { bg: '#fff3e0', stroke: '#c07f2a' },
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
