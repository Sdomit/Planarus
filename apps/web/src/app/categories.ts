// UI-only project categories, persisted in localStorage. Deliberately client-side:
// no backend, no migration — so categories don't sync across machines and aren't
// visible to the API/agents. Two keys: the ordered list of category names, and a
// {projectId: category} assignment map.
const CATS_KEY = 'approvo.categories'
const ASSIGN_KEY = 'approvo.projectCategory'

export const UNCATEGORIZED = '__uncategorized__'

function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, val: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(val))
  } catch {
    /* ignore quota/denied — categories are a convenience, not source of truth */
  }
}

export function listCategories(): string[] {
  return read<string[]>(CATS_KEY, [])
}

export function addCategory(name: string): void {
  const n = name.trim()
  if (!n) return
  const cats = listCategories()
  if (!cats.includes(n)) write(CATS_KEY, [...cats, n])
}

function assignments(): Record<string, string> {
  return read<Record<string, string>>(ASSIGN_KEY, {})
}

export function categoryOf(projectId: string): string | null {
  return assignments()[projectId] ?? null
}

export function assignCategory(projectId: string, category: string | null): void {
  const map = assignments()
  if (category) {
    addCategory(category)
    map[projectId] = category
  } else {
    delete map[projectId]
  }
  write(ASSIGN_KEY, map)
}
