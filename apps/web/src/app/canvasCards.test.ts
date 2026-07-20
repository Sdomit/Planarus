import { describe, it, expect } from 'vitest'
import {
  taskToRef,
  decisionToRef,
  riskToRef,
  milestoneToRef,
  todoToRef,
  docToRef,
  eventToRef,
  cardLabel,
  filterEntities,
  readCardRef,
  readReviewPin,
} from './canvasCards'
import type { Task, Decision, Risk, Milestone, Todo, DocSummary, CalendarEvent } from '../api/client'

const task = { id: 't1', title: 'Ship it', status: 'in_progress', priority: 'high', description: 'do the thing' } as Task
const decision = { id: 'd1', title: 'Use SQLite', status: 'accepted', decision: 'because local-first' } as Decision
const risk = { id: 'r1', title: 'Data loss', status: 'open', severity: 'critical', description: null, mitigation: 'backups' } as Risk
const milestone = { id: 'm1', title: 'Beta', status: 'planned', description: null, target_date: '2026-09-01' } as Milestone

describe('canvasCards helpers', () => {
  it('normalizes each entity kind, carrying status + meta', () => {
    expect(taskToRef(task)).toMatchObject({ kind: 'task', id: 't1', status: 'in_progress', meta: 'high' })
    expect(decisionToRef(decision)).toMatchObject({ kind: 'decision', status: 'accepted', detail: 'because local-first' })
    expect(riskToRef(risk)).toMatchObject({ kind: 'risk', status: 'open', meta: 'critical', detail: 'backups' })
    expect(milestoneToRef(milestone)).toMatchObject({ kind: 'milestone', status: 'planned', detail: '2026-09-01' })
  })

  it('bakes kind, title and status (with meta) into the label', () => {
    const label = cardLabel(taskToRef(task))
    expect(label).toBe('✔ Task\nShip it\nin_progress · high')
    // no meta → status only, no trailing separator
    expect(cardLabel(decisionToRef(decision))).toBe('◆ Decision\nUse SQLite\naccepted')
  })

  it('reads a valid card ref and rejects non-card / malformed customData', () => {
    expect(readCardRef({ approvoEntity: { kind: 'task', id: 't1' } })).toEqual({ kind: 'task', id: 't1' })
    expect(readCardRef(undefined)).toBeNull()
    expect(readCardRef({ foo: 1 })).toBeNull()
    expect(readCardRef({ approvoEntity: { kind: 'bogus', id: 'x' } })).toBeNull()
    expect(readCardRef({ approvoEntity: { kind: 'task' } })).toBeNull() // missing id
  })

  it('normalizes the wider entity kinds', () => {
    expect(todoToRef({ id: 'td1', label: 'Buy milk', done: true } as Todo)).toMatchObject({ kind: 'todo', title: 'Buy milk', status: 'done' })
    expect(todoToRef({ id: 'td2', label: 'Later', done: false } as Todo)).toMatchObject({ status: 'open' })
    expect(docToRef({ id: 'dc1', title: 'Spec', status: 'draft', doc_type: 'note' } as DocSummary)).toMatchObject({ kind: 'doc', meta: 'note' })
    expect(eventToRef({ id: 'ev1', title: 'Kickoff', status: 'confirmed', start_at: '2026-08-01T09:00:00Z', description: null, location: 'HQ' } as CalendarEvent))
      .toMatchObject({ kind: 'event', meta: '2026-08-01', detail: 'HQ' })
  })

  it('filters on any of kind, title, status or meta, AND-ing the tokens', () => {
    const all = [taskToRef(task), decisionToRef(decision), riskToRef(risk), milestoneToRef(milestone)]
    expect(filterEntities(all, '')).toHaveLength(4) // empty query keeps everything
    expect(filterEntities(all, 'ship').map((e) => e.id)).toEqual(['t1'])
    expect(filterEntities(all, 'RISK').map((e) => e.id)).toEqual(['r1']) // kind name, case-insensitive
    expect(filterEntities(all, 'critical').map((e) => e.id)).toEqual(['r1']) // meta
    expect(filterEntities(all, 'accepted').map((e) => e.id)).toEqual(['d1']) // status
    expect(filterEntities(all, 'task high').map((e) => e.id)).toEqual(['t1']) // both tokens must hit
    expect(filterEntities(all, 'task critical')).toEqual([]) // tokens AND, not OR
  })

  it('reads a review-pin comment id and rejects non-pins', () => {
    expect(readReviewPin({ reviewPin: { commentId: 'cmt_1' } })).toBe('cmt_1')
    expect(readReviewPin({ approvoEntity: { kind: 'task', id: 't1' } })).toBeNull()
    expect(readReviewPin({ reviewPin: {} })).toBeNull()
    expect(readReviewPin(undefined)).toBeNull()
  })
})
