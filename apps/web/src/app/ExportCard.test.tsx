import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ExportCard from './ExportCard'

afterEach(cleanup)

// vi.hoisted so the factory can reference these directly (no spread wrapper —
// spreading into a vi.fn's inferred signature trips tsc -b's TS2556).
const { exportFn, importFn } = vi.hoisted(() => ({
  exportFn: vi.fn(async (_id: string) => ({ planarus_export: 1, project: { title: 'Demo' } })),
  importFn: vi.fn(async (_ws: string, _data: unknown) => ({ id: 'p2', title: 'Imported Demo' })),
}))

vi.mock('../api/client', () => ({
  api: {
    projects: {
      list: vi.fn(async () => [{ id: 'p1', title: 'Demo', slug: 'demo' }]),
      export: exportFn,
      import: importFn,
    },
    workspaces: { list: vi.fn(async () => [{ id: 'w1', name: 'Main' }]) },
  },
}))

// jsdom 25 omits the standard Blob/File .text(); real browsers have it.
function jsonFile(content: string, name: string, type: string): File {
  const f = new File([content], name, { type })
  Object.defineProperty(f, 'text', { value: async () => content })
  return f
}

describe('ExportCard', () => {
  beforeEach(() => { exportFn.mockClear(); importFn.mockClear() })

  it('downloads the selected project as JSON', async () => {
    const createUrl = vi.fn(() => 'blob:x')
    vi.stubGlobal('URL', { createObjectURL: createUrl, revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<ExportCard />)
    await screen.findByRole('option', { name: 'Demo' })
    fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }))

    await waitFor(() => expect(exportFn).toHaveBeenCalledWith('p1'))
    expect(createUrl).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()

    click.mockRestore()
    vi.unstubAllGlobals()
  })

  it('imports an uploaded JSON file into the selected workspace', async () => {
    render(<ExportCard />)
    await screen.findByRole('option', { name: 'Main' })
    const file = jsonFile(JSON.stringify({ planarus_export: 1 }), 'demo.json', 'application/json')
    fireEvent.change(screen.getByLabelText('Export file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))

    await waitFor(() => expect(importFn).toHaveBeenCalledWith('w1', { planarus_export: 1 }))
    expect(await screen.findByText(/Imported .* as a new project/)).toBeTruthy()
  })

  it('rejects a non-JSON file with a friendly error', async () => {
    render(<ExportCard />)
    await screen.findByRole('option', { name: 'Main' })
    const file = jsonFile('not json', 'bad.txt', 'text/plain')
    fireEvent.change(screen.getByLabelText('Export file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))

    expect(await screen.findByText(/not valid JSON/)).toBeTruthy()
    expect(importFn).not.toHaveBeenCalled()
  })
})
