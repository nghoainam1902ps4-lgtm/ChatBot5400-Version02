import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ChatPanel } from './ChatPanel'

// useTranslation is mocked globally in setup.ts (t returns the key string)

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal: vi.fn() }),
}))

// Keep the message-content deps light for this composer-focused test.
vi.mock('@/components/sources/MessageActions', () => ({
  MessageActions: () => null,
}))

// ChatPanel fetches batch feedback state via useSessionFeedback; stub it so
// these composer tests don't need a QueryClientProvider.
vi.mock('@/lib/hooks/use-feedback', () => ({
  useSessionFeedback: () => ({ data: [] }),
}))

describe('ChatPanel composer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom does not implement scrollIntoView (used by the auto-scroll effect).
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
  })

  const getTextarea = () => screen.getByRole('textbox') as HTMLTextAreaElement

  it('sends the typed message and clears the input on send-button click', () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: '  hello world  ' } })

    const sendButton = screen.getByRole('button')
    fireEvent.click(sendButton)

    expect(onSendMessage).toHaveBeenCalledTimes(1)
    expect(onSendMessage).toHaveBeenCalledWith('hello world', undefined)
    expect(textarea.value).toBe('')
  })

  it('sends on Cmd+Enter on macOS', () => {
    const uaSpy = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
    )
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: 'via cmd' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true, ctrlKey: false })

    expect(onSendMessage).toHaveBeenCalledWith('via cmd', undefined)
    expect(textarea.value).toBe('')
    uaSpy.mockRestore()
  })

  it('sends on Ctrl+Enter on non-macOS', () => {
    const uaSpy = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    )
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={false}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    fireEvent.change(textarea, { target: { value: 'via ctrl' } })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true, metaKey: false })

    expect(onSendMessage).toHaveBeenCalledWith('via ctrl', undefined)
    expect(textarea.value).toBe('')
    uaSpy.mockRestore()
  })

  it('does not send while streaming', () => {
    const onSendMessage = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        isStreaming={true}
        contextIndicators={null}
        onSendMessage={onSendMessage}
      />
    )

    const textarea = getTextarea()
    // Textarea is disabled while streaming, but the guard must also hold.
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    expect(onSendMessage).not.toHaveBeenCalled()
  })
})

// PA1: ChatComposer publishes its height as --composer-h on <html> so the
// toaster can sit above the input. ResizeObserver is mocked so each test drives
// the measured heights directly.
describe('ChatPanel composer height (--composer-h)', () => {
  class MockResizeObserver {
    static instances: MockResizeObserver[] = []
    targets: Element[] = []
    disconnected = false
    constructor(private readonly callback: ResizeObserverCallback) {
      MockResizeObserver.instances.push(this)
    }
    observe(target: Element) {
      this.targets.push(target)
    }
    unobserve() {}
    disconnect() {
      this.disconnected = true
    }
    /** Report a new border-box height for the observed element. */
    resize(height: number) {
      const entry = {
        target: this.targets[0],
        borderBoxSize: [{ blockSize: height, inlineSize: 320 }],
      } as unknown as ResizeObserverEntry
      act(() => this.callback([entry], this as unknown as ResizeObserver))
    }
  }

  const composerHeight = () => document.documentElement.style.getPropertyValue('--composer-h')

  // Radix ScrollArea also uses ResizeObserver; the composer's observer is the
  // one watching the element that contains a chat textarea.
  const composerObservers = () =>
    MockResizeObserver.instances.filter((o) => o.targets[0]?.querySelector('textarea'))

  const panel = (key?: string) => (
    <ChatPanel key={key} messages={[]} isStreaming={false} contextIndicators={null} onSendMessage={vi.fn()} />
  )

  beforeEach(() => {
    MockResizeObserver.instances = []
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    document.documentElement.style.removeProperty('--composer-h')
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('updates --composer-h whenever the composer height changes', () => {
    render(panel())
    const [observer] = composerObservers()
    expect(observer).toBeDefined()

    observer.resize(91)
    expect(composerHeight()).toBe('91px')

    // Multi-line input grows the composer: the variable follows.
    observer.resize(195)
    expect(composerHeight()).toBe('195px')

    // Fractional heights are rounded up so the toast never touches the composer.
    observer.resize(130.2)
    expect(composerHeight()).toBe('131px')
  })

  it('ignores a hidden composer (height 0) instead of overwriting the visible one', () => {
    render(
      <>
        {panel('visible')}
        {panel('hidden')}
      </>
    )
    const [visible, hidden] = composerObservers()
    expect(composerObservers()).toHaveLength(2)

    visible.resize(91)
    hidden.resize(0) // display:none twin (desktop column below lg)
    expect(composerHeight()).toBe('91px')

    // If the only visible composer is hidden too, the variable is removed.
    visible.resize(0)
    expect(composerHeight()).toBe('')
  })

  it('publishes the largest height when several composers are visible', () => {
    render(
      <>
        {panel('a')}
        {panel('b')}
      </>
    )
    const [a, b] = composerObservers()

    a.resize(91)
    b.resize(130)
    expect(composerHeight()).toBe('130px')

    b.resize(60)
    expect(composerHeight()).toBe('91px')
  })

  it('disconnects its observer on unmount and recomputes or clears --composer-h', () => {
    const first = render(panel())
    const second = render(panel())
    const [a, b] = composerObservers()
    a.resize(91)
    b.resize(130)
    expect(composerHeight()).toBe('130px')

    // Unmounting the taller composer falls back to the remaining one.
    second.unmount()
    expect(b.disconnected).toBe(true)
    expect(a.disconnected).toBe(false)
    expect(composerHeight()).toBe('91px')

    // No composer left: no stale height remains.
    first.unmount()
    expect(a.disconnected).toBe(true)
    expect(composerHeight()).toBe('')
  })
})
