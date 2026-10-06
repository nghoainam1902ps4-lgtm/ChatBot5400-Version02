import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useSetReaction, sessionFeedbackKey } from './use-feedback'
import type { FeedbackState } from '@/lib/types/api'

// useAuth is globally mocked (user.id === '1'); useTranslation returns the key.

const h = vi.hoisted(() => ({ setReaction: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn() }))

vi.mock('@/lib/api/feedback', () => ({
  feedbackApi: { setReaction: h.setReaction },
}))
vi.mock('sonner', () => ({ toast: { success: h.toastSuccess, error: h.toastError } }))

const SESSION = 'chat_session:s1'
const KEY = sessionFeedbackKey(SESSION, '1')

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  qc.setQueryData<FeedbackState[]>(KEY, [
    { message_id: 'm1', reaction: null, reported: false },
  ])
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return { qc, wrapper }
}

const reactionAt0 = (qc: QueryClient) =>
  qc.getQueryData<FeedbackState[]>(KEY)?.[0].reaction

describe('useSetReaction optimistic update', () => {
  beforeEach(() => vi.clearAllMocks())

  it('optimistically sets the reaction and reconciles with server truth on success', async () => {
    const d = deferred<FeedbackState>()
    h.setReaction.mockReturnValue(d.promise)
    const { qc, wrapper } = makeWrapper()
    const { result } = renderHook(() => useSetReaction(SESSION), { wrapper })

    await act(async () => {
      result.current.mutate({ messageId: 'm1', reaction: 'like' })
    })
    // optimistic: cache shows 'like' while the request is still in flight
    expect(reactionAt0(qc)).toBe('like')

    await act(async () => {
      d.resolve({ message_id: 'm1', reaction: 'like', reported: false })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(qc.getQueryData<FeedbackState[]>(KEY)?.[0]).toEqual({
      message_id: 'm1',
      reaction: 'like',
      reported: false,
    })
    expect(h.toastSuccess).toHaveBeenCalledWith('feedback.saved')
  })

  it('rolls back to the previous state and shows an error toast on failure', async () => {
    const d = deferred<FeedbackState>()
    h.setReaction.mockReturnValue(d.promise)
    const { qc, wrapper } = makeWrapper()
    const { result } = renderHook(() => useSetReaction(SESSION), { wrapper })

    await act(async () => {
      result.current.mutate({ messageId: 'm1', reaction: 'dislike' })
    })
    expect(reactionAt0(qc)).toBe('dislike') // optimistic flip

    await act(async () => {
      d.reject(new Error('boom'))
      await d.promise.catch(() => {})
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    // rolled back to the exact previous state (reaction null)
    expect(reactionAt0(qc)).toBeNull()
    expect(h.toastError).toHaveBeenCalledWith('feedback.failed')
  })

  it('leaves no optimistic ghost when the cache was empty and the mutation fails', async () => {
    const d = deferred<FeedbackState>()
    h.setReaction.mockReturnValue(d.promise)
    // wrapper with NO seeded data for the key (undefined cache)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(() => useSetReaction(SESSION), { wrapper })

    await act(async () => {
      result.current.mutate({ messageId: 'm1', reaction: 'like' })
    })
    // optimistic entry exists transiently
    expect(qc.getQueryData<FeedbackState[]>(KEY)?.[0]?.reaction).toBe('like')

    await act(async () => {
      d.reject(new Error('boom'))
      await d.promise.catch(() => {})
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    // no ghost: the optimistic data is fully removed (back to undefined)
    expect(qc.getQueryData<FeedbackState[]>(KEY)).toBeUndefined()
  })

  it('removes the cache entry when the server deletes the row (reaction null, not reported)', async () => {
    h.setReaction.mockResolvedValue({ message_id: 'm1', reaction: null, reported: false })
    const { qc, wrapper } = makeWrapper()
    const { result } = renderHook(() => useSetReaction(SESSION), { wrapper })

    act(() => {
      result.current.mutate({ messageId: 'm1', reaction: null })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const list = qc.getQueryData<FeedbackState[]>(KEY) ?? []
    expect(list.find((f) => f.message_id === 'm1')).toBeUndefined() // no {null,false} ghost
  })
})
