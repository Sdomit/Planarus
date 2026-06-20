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

export interface DocSummary {
  id: string
  project_id: string
  parent_doc_id: string | null
  title: string
  slug: string
  doc_type: string
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
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
    headers: { ...init?.headers, 'X-AgentBoard-Local-Token': token },
  })
}

export const api = {
  workspaces: {
    list: () => request<Workspace[]>('/workspaces'),
    create: (data: WorkspaceCreate) =>
      request<Workspace>('/workspaces', { method: 'POST', body: JSON.stringify(data) }),
  },
  projects: {
    list: (workspaceId?: string) =>
      request<Project[]>(`/projects${workspaceId ? `?workspace_id=${workspaceId}` : ''}`),
    create: (data: ProjectCreate) =>
      request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
    get: (id: string) => request<Project>(`/projects/${id}`),
    update: (id: string, data: Partial<Pick<Project, 'title' | 'summary' | 'status'>>) =>
      request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  phases: {
    list: (projectId: string) => request<Phase[]>(`/projects/${projectId}/phases`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<Phase>(`/projects/${projectId}/phases`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Phase, 'title' | 'status'>>) =>
      request<Phase>(`/phases/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
    create: (projectId: string, data: { title: string; status?: string; priority?: string }) =>
      request<Task>(`/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Task, 'title' | 'status' | 'priority'>>) =>
      request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  decisions: {
    list: (projectId: string) => request<Decision[]>(`/projects/${projectId}/decisions`),
    create: (projectId: string, data: { title: string; decision: string; status?: string }) =>
      request<Decision>(`/projects/${projectId}/decisions`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Pick<Decision, 'title' | 'decision' | 'status'>>) =>
      request<Decision>(`/decisions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  risks: {
    list: (projectId: string) => request<Risk[]>(`/projects/${projectId}/risks`),
    create: (projectId: string, data: { title: string; severity: string; status?: string }) =>
      request<Risk>(`/projects/${projectId}/risks`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Pick<Risk, 'title' | 'severity' | 'status'>>) =>
      request<Risk>(`/risks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  blockers: {
    list: (projectId: string) => request<Blocker[]>(`/projects/${projectId}/blockers`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<Blocker>(`/projects/${projectId}/blockers`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Pick<Blocker, 'title' | 'status'>>) =>
      request<Blocker>(`/blockers/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
}
