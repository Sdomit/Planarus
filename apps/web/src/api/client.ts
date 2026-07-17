const BASE = '/api/v1'

export interface Workspace {
  id: string
  name: string
  slug: string
  description: string | null
  default_project_root: string | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  workspace_id: string
  title: string
  slug: string
  summary: string | null
  project_type: string | null
  status: string
  priority: string | null
  folder_path: string | null
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface ContextFile {
  id: string
  project_id: string
  kind: string
  relative_path: string
  checksum: string
  generated_at: string
  pinned: boolean
  last_manual_edit_at: string | null
  token_estimate: number | null
  created_at: string
  updated_at: string
}

export interface RegenOutcome {
  relative_path: string
  kind: string
  status: string
  pinned: boolean
  drifted: boolean
}

export interface RegenReport {
  project_id: string
  generated_at: string
  written: number
  drifted: number
  outcomes: RegenOutcome[]
}

export interface Phase {
  id: string
  project_id: string
  title: string
  description: string | null
  status: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Stage {
  id: string
  phase_id: string
  project_id: string
  title: string
  description: string | null
  status: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  project_id: string
  phase_id: string | null
  stage_id: string | null
  parent_task_id: string | null
  title: string
  description: string | null
  status: string
  priority: string | null
  due_at: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Decision {
  id: string
  project_id: string
  title: string
  decision: string
  context: string | null
  status: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Risk {
  id: string
  project_id: string
  title: string
  description: string | null
  severity: string
  status: string
  mitigation: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Blocker {
  id: string
  project_id: string
  task_id: string | null
  title: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Milestone {
  id: string
  project_id: string
  phase_id: string | null
  title: string
  description: string | null
  status: string
  target_date: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface CalendarEvent {
  id: string
  project_id: string
  phase_id: string | null
  title: string
  description: string | null
  location: string | null
  status: string
  start_at: string
  end_at: string | null
  all_day: boolean
  recurrence: string
  recurrence_until: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

/** A normalized entry in the aggregated calendar feed. */
export interface CalendarItem {
  id: string
  source: 'event' | 'milestone' | 'task'
  ref_id: string
  title: string
  start_at: string
  end_at: string | null
  all_day: boolean
  status: string | null
  phase_id: string | null
  recurring: boolean
}

export interface ProjectCalendar {
  project_id: string
  generated_at: string
  items: CalendarItem[]
}

/** An external calendar link (Google/Microsoft). Never carries tokens. */
export interface CalendarConnection {
  id: string
  project_id: string
  provider: string
  account_email: string
  status: string
  last_synced_at: string | null
  created_at: string
}

export interface SyncResult {
  connection_id: string
  pushed: number
  pulled: number
  status: string
}

export interface ChecklistItem {
  id: string
  task_id: string
  label: string
  done: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Comment {
  id: string
  project_id: string
  entity_type: string
  entity_id: string
  body: string
  author_type: string
  status: string
  created_at: string
  updated_at: string | null
}

export interface Link {
  id: string
  project_id: string
  entity_type: string
  entity_id: string
  url: string
  title: string | null
  created_at: string
}

export interface DocSummary {
  id: string
  project_id: string
  parent_doc_id: string | null
  title: string
  slug: string
  doc_type: string
  editor_format: string
  status: string
  sort_order: number
  version: number
  updated_at: string
  archived_at: string | null
}

export interface Doc extends DocSummary {
  editor_format: string
  content_json: string
  markdown_cache: string
  export_relative_path: string | null
  export_checksum: string | null
  exported_at: string | null
  created_at: string
}

export interface DocCreate {
  title: string
  doc_type: string
  editor_format?: string
  status?: string
  sort_order?: number
  parent_doc_id?: string | null
  slug?: string | null
}

export interface DocUpdate {
  version: number
  title?: string | null
  doc_type?: string | null
  status?: string | null
  sort_order?: number | null
  parent_doc_id?: string | null
  content_json?: string | null
  markdown_cache?: string | null
  archived_at?: string | null
}

export interface DocExportResponse {
  export_path: string
  was_changed: boolean
  drift_detected: boolean
  checksum: string
}

// --- Read-only Git metadata (Phase 8) --------------------------------------

export interface GitRepoLink {
  project_id: string
  repo_path: string | null
  is_repo: boolean
  current_branch: string | null
  detached: boolean
  last_commit_sha: string | null
  last_commit_subject: string | null
  is_dirty: boolean
  dirty_count: number
  remote_url: string | null
  message: string | null
  checked_at: string
}

export interface WorkspaceCreate {
  name: string
  slug: string
  description?: string
}

export interface ProjectCreate {
  workspace_id: string
  title: string
  slug: string
  summary?: string
  status?: string
}

// --- Context Pack Builder (Phase 6A) ---------------------------------------

export interface ContextPackProfile {
  key: string
  version: number
  label: string
  description: string
  default_target: string
  include_git_checklist: boolean
}

export interface ContextPackProfilesResponse {
  target_tools: string[]
  budget_presets: Record<string, number>
  default_budget_preset: string
  profiles: ContextPackProfile[]
}

export interface StructuredSourceItem {
  source_id: string
  label: string
  kind: string
  default_included: boolean
  optional: boolean
  token_estimate: number
}

export interface DocumentSourceItem {
  source_id: string
  doc_id: string
  title: string
  doc_type: string
  status: string
  token_estimate: number
}

export interface GovernanceSourceItem {
  source_id: string
  relative_path: string
  available: boolean
  status: string
  token_estimate: number
}

export interface ContextPackSources {
  project_id: string
  has_folder: boolean
  structured: StructuredSourceItem[]
  documents: DocumentSourceItem[]
  governance: GovernanceSourceItem[]
  warnings: string[]
}

export interface ContextPackSelection {
  document_ids?: string[]
  document_order?: string[]
  pinned_source_ids?: string[]
  excluded_source_ids?: string[]
  include_done_tasks?: boolean
  include_closed_risks?: boolean
  include_resolved_blockers?: boolean
  include_all_decisions?: boolean
  include_audit_slice?: boolean
}

export interface ContextPackPreviewRequest {
  profile: string
  target_tool: string
  budget_preset: string
  objective: string
  selection: ContextPackSelection
}

export interface ManifestEntry {
  source_id: string
  label: string
  kind: string
  included: boolean
  truncated: boolean
  pinned: boolean
  flagged: boolean
  token_estimate: number
  version: string
  note: string | null
}

export interface TruncationEntry {
  source_id: string
  reason: string
}

export interface SecretFinding {
  pattern_label: string
  masked_preview: string
  source_ref: string
  count: number
}

export interface ContextPackPreview {
  markdown: string
  pack_checksum: string
  token_estimate: number
  budget_preset: string
  budget_limit: number
  over_budget: boolean
  profile: { key: string; version: number; label: string; include_git_checklist: boolean }
  target_tool: string
  manifest: ManifestEntry[]
  warnings: string[]
  truncations: TruncationEntry[]
  secret_findings: SecretFinding[]
}

// --- Approval Queue (Phase 7A) ---------------------------------------------

export interface ApprovalSummary {
  id: string
  workspace_id: string
  project_id: string
  origin: string
  actor_ref: string | null
  action_type: string
  target_entity_type: string | null
  target_entity_id: string | null
  risk_level: string
  status: string
  policy_version: number
  created_at: string
  expires_at: string
  decided_at: string | null
  decided_by: string | null
  applied_at: string | null
  reason: string | null
  failure_reason: string | null
}

export interface DiffEntry {
  field: string
  before: unknown
  after: unknown
}

export interface ApprovalDetail extends ApprovalSummary {
  patch_checksum: string
  diff: DiffEntry[]
  is_expired: boolean
  stale_reason: string | null
  secret_warning: boolean
}

export interface ApprovalAuditEntry {
  id: string
  event_type: string
  actor_type: string
  created_at: string
}

// --- External API clients (Phase 7C1) --------------------------------------

export interface ApiClientSummary {
  id: string
  workspace_id: string
  key_id: string
  label: string
  can_read: boolean
  can_propose: boolean
  project_ids: string[]
  enabled: boolean
  created_at: string
  expires_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface ApiClientCreatePayload {
  label: string
  workspace_id: string
  project_ids: string[]
  can_read: boolean
  can_propose: boolean
  expires_in_days?: number
}

export interface ApiClientCreatedResponse {
  client: ApiClientSummary
  // The raw key — returned exactly once, never stored.
  api_key: string
  warning: string
}

// --- Phase 9: roadmap / timeline / agent runs / notifications ----------------

export interface RoadmapTaskRollup {
  total: number
  done: number
  in_progress: number
  blocked: number
}

export interface RoadmapStage {
  id: string
  title: string
  status: string
  sort_order: number
  tasks: RoadmapTaskRollup
  pct_done: number
}

export interface RoadmapPhase {
  id: string
  title: string
  status: string
  sort_order: number
  stages: RoadmapStage[]
  tasks: RoadmapTaskRollup
  pct_done: number
}

export interface ProjectRoadmap {
  project_id: string
  generated_at: string
  phases: RoadmapPhase[]
  unphased: RoadmapTaskRollup
  totals: RoadmapTaskRollup
  pct_done: number
}

export interface TimelineEvent {
  id: string
  at: string
  event_type: string
  entity_type: string
  entity_id: string | null
  actor_type: string
  label: string
}

export interface ProjectTimeline {
  project_id: string
  generated_at: string
  events: TimelineEvent[]
}

export interface AgentRun {
  id: string
  project_id: string
  agent_family: string
  agent_name: string | null
  mode: string | null
  status: string
  summary: string | null
  started_at: string
  ended_at: string | null
  created_at: string
  updated_at: string
}

export interface AgentRunAnalytics {
  project_id: string
  generated_at: string
  total: number
  by_family: Record<string, number>
  by_status: Record<string, number>
  by_mode: Record<string, number>
  success_rate: number | null
  avg_duration_minutes: number | null
  last_run_at: string | null
}

export interface NotificationItem {
  id: string
  kind: string
  severity: string
  title: string
  detail: string | null
  project_id: string
  project_title: string
  at: string
}

export interface NotificationFeed {
  generated_at: string
  items: NotificationItem[]
}

export interface NotificationRule {
  id: string
  project_id: string
  channel: string
  trigger_type: string
  enabled: boolean
  to_email: string
  threshold_hours: number
  created_at: string
  updated_at: string
}

export interface EmailLogEntry {
  id: string
  project_id: string
  rule_id: string | null
  to_email: string
  subject: string
  status: string
  error: string | null
  sent_at: string
  created_at: string
}

export interface ReminderOutcome {
  rule_id: string
  status: string
  reason: string | null
  email_log_id: string | null
}

export interface ReminderSendResult {
  project_id: string
  sent: number
  skipped: number
  failed: number
  outcomes: ReminderOutcome[]
}

// --- Runtime settings (Phase 9B) --------------------------------------------

export interface AppSettings {
  // switch tier (editable)
  email_enabled: boolean
  email_from: string
  external_api_active: boolean
  // ceiling tier (env-owned, read-only status)
  external_api_permitted_by_env: boolean
  external_api_hosts_configured: boolean
  email_smtp_loopback: boolean
}

export interface AppSettingsUpdate {
  email_enabled?: boolean
  email_from?: string
  external_api_active?: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // init is spread FIRST so the headers merge below always wins — a caller-supplied
  // headers object (e.g. controlRequest's token) must add to, not replace, the
  // Content-Type. The old order dropped Content-Type on every body-carrying
  // control call and FastAPI 422'd the raw text/plain body.
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// Local control token (Phase 7A): fetched once from the loopback API and attached
// to every state-changing approval call. Held in memory only — never persisted.
let _localToken: string | null = null

export function _resetLocalTokenForTests(): void {
  _localToken = null
}

async function getLocalToken(): Promise<string> {
  if (_localToken) return _localToken
  const res = await fetch(`${BASE}/local-session`)
  if (!res.ok) throw new Error(`local session unavailable (${res.status})`)
  const data = (await res.json()) as { token: string }
  _localToken = data.token
  return _localToken
}

async function controlRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getLocalToken()
  return request<T>(path, {
    ...init,
    headers: { ...init?.headers, 'X-Approvo-Local-Token': token },
  })
}

export const api = {
  workspaces: {
    list: () => request<Workspace[]>('/workspaces'),
    create: (data: WorkspaceCreate) =>
      request<Workspace>('/workspaces', { method: 'POST', body: JSON.stringify(data) }),
  },
  projects: {
    list: (workspaceId?: string, includeArchived = false) => {
      const q = new URLSearchParams()
      if (workspaceId) q.set('workspace_id', workspaceId)
      if (includeArchived) q.set('include_archived', 'true')
      const qs = q.toString()
      return request<Project[]>(`/projects${qs ? `?${qs}` : ''}`)
    },
    create: (data: ProjectCreate) =>
      request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
    get: (id: string) => request<Project>(`/projects/${id}`),
    update: (id: string, data: Partial<Pick<Project, 'title' | 'summary' | 'status'>>) =>
      request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    archive: (id: string) => request<Project>(`/projects/${id}/archive`, { method: 'POST' }),
    unarchive: (id: string) => request<Project>(`/projects/${id}/unarchive`, { method: 'POST' }),
    duplicate: (id: string) => request<Project>(`/projects/${id}/duplicate`, { method: 'POST' }),
    remove: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  },
  phases: {
    list: (projectId: string) => request<Phase[]>(`/projects/${projectId}/phases`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<Phase>(`/projects/${projectId}/phases`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Phase, 'title' | 'description' | 'status'>>) =>
      request<Phase>(`/phases/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/phases/${id}`, { method: 'DELETE' }),
    reorder: (projectId: string, ids: string[]) =>
      request<Phase[]>(`/projects/${projectId}/phases/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  },
  stages: {
    list: (projectId: string) => request<Stage[]>(`/projects/${projectId}/stages`),
    create: (projectId: string, data: { title: string; phase_id: string; status?: string }) =>
      request<Stage>(`/projects/${projectId}/stages`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Stage, 'title' | 'status'>>) =>
      request<Stage>(`/stages/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  tasks: {
    list: (projectId: string) => request<Task[]>(`/projects/${projectId}/tasks`),
    create: (
      projectId: string,
      data: {
        title: string
        status?: string
        priority?: string
        phase_id?: string
        stage_id?: string
        parent_task_id?: string
      },
    ) =>
      request<Task>(`/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(data) }),
    update: (
      id: string,
      data: Partial<Pick<Task, 'title' | 'description' | 'status' | 'priority' | 'phase_id' | 'stage_id' | 'due_at' | 'parent_task_id'>>,
    ) =>
      request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
    reorder: (projectId: string, ids: string[]) =>
      request<Task[]>(`/projects/${projectId}/tasks/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  },
  decisions: {
    list: (projectId: string) => request<Decision[]>(`/projects/${projectId}/decisions`),
    create: (projectId: string, data: { title: string; decision: string; status?: string }) =>
      request<Decision>(`/projects/${projectId}/decisions`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Pick<Decision, 'title' | 'decision' | 'context' | 'status'>>) =>
      request<Decision>(`/decisions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/decisions/${id}`, { method: 'DELETE' }),
    reorder: (projectId: string, ids: string[]) =>
      request<Decision[]>(`/projects/${projectId}/decisions/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  },
  risks: {
    list: (projectId: string) => request<Risk[]>(`/projects/${projectId}/risks`),
    create: (projectId: string, data: { title: string; severity: string; status?: string }) =>
      request<Risk>(`/projects/${projectId}/risks`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Risk, 'title' | 'description' | 'severity' | 'status' | 'mitigation'>>) =>
      request<Risk>(`/risks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/risks/${id}`, { method: 'DELETE' }),
    reorder: (projectId: string, ids: string[]) =>
      request<Risk[]>(`/projects/${projectId}/risks/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  },
  blockers: {
    list: (projectId: string) => request<Blocker[]>(`/projects/${projectId}/blockers`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<Blocker>(`/projects/${projectId}/blockers`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Pick<Blocker, 'title' | 'description' | 'status' | 'task_id'>>) =>
      request<Blocker>(`/blockers/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/blockers/${id}`, { method: 'DELETE' }),
  },
  milestones: {
    list: (projectId: string) => request<Milestone[]>(`/projects/${projectId}/milestones`),
    create: (projectId: string, data: { title: string; status?: string; target_date?: string; phase_id?: string }) =>
      request<Milestone>(`/projects/${projectId}/milestones`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Milestone, 'title' | 'description' | 'status' | 'target_date' | 'phase_id'>>) =>
      request<Milestone>(`/milestones/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/milestones/${id}`, { method: 'DELETE' }),
    reorder: (projectId: string, ids: string[]) =>
      request<Milestone[]>(`/projects/${projectId}/milestones/reorder`, { method: 'POST', body: JSON.stringify({ ids }) }),
  },
  calendarEvents: {
    list: (projectId: string) => request<CalendarEvent[]>(`/projects/${projectId}/calendar-events`),
    create: (
      projectId: string,
      data: {
        title: string
        start_at: string
        end_at?: string | null
        all_day?: boolean
        status?: string
        description?: string
        location?: string
        phase_id?: string
        recurrence?: string
        recurrence_until?: string | null
      },
    ) =>
      request<CalendarEvent>(`/projects/${projectId}/calendar-events`, { method: 'POST', body: JSON.stringify(data) }),
    update: (
      id: string,
      data: Partial<Pick<CalendarEvent, 'title' | 'start_at' | 'end_at' | 'all_day' | 'status' | 'description' | 'location' | 'phase_id' | 'recurrence' | 'recurrence_until'>>,
    ) =>
      request<CalendarEvent>(`/calendar-events/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) =>
      request<void>(`/calendar-events/${id}`, { method: 'DELETE' }),
  },
  calendar: {
    get: (projectId: string, params?: { from?: string; to?: string }) => {
      const q = new URLSearchParams()
      if (params?.from) q.set('from', params.from)
      if (params?.to) q.set('to', params.to)
      const qs = q.toString()
      return request<ProjectCalendar>(`/projects/${projectId}/calendar${qs ? `?${qs}` : ''}`)
    },
    /** Direct download URL for the .ics export (goes through the /api proxy). */
    icsHref: (projectId: string, params?: { from?: string; to?: string }) => {
      const q = new URLSearchParams()
      if (params?.from) q.set('from', params.from)
      if (params?.to) q.set('to', params.to)
      const qs = q.toString()
      return `${BASE}/projects/${projectId}/calendar.ics${qs ? `?${qs}` : ''}`
    },
  },
  calendarSync: {
    providers: () => request<{ providers: string[] }>(`/calendar-sync/providers`),
    connections: (projectId: string) =>
      request<CalendarConnection[]>(`/projects/${projectId}/calendar-connections`),
    connect: (provider: string, projectId: string, redirectUri: string) =>
      request<{ authorize_url: string }>(
        `/calendar-sync/${provider}/connect?project_id=${encodeURIComponent(projectId)}&redirect_uri=${encodeURIComponent(redirectUri)}`,
      ),
    disconnect: (id: string) => request<void>(`/calendar-connections/${id}`, { method: 'DELETE' }),
    sync: (id: string) => request<SyncResult>(`/calendar-connections/${id}/sync`, { method: 'POST' }),
    /** The OAuth callback URL to register with the provider (same-origin, proxied). */
    callbackUrl: (provider: string) => `${window.location.origin}${BASE}/calendar-sync/${provider}/callback`,
  },
  checklistItems: {
    list: (taskId: string) => request<ChecklistItem[]>(`/tasks/${taskId}/checklist-items`),
    create: (taskId: string, data: { label: string; done?: boolean }) =>
      request<ChecklistItem>(`/tasks/${taskId}/checklist-items`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<ChecklistItem, 'label' | 'done'>>) =>
      request<ChecklistItem>(`/checklist-items/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  comments: {
    list: (projectId: string, params?: { entity_type?: string; entity_id?: string }) => {
      const q = new URLSearchParams()
      if (params?.entity_type) q.set('entity_type', params.entity_type)
      if (params?.entity_id) q.set('entity_id', params.entity_id)
      const qs = q.toString()
      return request<Comment[]>(`/projects/${projectId}/comments${qs ? `?${qs}` : ''}`)
    },
    create: (projectId: string, data: { entity_type: string; entity_id: string; body: string }) =>
      request<Comment>(`/projects/${projectId}/comments`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Comment, 'body' | 'status'>>) =>
      request<Comment>(`/comments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    remove: (id: string) => request<void>(`/comments/${id}`, { method: 'DELETE' }),
  },
  links: {
    list: (projectId: string, params?: { entity_type?: string; entity_id?: string }) => {
      const q = new URLSearchParams()
      if (params?.entity_type) q.set('entity_type', params.entity_type)
      if (params?.entity_id) q.set('entity_id', params.entity_id)
      const qs = q.toString()
      return request<Link[]>(`/projects/${projectId}/links${qs ? `?${qs}` : ''}`)
    },
    create: (projectId: string, data: { entity_type: string; entity_id: string; url: string; title?: string }) =>
      request<Link>(`/projects/${projectId}/links`, { method: 'POST', body: JSON.stringify(data) }),
  },
  docs: {
    list: (projectId: string, params?: { doc_type?: string; status?: string; include_archived?: boolean }) => {
      const q = new URLSearchParams()
      if (params?.doc_type) q.set('doc_type', params.doc_type)
      if (params?.status) q.set('status', params.status)
      if (params?.include_archived) q.set('include_archived', 'true')
      const qs = q.toString()
      return request<DocSummary[]>(`/projects/${projectId}/docs${qs ? `?${qs}` : ''}`)
    },
    get: (id: string) => request<Doc>(`/docs/${id}`),
    create: (projectId: string, data: DocCreate) =>
      request<Doc>(`/projects/${projectId}/docs`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: DocUpdate) =>
      request<Doc>(`/docs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    exportMarkdown: (id: string) =>
      request<DocExportResponse>(`/docs/${id}/export-markdown`, { method: 'POST' }),
  },
  contextFiles: {
    list: (projectId: string) =>
      request<ContextFile[]>(`/context-files?project_id=${projectId}`),
    regenerate: (projectId: string) =>
      request<RegenReport>(`/projects/${projectId}/context/regenerate`, { method: 'POST' }),
    setPinned: (id: string, pinned: boolean) =>
      request<ContextFile>(`/context-files/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ pinned }),
      }),
    content: (id: string) =>
      request<{ relative_path: string; content: string | null; drifted: boolean }>(
        `/context-files/${id}/content`,
      ),
    diff: (id: string) =>
      request<{ relative_path: string; diff: string }>(`/context-files/${id}/diff`),
  },
  git: {
    get: (projectId: string) => request<GitRepoLink>(`/projects/${projectId}/git`),
  },
  contextPack: {
    profiles: () => request<ContextPackProfilesResponse>('/context-pack/profiles'),
    sources: (projectId: string) =>
      request<ContextPackSources>(`/projects/${projectId}/context-pack/sources`),
    preview: (projectId: string, body: ContextPackPreviewRequest) =>
      request<ContextPackPreview>(`/projects/${projectId}/context-pack/preview`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },
  approvals: {
    localSession: () => request<{ token: string }>('/local-session'),
    list: (projectId?: string, status?: string) => {
      const q = new URLSearchParams()
      if (projectId) q.set('project_id', projectId)
      if (status) q.set('status', status)
      const qs = q.toString()
      return request<ApprovalSummary[]>(`/approvals${qs ? `?${qs}` : ''}`)
    },
    get: (id: string) => request<ApprovalDetail>(`/approvals/${id}`),
    audit: (id: string) => request<ApprovalAuditEntry[]>(`/approvals/${id}/audit`),
    approve: (id: string) =>
      controlRequest<ApprovalSummary>(`/approvals/${id}/approve`, { method: 'POST' }),
    reject: (id: string, reason?: string) =>
      controlRequest<ApprovalSummary>(`/approvals/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason ?? null }),
      }),
    apply: (id: string) =>
      controlRequest<ApprovalSummary>(`/approvals/${id}/apply`, { method: 'POST' }),
    invalidate: (id: string) =>
      controlRequest<ApprovalSummary>(`/approvals/${id}/invalidate`, { method: 'POST' }),
  },
  // External API client (machine key) management — local-human only. Every call
  // is local-control-gated, so all three go through controlRequest. The raw key is
  // returned only by create() and is never persisted by the client.
  apiClients: {
    list: (workspaceId?: string) =>
      controlRequest<ApiClientSummary[]>(
        `/api-clients${workspaceId ? `?workspace_id=${workspaceId}` : ''}`,
      ),
    create: (data: ApiClientCreatePayload) =>
      controlRequest<ApiClientCreatedResponse>('/api-clients', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    revoke: (id: string) =>
      controlRequest<ApiClientSummary>(`/api-clients/${id}/revoke`, { method: 'POST' }),
  },
  // --- Phase 9 ----------------------------------------------------------------
  roadmap: {
    get: (projectId: string) => request<ProjectRoadmap>(`/projects/${projectId}/roadmap`),
  },
  timeline: {
    get: (projectId: string, limit = 100) =>
      request<ProjectTimeline>(`/projects/${projectId}/timeline?limit=${limit}`),
  },
  agentRuns: {
    list: (projectId: string) => request<AgentRun[]>(`/projects/${projectId}/agent-runs`),
    create: (
      projectId: string,
      data: Partial<Pick<AgentRun, 'agent_family' | 'agent_name' | 'mode' | 'status' | 'summary'>>,
    ) =>
      request<AgentRun>(`/projects/${projectId}/agent-runs`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (
      id: string,
      data: Partial<Pick<AgentRun, 'agent_family' | 'agent_name' | 'mode' | 'status' | 'summary' | 'ended_at'>>,
    ) => request<AgentRun>(`/agent-runs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    analytics: (projectId: string) =>
      request<AgentRunAnalytics>(`/projects/${projectId}/agent-runs/analytics`),
  },
  notifications: {
    feed: (projectId?: string | null) =>
      request<NotificationFeed>(
        `/notifications${projectId ? `?project_id=${projectId}` : ''}`,
      ),
  },
  notificationRules: {
    list: (projectId: string) =>
      request<NotificationRule[]>(`/projects/${projectId}/notification-rules`),
    // Rule writes configure where outbound email goes → local-control-gated.
    create: (
      projectId: string,
      data: { to_email: string; trigger_type?: string; threshold_hours?: number; enabled?: boolean },
    ) =>
      controlRequest<NotificationRule>(`/projects/${projectId}/notification-rules`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (
      id: string,
      data: Partial<Pick<NotificationRule, 'trigger_type' | 'enabled' | 'to_email' | 'threshold_hours'>>,
    ) =>
      controlRequest<NotificationRule>(`/notification-rules/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
  },
  reminders: {
    // Sending has a side effect outside the app (SMTP) → local-control-gated.
    send: (projectId: string) =>
      controlRequest<ReminderSendResult>(`/projects/${projectId}/reminders/send`, {
        method: 'POST',
      }),
    emailLog: (projectId: string, limit = 50) =>
      request<EmailLogEntry[]>(`/projects/${projectId}/email-log?limit=${limit}`),
  },
  // Runtime settings (Phase 9B). GET is a plain local read; PUT changes a
  // connection's effective state → local-control-gated.
  settings: {
    get: () => request<AppSettings>('/settings'),
    update: (data: AppSettingsUpdate) =>
      controlRequest<AppSettings>('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  },
}
