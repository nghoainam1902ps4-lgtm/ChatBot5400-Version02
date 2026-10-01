import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { readFileSync } from 'fs'
import { SearchInput } from './SearchInput'

const props = { placeholder: 'Find notebooks…', ariaLabel: 'Search notebooks', clearLabel: 'Clear the search' }

describe('SearchInput (generic)', () => {
  it('renders a search landmark with the caller placeholder and aria-label', () => {
    render(<SearchInput value="" onChange={vi.fn()} {...props} />)
    expect(screen.getByRole('search')).toBeInTheDocument()
    const input = screen.getByRole('textbox', { name: 'Search notebooks' })
    expect(input).toHaveAttribute('placeholder', 'Find notebooks…')
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveAttribute('inputmode', 'search')
    expect(input).toHaveAttribute('enterkeyhint', 'search')
    expect(input).toHaveAttribute('autocomplete', 'off')
    expect(input).toHaveAttribute('spellcheck', 'false')
  })

  it('shows the clear button only when there is a value', () => {
    const { rerender } = render(<SearchInput value="" onChange={vi.fn()} {...props} />)
    expect(screen.queryByRole('button', { name: 'Clear the search' })).not.toBeInTheDocument()
    rerender(<SearchInput value="abc" onChange={vi.fn()} {...props} />)
    expect(screen.getByRole('button', { name: 'Clear the search' })).toBeInTheDocument()
  })

  it('reports typed text', () => {
    const onChange = vi.fn()
    render(<SearchInput value="" onChange={onChange} {...props} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'quy dinh' } })
    expect(onChange).toHaveBeenCalledWith('quy dinh')
  })

  it('Escape clears only when there is a value', () => {
    const onChange = vi.fn()
    const { rerender } = render(<SearchInput value="abc" onChange={onChange} {...props} />)
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onChange).toHaveBeenCalledWith('')
    onChange.mockClear()
    rerender(<SearchInput value="" onChange={onChange} {...props} />)
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('clicking X clears and refocuses the input', () => {
    const onChange = vi.fn()
    render(<SearchInput value="abc" onChange={onChange} {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear the search' }))
    expect(onChange).toHaveBeenCalledWith('')
    expect(screen.getByRole('textbox')).toHaveFocus()
  })

  it('uses no Sources translation key or hardcoded domain copy', () => {
    const src = readFileSync('src/components/common/SearchInput.tsx', 'utf8')
    expect(src).not.toMatch(/sources\./)
    expect(src).not.toMatch(/useTranslation/)
  })
})
