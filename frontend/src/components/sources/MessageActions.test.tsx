import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MessageActions } from './MessageActions'

// useTranslation is globally mocked in setup.ts (t returns the key string).

const h = vi.hoisted(() => ({
  createNoteMutate: vi.fn(),
  setReactionMutate: vi.fn(),
  reportMutate: vi.fn(),
  reactionPending: false,
  reportPending: false,
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/lib/hooks/use-notes', () => ({
  useCreateNote: () => ({ mutate: h.createNoteMutate, isPending: false }),
}))

vi.mock('@/lib/hooks/use-feedback', () => ({
  useSetReaction: () => ({ mutate: h.setReactionMutate, isPending: h.reactionPending }),
  useReportMessage: () => ({ mutate: h.reportMutate, isPending: h.reportPending }),
}))

vi.mock('sonner', () => ({
  toast: { success: h.toastSuccess, error: h.toastError },
}))

const baseProps = {
  content: 'The AI answer',
  notebookId: 'notebook:n1',
  sessionId: 'chat_session:s1',
  messageId: 'uuid-1',
  feedbackEnabled: true,
} as const

describe('MessageActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    h.reactionPending = false
    h.reportPending = false
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })
  afterEach(cleanup)

  it('still saves to note and copies (unchanged behavior)', async () => {
    render(<MessageActions {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.saveToNote' }))
    expect(h.createNoteMutate).toHaveBeenCalledWith(
      expect.objectContaining({ content: 'The AI answer', note_type: 'ai', notebook_id: 'notebook:n1' })
    )
    fireEvent.click(screen.getByRole('button', { name: 'chat.copy' }))
    await waitFor(() =>
      expect((navigator.clipboard.writeText as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('The AI answer')
    )
  })

  it('renders like/dislike/report for a persisted AI message', () => {
    render(<MessageActions {...baseProps} />)
    expect(screen.getByRole('button', { name: 'feedback.like' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'feedback.dislike' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'feedback.report' })).toBeInTheDocument()
  })

  it('does not render feedback actions without session/message id', () => {
    render(<MessageActions content="x" notebookId="notebook:n1" />)
    expect(screen.queryByRole('button', { name: 'feedback.like' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'feedback.report' })).toBeNull()
  })

  it('likes when none, and toggles off when already liked', () => {
    const { rerender } = render(<MessageActions {...baseProps} reaction={null} />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.like' }))
    expect(h.setReactionMutate).toHaveBeenCalledWith({ messageId: 'uuid-1', reaction: 'like' })

    h.setReactionMutate.mockClear()
    rerender(<MessageActions {...baseProps} reaction="like" />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.removeLike' }))
    expect(h.setReactionMutate).toHaveBeenCalledWith({ messageId: 'uuid-1', reaction: null })
  })

  it('switches like -> dislike (mutual exclusion)', () => {
    render(<MessageActions {...baseProps} reaction="like" />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.dislike' }))
    expect(h.setReactionMutate).toHaveBeenCalledWith({ messageId: 'uuid-1', reaction: 'dislike' })
  })

  it('reflects active state via aria-pressed', () => {
    render(<MessageActions {...baseProps} reaction="dislike" reported />)
    expect(screen.getByRole('button', { name: 'feedback.removeDislike' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'feedback.reported' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'feedback.like' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('disables feedback actions when feedbackEnabled is false', () => {
    render(<MessageActions {...baseProps} feedbackEnabled={false} />)
    expect(screen.getByRole('button', { name: 'feedback.like' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'feedback.dislike' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'feedback.report' })).toBeDisabled()
  })

  it('opens the report dialog, validates the reason, and submits trimmed', async () => {
    h.reportMutate.mockImplementation((_vars, opts) => opts?.onSuccess?.())
    render(<MessageActions {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.report' }))

    expect(await screen.findByText('feedback.reportTitle')).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: 'feedback.submitReport' })
    // empty reason -> disabled
    expect(submit).toBeDisabled()
    // whitespace-only -> still disabled
    const textarea = screen.getByLabelText('feedback.reportReasonLabel')
    fireEvent.change(textarea, { target: { value: '   ' } })
    expect(submit).toBeDisabled()
    // real reason (with surrounding spaces) -> enabled, submits trimmed
    fireEvent.change(textarea, { target: { value: '  spam answer  ' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    expect(h.reportMutate).toHaveBeenCalledWith(
      { messageId: 'uuid-1', reason: 'spam answer' },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    )
    // closes on success
    await waitFor(() => expect(screen.queryByText('feedback.reportTitle')).toBeNull())
  })

  it('disables the submit button while a report is pending', async () => {
    h.reportPending = true
    render(<MessageActions {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: 'feedback.report' }))
    const submit = await screen.findByRole('button', { name: 'feedback.submitReport' })
    expect(submit).toBeDisabled()
  })
})
