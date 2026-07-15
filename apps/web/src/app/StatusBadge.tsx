// Maps Approvo status/priority/severity values to forma badge "tones".
export type ToneKind =
  | 'project' | 'phase' | 'task' | 'priority'
  | 'decision' | 'severity' | 'riskstatus' | 'milestone'
  | 'approval' | 'docstatus' | 'agentrun' | 'emailstatus' | 'notifseverity'

type Tone = 'neutral' | 'info' | 'accent' | 'success' | 'warning' | 'danger' | 'critical'

const TONE: Record<ToneKind, Record<string, Tone>> = {
  project: {
    idea: 'neutral', researching: 'info', planning: 'info', ready: 'accent',
    active: 'success', blocked: 'danger', paused: 'warning', later: 'neutral',
    review: 'warning', done: 'success', archived: 'neutral',
  },
  phase: { planned: 'neutral', active: 'info', blocked: 'danger', done: 'success', canceled: 'neutral' },
  task: {
    backlog: 'neutral', ready: 'info', in_progress: 'accent', waiting: 'warning',
    needs_review: 'warning', blocked: 'danger', done: 'success', canceled: 'neutral',
  },
  priority: { low: 'neutral', med: 'info', medium: 'info', high: 'warning', urgent: 'danger' },
  decision: { proposed: 'info', accepted: 'success', superseded: 'neutral', reversed: 'danger' },
  severity: { low: 'neutral', medium: 'warning', high: 'danger', critical: 'critical' },
  riskstatus: { open: 'danger', monitoring: 'warning', mitigated: 'success', accepted: 'info', closed: 'neutral' },
  milestone: { planned: 'neutral', active: 'info', achieved: 'success', missed: 'danger', canceled: 'neutral' },
  approval: {
    pending: 'warning', approved: 'info', applying: 'info', applied: 'success',
    rejected: 'danger', invalidated: 'neutral', expired: 'neutral', failed: 'danger',
  },
  docstatus: { draft: 'neutral', published: 'success' },
  agentrun: { started: 'info', succeeded: 'success', failed: 'danger', canceled: 'neutral' },
  emailstatus: { sent: 'success', failed: 'danger', skipped: 'warning' },
  notifseverity: { action: 'danger', warn: 'warning', info: 'neutral' },
}

export function toneFor(kind: ToneKind, value: string | null | undefined): Tone {
  if (!value) return 'neutral'
  return TONE[kind]?.[value] ?? 'neutral'
}

/** A forma status pill: colored dot + label. */
export function StatusBadge({
  kind,
  value,
  className = '',
}: {
  kind: ToneKind
  value: string | null | undefined
  className?: string
}) {
  if (!value) return null
  const tone = toneFor(kind, value)
  return (
    <span className={`sbadge sbadge--${tone} ${className}`.trim()}>
      <span className="sdot" />
      {value.replace(/_/g, ' ')}
    </span>
  )
}
