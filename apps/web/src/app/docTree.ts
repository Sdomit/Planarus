import type { DocSummary } from '../api/client'

export interface DocNode extends DocSummary {
  children: DocNode[]
}

/**
 * Build a nested tree from a flat doc list (already ordered by the API).
 * A doc whose parent is missing (deleted/foreign) is surfaced at the top level
 * so nothing is ever silently hidden. Input order is preserved. Mirrors
 * `buildTodoTree` (todoTree.ts).
 *
 * Cycle-safe. Every doc in a cycle has a parent that is present, so none of them
 * ever lands in `roots` — and no root can reach them either, which silently hid
 * the whole cyclic component (and its subtree) while the list header still
 * counted the rows. The server rejects new cycles (`hierarchy.validate_parent`)
 * and `doc_service.repair_parent_integrity` sweeps old ones, so this is a
 * recovery path — but it is exactly when a doc must not vanish from the UI.
 */
export function buildDocTree(flat: DocSummary[]): DocNode[] {
  const byId = new Map<string, DocNode>()
  for (const d of flat) byId.set(d.id, { ...d, children: [] })

  /** True if following this doc's parent chain revisits a node — i.e. it sits on
   *  a cycle. Bounded by `seen`, so it terminates on the malformed input it
   *  exists to detect. */
  const onCycle = (start: string): boolean => {
    const seen = new Set<string>()
    let cur: string | undefined = start
    while (cur !== undefined) {
      if (seen.has(cur)) return true
      seen.add(cur)
      cur = byId.get(cur)?.parent_doc_id ?? undefined
    }
    return false
  }

  const roots: DocNode[] = []
  for (const d of flat) {
    const node = byId.get(d.id)!
    const parent = d.parent_doc_id ? byId.get(d.parent_doc_id) : undefined
    // Cycle members are surfaced as roots and the back-edge is dropped. Merely
    // promoting them while still attaching would leave A in B.children and B in
    // A.children, which renders as infinitely nested rows.
    if (parent && !onCycle(d.id)) parent.children.push(node)
    else roots.push(node) // top-level, orphaned parent, or a cycle → surface it
  }
  return roots
}

/**
 * Walk `doc_id`'s ancestor chain (root-first) using an already-loaded id → doc
 * map, for a breadcrumb. Stops at a missing parent (deleted/foreign) rather
 * than throwing, same "surface, don't hide" rule as `buildDocTree`. Bounded so
 * a data cycle (pre-existing rows only — the API rejects new ones) can't loop
 * forever.
 */
const MAX_BREADCRUMB_DEPTH = 64

export function docAncestors(docId: string, byId: Map<string, DocSummary>): DocSummary[] {
  const chain: DocSummary[] = []
  const seen = new Set<string>()
  let current = byId.get(docId)?.parent_doc_id ?? null
  while (current && !seen.has(current) && chain.length < MAX_BREADCRUMB_DEPTH) {
    seen.add(current)
    const doc = byId.get(current)
    if (!doc) break
    chain.push(doc)
    current = doc.parent_doc_id
  }
  return chain.reverse()
}
