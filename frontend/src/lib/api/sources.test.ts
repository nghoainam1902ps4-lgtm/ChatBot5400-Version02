import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('./client', () => ({ default: { post: (...args: unknown[]) => post(...args) } }))

import { sourcesApi } from './sources'

describe('sourcesApi.create', () => {
  beforeEach(() => {
    post.mockReset()
    post.mockResolvedValue({ data: { id: 'source:1' } })
  })

  it('sends the chosen reviewer so the submission is routed to them', async () => {
    await sourcesApi.create({
      type: 'text',
      title: 'TEST-B7',
      content: 'KIEMTRA107',
      notebooks: [],
      reviewer_id: 'user:p',
    })
    const form = post.mock.calls[0][1] as FormData
    expect(form.get('reviewer_id')).toBe('user:p')
  })

  it('omits reviewer_id when none was chosen', async () => {
    await sourcesApi.create({ type: 'text', title: 't', content: 'x' })
    const form = post.mock.calls[0][1] as FormData
    expect(form.has('reviewer_id')).toBe(false)
  })
})
