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
}
