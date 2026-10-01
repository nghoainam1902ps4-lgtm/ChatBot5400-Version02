import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TransformationCard } from './TransformationCard'
import type { Transformation } from '@/lib/types/transformations'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const mutate = vi.fn()
vi.mock('@/lib/hooks/use-transformations', () => ({
  useDeleteTransformation: () => ({ mutate, isPending: false }),
}))

const transformation: Transformation = {
  id: 'transformation:1',
  name: 'summarize',
  title: 'Summarize',
  description: 'Summarize the content',
  prompt: Array.from({ length: 200 }, (_, i) => `line ${i + 1}`).join('\n'),
  apply_default: false,
  model_id: null,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
}

const openMenu = () => {
  fireEvent.keyDown(screen.getByRole('button', { name: 'common.actions' }), { key: 'Enter' })
  return screen.getByRole('menu')
}

describe('TransformationCard (P1B)', () => {
  it('keeps the description in the header in both states and never duplicates it', () => {
    render(<TransformationCard transformation={transformation} />)
    expect(screen.getAllByText('Summarize the content')).toHaveLength(1)

    fireEvent.click(screen.getByText('summarize'))
    expect(screen.getAllByText('Summarize the content')).toHaveLength(1)
    expect(screen.queryByText('common.description')).toBeNull()
  })

  it('caps the prompt with an internal scroll and keeps the full content', () => {
    render(<TransformationCard transformation={transformation} />)
    fireEvent.click(screen.getByText('summarize'))
    const pre = document.querySelector('pre') as HTMLElement
    expect(pre.className).toContain('max-h-[40vh]')
    expect(pre.className).toContain('overflow-auto')
    expect(pre.textContent).toContain('line 200')
  })

  it('uses a 15px chevron', () => {
    const { container } = render(<TransformationCard transformation={transformation} />)
    expect(container.querySelector('.lucide-chevron-right')?.getAttribute('class')).toContain('size-[15px]')
    fireEvent.click(screen.getByText('summarize'))
    expect(container.querySelector('.lucide-chevron-down')?.getAttribute('class')).toContain('size-[15px]')
  })

  it('keeps Playground direct; Edit and Delete live in the menu', () => {
    const onPlayground = vi.fn()
    const onEdit = vi.fn()
    render(<TransformationCard transformation={transformation} onPlayground={onPlayground} onEdit={onEdit} />)

    fireEvent.click(screen.getByRole('button', { name: /transformations\.playground/ }))
    expect(onPlayground).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /common\.edit/ })).toBeNull()

    fireEvent.keyDown(within(openMenu()).getByRole('menuitem', { name: 'common.edit' }), { key: 'Enter' })
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  it('menu Delete is destructive and still opens the confirm dialog before deleting', () => {
    render(<TransformationCard transformation={transformation} />)
    const del = within(openMenu()).getByRole('menuitem', { name: 'common.delete' })
    expect(del).toHaveAttribute('data-variant', 'destructive')
    fireEvent.keyDown(del, { key: 'Enter' })

    expect(screen.getByText('transformations.deleteConfirm')).toBeInTheDocument()
    expect(mutate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'common.delete' }))
    expect(mutate).toHaveBeenCalledWith('transformation:1')
  })

  it('the action menu is non-modal: opening it never locks body pointer events', () => {
    render(<TransformationCard transformation={transformation} />)
    openMenu()
    expect(document.body.style.pointerEvents).not.toBe('none')
  })
})
