import { describe, it, expect } from 'vitest'
import { buildDocTree, docAncestors } from './docTree'
import type { DocSummary } from '../api/client'

const d = (id: string, parent_doc_id: string | null, title = id): DocSummary => ({
  id, project_id: 'p', parent_doc_id, title, slug: id, doc_type: 'note',
  editor_format: 'tiptap_json', status: 'draft', sort_order: 0, version: 1,
  updated_at: '', archived_at: null, color: null,
})

describe('buildDocTree', () => {
  it('nests arbitrarily deep and preserves order', () => {
    const tree = buildDocTree([d('a', null), d('a1', 'a'), d('a1x', 'a1'), d('b', null)])
    expect(tree.map((n) => n.id)).toEqual(['a', 'b'])
    expect(tree[0].children.map((n) => n.id)).toEqual(['a1'])
    expect(tree[0].children[0].children.map((n) => n.id)).toEqual(['a1x'])
  })

  it('surfaces an orphan (parent missing) at the top level', () => {
    const tree = buildDocTree([d('orphan', 'gone')])
    expect(tree.map((n) => n.id)).toEqual(['orphan'])
  })

  it('returns [] for an empty list', () => {
    expect(buildDocTree([])).toEqual([])
  })

  // A cycle member always has a present parent, so it never landed in `roots`
  // and no root could reach it — the whole component vanished from the tree
  // while the list header still counted the rows.
  it('surfaces a two-node cycle instead of hiding it', () => {
    const tree = buildDocTree([d('x', 'y'), d('y', 'x')])
    expect(tree.map(n => n.id).sort()).toEqual(['x', 'y'])
  })

  it('surfaces a self-parent', () => {
    expect(buildDocTree([d('solo', 'solo')]).map(n => n.id)).toEqual(['solo'])
  })

  it('does not nest a cycle into itself (would render infinitely)', () => {
    const tree = buildDocTree([d('x', 'y'), d('y', 'x')])
    expect(tree.every(n => n.children.length === 0)).toBe(true)
  })

  it('keeps healthy siblings nested while a cycle sits alongside', () => {
    const tree = buildDocTree([d('root', null), d('kid', 'root'), d('x', 'y'), d('y', 'x')])
    const root = tree.find(n => n.id === 'root')!
    expect(root.children.map(n => n.id)).toEqual(['kid'])
    expect(tree.map(n => n.id).sort()).toEqual(['root', 'x', 'y'])
  })

  it('every input doc appears exactly once in the tree', () => {
    const flat = [d('a', null), d('a1', 'a'), d('x', 'y'), d('y', 'x'), d('orphan', 'gone')]
    const seen: string[] = []
    const walk = (nodes: ReturnType<typeof buildDocTree>) => {
      for (const n of nodes) { seen.push(n.id); walk(n.children) }
    }
    walk(buildDocTree(flat))
    expect(seen.sort()).toEqual(['a', 'a1', 'orphan', 'x', 'y'])
  })
})

describe('docAncestors', () => {
  const byId = new Map<string, DocSummary>(
    [d('root', null), d('mid', 'root'), d('leaf', 'mid')].map((doc) => [doc.id, doc]),
  )

  it('walks the chain root-first', () => {
    expect(docAncestors('leaf', byId).map((n) => n.id)).toEqual(['root', 'mid'])
  })

  it('is empty for a top-level doc', () => {
    expect(docAncestors('root', byId)).toEqual([])
  })

  it('stops at a missing parent instead of throwing', () => {
    const partial = new Map(byId)
    partial.delete('root')
    expect(docAncestors('leaf', partial).map((n) => n.id)).toEqual(['mid'])
  })

  it('does not loop forever on a cycle', () => {
    const cyclic = new Map<string, DocSummary>([
      ['x', d('x', 'y')],
      ['y', d('y', 'x')],
    ])
    expect(docAncestors('x', cyclic).length).toBeLessThan(10)
  })
})
