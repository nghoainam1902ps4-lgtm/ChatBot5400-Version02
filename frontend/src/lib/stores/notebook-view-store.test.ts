import { afterEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'notebook-view-storage'

// Fresh module per test so persist hydrates from the localStorage set up here.
async function loadStore() {
  vi.resetModules()
  const { useNotebookViewStore } = await import('./notebook-view-store')
  return useNotebookViewStore
}

describe('notebook-view-store (P1A default view)', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('defaults to list for a new user', async () => {
    const store = await loadStore()
    expect(store.getState().viewMode).toBe('list')
  })

  it('keeps a persisted tile preference (no reset)', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: { viewMode: 'tile' }, version: 0 }))
    const store = await loadStore()
    expect(store.getState().viewMode).toBe('tile')
  })

  it('still persists toggles under the same key', async () => {
    const store = await loadStore()
    store.getState().setViewMode('tile')
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}').state.viewMode).toBe('tile')
    store.getState().setViewMode('list')
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}').state.viewMode).toBe('list')
  })
})
