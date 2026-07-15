import { beforeEach, describe, expect, it } from 'vitest'
import {
  addCategory,
  assignCategory,
  categoryOf,
  listCategories,
} from './categories'

beforeEach(() => localStorage.clear())

describe('categories (localStorage)', () => {
  it('adds categories without duplicates, trimming whitespace', () => {
    addCategory('Work')
    addCategory('  Work  ')
    addCategory('Personal')
    addCategory('   ')
    expect(listCategories()).toEqual(['Work', 'Personal'])
  })

  it('assigns and reassigns a project, auto-registering the category', () => {
    assignCategory('proj_1', 'Clients')
    expect(categoryOf('proj_1')).toBe('Clients')
    expect(listCategories()).toContain('Clients')

    assignCategory('proj_1', 'Internal')
    expect(categoryOf('proj_1')).toBe('Internal')
  })

  it('clears an assignment with null', () => {
    assignCategory('proj_2', 'X')
    assignCategory('proj_2', null)
    expect(categoryOf('proj_2')).toBeNull()
  })
})
