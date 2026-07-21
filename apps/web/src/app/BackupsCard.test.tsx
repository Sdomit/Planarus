import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import BackupsCard from './BackupsCard'

afterEach(cleanup)

const list = vi.fn(async () => [
  {
    name: 'planarus-20260719T220501123456Z.db',
    size_bytes: 2048,
    created_at: '2026-07-19T22:05:01Z',
  },
])
const create = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    backups: {
      list: () => list(),
      create: () => create(),
    },
  },
}))

const props = {
  enabled: true,
  savedEnabled: true,
  retention: 7,
  offsite: false,
  supported: true,
  offsiteSupported: true,
  dirConfigured: true,
  onChange: vi.fn(),
}

describe('BackupsCard', () => {
  it('lists existing backups with size and time', async () => {
    render(<BackupsCard {...props} />)
    expect(await screen.findByText('planarus-20260719T220501123456Z.db')).toBeTruthy()
    expect(screen.getByText(/2 KB/)).toBeTruthy()
  })

  it('does not offer a backup the server is guaranteed to reject', async () => {
    // The switch is save-gated, so until it is stored POST /backups 409s.
    // Offering an action that cannot succeed is worse than disabling it.
    render(<BackupsCard {...props} savedEnabled={false} />)
    await screen.findByText('Backups')
    const button = screen.getByRole('button', { name: 'Back up now' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(screen.getByText(/Save your change before taking a backup/)).toBeTruthy()
  })

  it('reports a failed off-site push without calling the backup a failure', async () => {
    create.mockResolvedValueOnce({
      backup: { name: 'planarus-x.db', size_bytes: 10, created_at: 't' },
      pruned: 0,
      offsite: null,
      offsite_error: 'RuntimeError: s3 down',
    })
    render(<BackupsCard {...props} />)
    await screen.findByText('Backups')
    fireEvent.click(screen.getByRole('button', { name: 'Back up now' }))

    // The verified local snapshot is still reported as made…
    expect(await screen.findByText(/planarus-x\.db/)).toBeTruthy()
    // …and the degraded off-site state is surfaced rather than swallowed.
    expect(screen.getByText(/off-site copy did not happen: RuntimeError: s3 down/)).toBeTruthy()
  })

  it('explains why off-site is unavailable on the local storage backend', async () => {
    render(<BackupsCard {...props} offsiteSupported={false} />)
    await screen.findByText('Backups')
    const box = screen.getByLabelText('Also copy each backup off-site') as HTMLInputElement
    expect(box.disabled).toBe(true)
    expect(screen.getByText(/PLANARUS_STORAGE_BACKEND=s3/)).toBeTruthy()
  })
})
