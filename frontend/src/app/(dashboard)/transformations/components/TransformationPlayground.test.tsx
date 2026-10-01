import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TransformationPlayground } from './TransformationPlayground'
import type { Transformation } from '@/lib/types/transformations'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const mutateAsync = vi.fn()
let isPending = false
vi.mock('@/lib/hooks/use-transformations', () => ({
  useExecuteTransformation: () => ({ mutateAsync, isPending }),
}))
vi.mock('@/components/common/ModelSelector', () => ({
  ModelSelector: ({ onChange }: { onChange: (v: string) => void }) => (
    <button type="button" onClick={() => onChange('model:1')}>pick model</button>
  ),
}))

const tr = { id: 'transformation:1', name: 'summarize' } as Transformation

function ready() {
  render(<TransformationPlayground transformations={[tr]} selectedTransformation={tr} />)
  fireEvent.click(screen.getByText('pick model'))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'input text' } })
  return screen.getByRole('button', { name: /transformations\.runTest/ })
}

describe('TransformationPlayground (P1B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    isPending = false
  })

  it('labels the selector with transformations.selectLabel and preselects the given transformation', () => {
    render(<TransformationPlayground transformations={[tr]} selectedTransformation={tr} />)
    expect(screen.getByText('transformations.selectLabel')).toBeInTheDocument()
    expect(screen.queryByText('navigation.transformation')).toBeNull()
    expect(screen.getByRole('combobox')).toHaveTextContent('summarize')
  })

  it('run button is full width and keeps the canExecute guard', () => {
    render(<TransformationPlayground transformations={[tr]} />)
    const run = screen.getByRole('button', { name: /transformations\.runTest/ })
    expect(run.className).toContain('w-full')
    expect(run).toBeDisabled()
  })

  it('runs with the same payload, then shows ONE capped result surface (no Card-in-Card, no fixed 400px)', async () => {
    mutateAsync.mockResolvedValue({ output: '**short** result' })
    const run = ready()
    expect(run).toBeEnabled()
    fireEvent.click(run)
    expect(mutateAsync).toHaveBeenCalledWith({ transformation_id: 'transformation:1', input_text: 'input text', model_id: 'model:1' })

    const out = await waitFor(() => {
      const el = document.querySelector('[data-slot="playground-output"]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    expect(out.className).toContain('max-h-[400px]')
    expect(out.className).toContain('overflow-auto')
    expect(out.className).not.toMatch(/(^| )h-\[400px\]/)
    expect(out.querySelector('[data-slot="card"]')).toBeNull()
    expect(out.closest('[data-slot="card"]')?.querySelectorAll('[data-slot="card"]').length ?? 0).toBe(0)
    // Markdown pipeline still renders
    expect(out.querySelector('strong')).toHaveTextContent('short')
  })

  it('renders Markdown tables through the existing components', async () => {
    mutateAsync.mockResolvedValue({ output: '| a | b |\n|---|---|\n| 1 | 2 |' })
    fireEvent.click(ready())
    await waitFor(() => expect(document.querySelector('[data-slot="playground-output"] table')).not.toBeNull())
    expect(document.querySelector('[data-slot="playground-output"] table')?.className).toContain('border-collapse')
  })
})
