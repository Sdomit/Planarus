import { describe, it, expect } from 'vitest'
import { buildTodoTree } from './todoTree'
import type { Todo } from '../api/client'

const t = (id: string, parent_id: string | null, label = id): Todo => ({
  id, project_id: 'p', parent_id, label, done: false, sort_order: 0,
  created_at: '', updated_at: '',
})

describe('buildTodoTree', () => {
  it('nests arbitrarily deep and preserves order', () => {
    const tree = buildTodoTree([t('a', null), t('a1', 'a'), t('a1x', 'a1'), t('b', null)])
    expect(tree.map((n) => n.id)).toEqual(['a', 'b'])
    expect(tree[0].children.map((n) => n.id)).toEqual(['a1'])
    expect(tree[0].children[0].children.map((n) => n.id)).toEqual(['a1x']) // sub-sub
  })

  it('surfaces an orphan (parent missing) at the top level', () => {
    const tree = buildTodoTree([t('orphan', 'gone')])
    expect(tree.map((n) => n.id)).toEqual(['orphan'])
  })

  it('returns [] for an empty list', () => {
    expect(buildTodoTree([])).toEqual([])
  })
})
