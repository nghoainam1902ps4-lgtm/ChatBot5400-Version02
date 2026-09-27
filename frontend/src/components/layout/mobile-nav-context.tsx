'use client'

import { createContext, useContext } from 'react'

/**
 * Presentation-only context for the M1 mobile shell (< 1024px). Provided by
 * AppShell; it carries no navigation or business state of its own.
 * - `openNav` opens the navigation drawer (the desktop AppSidebar reused).
 * - `topBarActions` is the DOM node in a page's mobile top bar where the
 *   visible chat panel portals its session button, so the session dialog state
 *   stays inside ChatPanel.
 */
interface MobileNavContextValue {
  openNav: () => void
  topBarActions: HTMLElement | null
  setTopBarActions: (node: HTMLElement | null) => void
}

const noop = () => {}

export const MobileNavContext = createContext<MobileNavContextValue>({
  openNav: noop,
  topBarActions: null,
  setTopBarActions: noop,
})

export function useMobileNav() {
  return useContext(MobileNavContext)
}
