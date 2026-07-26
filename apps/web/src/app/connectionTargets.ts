import type { Decision, Doc, DocSummary, Milestone, Phase, Risk, Task } from '../api/client'
import type { ConnectionTarget } from './EntityConnections'

/** The project-scoped collections a connection target list is built from. */
export interface ConnectionTargetSources {
  phases: Phase[]
  tasks: Task[]
  milestones: Milestone[]
  decisions: Decision[]
  risks: Risk[]
  docs: DocSummary[]
}

/**
 * One doc's target entry, exactly as `buildConnectionTargets` would produce it.
 *
 * Exported so a panel that already loaded the full graph once (Docs) can merge
 * in a single newly-created or newly-loaded doc locally, instead of re-running
 * all seven list calls to add one row.
 */
export function docToTarget(doc: DocSummary | Doc): ConnectionTarget {
  return { entityType: 'doc', id: doc.id, title: doc.title, meta: [doc.doc_type, doc.status].join(' · ') }
}

/**
 * Build the picker/label list for `ConnectionProvider`.
 *
 * Extracted from `PlanningPanel` when Docs gained its own connection section:
 * two panels now need identical `meta` strings, and a target that reads
 * "Phase 2 · in progress" in Planning but "in_progress" in Docs is the same
 * item wearing two names. The composer's `Type · title · meta` option text and
 * the detail row's context line both come from here, so any drift is visible
 * to a person comparing the two surfaces side by side.
 *
 * Pure and synchronous on purpose — callers pass collections they already hold,
 * which is what keeps opening a detail view free of an extra fetch.
 */
export function buildConnectionTargets({
  phases, tasks, milestones, decisions, risks, docs,
}: ConnectionTargetSources): ConnectionTarget[] {
  const phaseTitleById = new Map(phases.map(phase => [phase.id, phase.title]))
  const phaseAnd = (phaseId: string | null | undefined, ...rest: (string | null | undefined)[]) =>
    [phaseId ? phaseTitleById.get(phaseId) : null, ...rest].filter(Boolean).join(' · ')

  return [
    ...phases.map(phase => ({
      entityType: 'phase' as const, id: phase.id, title: phase.title, meta: phase.status,
    })),
    ...tasks.map(task => ({
      entityType: 'task' as const, id: task.id, title: task.title,
      // Status keys are stored snake_case; only this one is shown as prose.
      meta: phaseAnd(task.phase_id, task.status.replace(/_/g, ' ')),
    })),
    ...milestones.map(milestone => ({
      entityType: 'milestone' as const, id: milestone.id, title: milestone.title,
      meta: phaseAnd(milestone.phase_id, milestone.status),
    })),
    ...decisions.map(decision => ({
      entityType: 'decision' as const, id: decision.id, title: decision.title,
      meta: phaseAnd(decision.phase_id, decision.status),
    })),
    ...risks.map(risk => ({
      entityType: 'risk' as const, id: risk.id, title: risk.title,
      meta: phaseAnd(risk.phase_id, risk.status),
    })),
    ...docs.map(docToTarget),
  ]
}
