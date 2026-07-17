import type { Todo } from '../api/client'

export interface TodoNode extends Todo {
  children: TodoNode[]
}

/**
 * Build a nested tree from a flat todo list (already ordered by the API).
 * A todo whose parent is missing (deleted/foreign) is surfaced at the top level
 * so nothing is ever silently hidden. Input order is preserved.
 */
export function buildTodoTree(flat: Todo[]): TodoNode[] {
  const byId = new Map<string, TodoNode>()
  for (const t of flat) byId.set(t.id, { ...t, children: [] })
  const roots: TodoNode[] = []
  for (const t of flat) {
    const node = byId.get(t.id)!
    const parent = t.parent_id ? byId.get(t.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node) // top-level, or orphaned parent → surface it
  }
  return roots
}
