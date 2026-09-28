import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SourceSearchInput } from './SourceSearchInput'

// useTranslation is mocked globally in setup.ts (t returns the key string)

describe('SourceSearchInput', () => {
  it('shows the localized placeholder and no clear button when empty', () => {
    render(<SourceSearchInput value="" onChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('sources.searchSourcesPlaceholder')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'sources.clearSearch' })).not.toBeInTheDocument()
  })

  it('reports typed text', () => {
    const onChange = vi.fn()
    render(<SourceSearchInput value="" onChange={onChange} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'quy dinh' } })
    expect(onChange).toHaveBeenCalledWith('quy dinh')
  })

  it('clears via the X button and refocuses the input', () => {
    const onChange = vi.fn()
    render(<SourceSearchInput value="641" onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'sources.clearSearch' }))
    expect(onChange).toHaveBeenCalledWith('')
    expect(screen.getByRole('textbox')).toHaveFocus()
  })

  it('clears on Escape only when there is a query', () => {
    const onChange = vi.fn()
    const { rerender } = render(<SourceSearchInput value="641" onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onChange).toHaveBeenCalledWith('')

    onChange.mockClear()
    rerender(<SourceSearchInput value="" onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onChange).not.toHaveBeenCalled()
  })
})
