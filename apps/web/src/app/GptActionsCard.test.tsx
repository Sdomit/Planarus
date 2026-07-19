import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import GptActionsCard from './GptActionsCard'

const gptOpenapi = vi.fn(async (profile = 'readonly') => ({
  openapi: '3.1.0',
  info: { title: `contract ${profile}` },
  servers: [{ url: 'https://REPLACE-WITH-YOUR-PUBLIC-HOST/api/external/v1' }],
  paths: {},
}))

vi.mock('../api/client', () => ({
  api: { integrations: { gptOpenapi: (...a: unknown[]) => gptOpenapi(...(a as [string])) } },
}))

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('GptActionsCard', () => {
  it('serves the contract and finalizes the server URL from a public host', async () => {
    render(<GptActionsCard active permitted hostsConfigured />)
    await waitFor(() => expect(screen.getByText(/REPLACE-WITH-YOUR-PUBLIC-HOST/)).toBeTruthy())
    fireEvent.change(screen.getByLabelText(/Public HTTPS host/i), { target: { value: 'https://approvo.example.com/' } })
    await waitFor(() => expect(screen.getByText(/https:\/\/approvo\.example\.com\/api\/external\/v1/)).toBeTruthy())
    // Placeholder is fully replaced in the finalized schema.
    expect(screen.queryByText(/REPLACE-WITH-YOUR-PUBLIC-HOST/)).toBeNull()
  })

  it('shows the exposure reason when not fully permitted', async () => {
    render(<GptActionsCard active={false} permitted={false} hostsConfigured={false} />)
    await waitFor(() => screen.getByText(/not permitted by environment/i))
  })

  it('warns on the read+propose profile and refetches that contract', async () => {
    render(<GptActionsCard active permitted hostsConfigured />)
    await waitFor(() => screen.getByText(/REPLACE-WITH-YOUR-PUBLIC-HOST/))
    fireEvent.click(screen.getByRole('tab', { name: /Read \+ propose/i }))
    expect(await screen.findByText(/import it for a first live GPT/i)).toBeTruthy()
    await waitFor(() => expect(gptOpenapi).toHaveBeenCalledWith('read_propose'))
  })
})
