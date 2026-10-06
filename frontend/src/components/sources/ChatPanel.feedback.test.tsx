import { render, screen, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ChatPanel } from './ChatPanel'
import type { SourceChatMessage } from '@/lib/types/api'

// useTranslation + useAuth are globally mocked in setup.ts.

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal: vi.fn() }),
}))

vi.mock('@/lib/hooks/use-notes', () => ({
  useCreateNote: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const fb = vi.hoisted(() => ({
  data: [{ message_id: 'uuid-ai', reaction: 'like', reported: false }] as unknown,
  isSuccess: true,
}))
const setReactionMutate = vi.fn()
vi.mock('@/lib/hooks/use-feedback', () => ({
  useSessionFeedback: () => ({ data: fb.data, isSuccess: fb.isSuccess }),
  useSetReaction: () => ({ mutate: setReactionMutate, isPending: false }),
  useReportMessage: () => ({ mutate: vi.fn(), isPending: false }),
}))

const messages: SourceChatMessage[] = [
  { id: 'h1', type: 'human', content: 'Question?' },
  { id: 'uuid-ai', type: 'ai', content: 'Persisted answer.' },
  { id: 'ai-temp', type: 'ai', content: 'Streaming answer.' },
]

function renderPanel(isStreaming = false) {
  return render(
    <ChatPanel
      messages={messages}
      isStreaming={isStreaming}
      contextIndicators={null}
      onSendMessage={vi.fn()}
      currentSessionId="chat_session:s1"
      notebookId="notebook:n1"
    />
  )
}

describe('ChatPanel feedback wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fb.data = [{ message_id: 'uuid-ai', reaction: 'like', reported: false }]
    fb.isSuccess = true
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
  })
  afterEach(cleanup)

  it('renders feedback actions once per AI message, never for human messages', () => {
    renderPanel()
    // two AI messages -> two report buttons; the human message has none
    expect(screen.getAllByRole('button', { name: 'feedback.report' })).toHaveLength(2)
  })

  it('reflects persisted reaction state from the batch query', () => {
    renderPanel()
    // the persisted AI message carries reaction=like -> shows "removeLike", enabled
    const removeLike = screen.getByRole('button', { name: 'feedback.removeLike' })
    expect(removeLike).toBeEnabled()
    expect(removeLike).toHaveAttribute('aria-pressed', 'true')
  })

  it('disables feedback on a temporary (streaming) AI message id', () => {
    renderPanel()
    // the temp 'ai-temp' message has no reaction -> shows "like", and is disabled
    const likeButtons = screen.getAllByRole('button', { name: 'feedback.like' })
    expect(likeButtons).toHaveLength(1)
    expect(likeButtons[0]).toBeDisabled()
  })

  it('disables all feedback actions while streaming', () => {
    renderPanel(true)
    for (const btn of screen.getAllByRole('button', { name: 'feedback.report' })) {
      expect(btn).toBeDisabled()
    }
  })

  it('disables feedback until the batch feedback state has loaded (isSuccess)', () => {
    // batch query still loading -> actions must be disabled to avoid acting on
    // unknown current state (R3)
    fb.data = undefined
    fb.isSuccess = false
    renderPanel(false)
    for (const btn of screen.getAllByRole('button', { name: 'feedback.report' })) {
      expect(btn).toBeDisabled()
    }
    // and no reaction state is assumed: the persisted AI shows "like" (default), disabled
    const likeButtons = screen.getAllByRole('button', { name: 'feedback.like' })
    expect(likeButtons.every((b) => (b as HTMLButtonElement).disabled)).toBe(true)
  })
})
