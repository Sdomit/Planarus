import { describe, expect, it } from 'vitest'
import { buildConnectionTargets } from './connectionTargets'
import type { Decision, DocSummary, Milestone, Phase, Risk, Task } from '../api/client'

// Only the fields buildConnectionTargets reads are meaningful; the rest exist to
// satisfy the API types.
const phase = { id: 'phs_1', title: 'Phase 2', status: 'active' } as Phase
const task = { id: 'tsk_1', title: 'Ship it', status: 'in_progress', phase_id: 'phs_1' } as Task
const orphanTask = { id: 'tsk_2', title: 'Unfiled', status: 'todo', phase_id: null } as Task
const milestone = { id: 'mls_1', title: 'Beta', status: 'open', phase_id: 'phs_1' } as Milestone
const decision = { id: 'dec_1', title: 'Keep it local', status: 'accepted', phase_id: null } as Decision
const risk = { id: 'rsk_1', title: 'Slippage', status: 'open', phase_id: 'phs_1' } as Risk
const doc = { id: 'doc_1', title: 'Architecture', doc_type: 'spec', status: 'draft' } as DocSummary

const build = () => buildConnectionTargets({
  phases: [phase], tasks: [task, orphanTask], milestones: [milestone],
  decisions: [decision], risks: [risk], docs: [doc],
})

describe('buildConnectionTargets', () => {
  it('includes every connectable type', () => {
    expect([...new Set(build().map(t => t.entityType))].sort()).toEqual(
      ['decision', 'doc', 'milestone', 'phase', 'risk', 'task'],
    )
  })

  it('resolves the phase title into meta rather than leaking the phase id', () => {
    const found = build().find(t => t.id === 'tsk_1')
    expect(found?.meta).toBe('Phase 2 · in progress')
    // A raw id in the visible label is the bug plan 25 calls out by name.
    expect(found?.meta).not.toContain('phs_1')
  })

  it('omits the phase segment for an unfiled item instead of rendering a blank one', () => {
    // `null · todo` would read as a missing phase; the separator must go too.
    expect(build().find(t => t.id === 'tsk_2')?.meta).toBe('todo')
  })

  it('humanises only the task status, which is the one shown as prose', () => {
    expect(build().find(t => t.id === 'tsk_1')?.meta).toContain('in progress')
    expect(build().find(t => t.id === 'phs_1')?.meta).toBe('active')
  })

  it('describes a doc by type and status', () => {
    expect(build().find(t => t.id === 'doc_1')?.meta).toBe('spec · draft')
  })

  it('is a pure function of its inputs — no fetch, no ordering surprise', () => {
    expect(build()).toEqual(build())
    // Phases first, docs last: the composer's option list groups by type.
    expect(build()[0].entityType).toBe('phase')
    expect(build()[build().length - 1].entityType).toBe('doc')
  })
})
