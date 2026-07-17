import { describe, it, expect } from 'vitest'
import {
  taskToRef,
  decisionToRef,
  riskToRef,
  milestoneToRef,
  cardLabel,
  readCardRef,
} from './canvasCards'
import type { Task, Decision, Risk, Milestone } from '../api/client'

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
})
