import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type NotebookViewMode = 'tile' | 'list'

interface NotebookViewState {
  viewMode: NotebookViewMode
  setViewMode: (mode: NotebookViewMode) => void
}

export const useNotebookViewStore = create<NotebookViewState>()(
  persist(
    (set) => ({
      viewMode: 'list',
      setViewMode: (mode) => set({ viewMode: mode }),
    }),
    {
      name: 'notebook-view-storage',
    }
  )
)
