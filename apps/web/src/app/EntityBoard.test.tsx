import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { EntityBoard, type BoardCol } from './EntityBoard'

afterEach(cleanup)

const columns: BoardCol[] = [
  { key: 'todo', label: 'To do', statuses: ['todo'], dot: '#888' },
  { key: 'doing', label: 'Doing', statuses: ['doing'], dot: '#08f' },
  { key: 'done', label: 'Done', statuses: ['done'], dot: '#0a0' },
]

type Item = { id: string; title: string; status: string }

function setup(status: string) {
  const onRestatus = vi.fn()
  const items: Item[] = [{ id: '1', title: 'Ship it', status }]
  render(
    <EntityBoard
      items={items}
      columns={columns}
      statusOf={i => i.status}
      onRestatus={onRestatus}
      labelOf={i => i.title}
      renderCard={i => <span>{i.title}</span>}
    />,
  )
  return { onRestatus }
}

// The board's cards carry no status control of their own, and dragging is
// mouse-only, so these buttons are the ONLY way to restatus on a touch device.
describe('EntityBoard column move buttons', () => {
  it('moves a card to the next column', () => {
    const { onRestatus } = setup('todo')
    fireEvent.click(screen.getByLabelText('Move Ship it to Doing'))
    expect(onRestatus).toHaveBeenCalledWith(
      expect.objectContaining({ id: '1' }),
      'doing',
    )
  })

  it('moves a card to the previous column', () => {
    const { onRestatus } = setup('done')
    fireEvent.click(screen.getByLabelText('Move Ship it to Doing'))
    expect(onRestatus).toHaveBeenCalledWith(
      expect.objectContaining({ id: '1' }),
      'doing',
    )
  })

  it('disables the left button in the first column', () => {
    setup('todo')
    const btn = screen.getByLabelText('Ship it is in the first column') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('disables the right button in the last column', () => {
    setup('done')
    const btn = screen.getByLabelText('Ship it is in the last column') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('does not fire a write when the button is disabled', () => {
    const { onRestatus } = setup('todo')
    fireEvent.click(screen.getByLabelText('Ship it is in the first column'))
    expect(onRestatus).not.toHaveBeenCalled()
  })
})
