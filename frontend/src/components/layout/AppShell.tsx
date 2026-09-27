'use client'

import { useMemo, useState } from 'react'
import { AppSidebar } from './AppSidebar'
import { SetupBanner } from './SetupBanner'
import { MobileNavDrawer } from './MobileNavDrawer'
import { MobileTopBar } from './MobileTopBar'
import { MobileNavContext } from './mobile-nav-context'
import { useVisualViewportVars } from '@/lib/hooks/use-visual-viewport'

interface AppShellProps {
  children: React.ReactNode
  /** The page renders its own mobile top bar (e.g. the notebook page). */
  hideMobileTopBar?: boolean
}

export function AppShell({ children, hideMobileTopBar = false }: AppShellProps) {
  const [navOpen, setNavOpen] = useState(false)
  const [topBarActions, setTopBarActions] = useState<HTMLElement | null>(null)
  const mobileNav = useMemo(
    () => ({ openNav: () => setNavOpen(true), topBarActions, setTopBarActions }),
    [topBarActions]
  )
  // < lg: size the shell to the visual viewport so the keyboard never covers
  // the composer. lg+: no-op.
  useVisualViewportVars()

  return (
    <MobileNavContext.Provider value={mobileNav}>
      {/* lg+: unchanged (sidebar rail + main, full height). Below lg the shell is
          pinned to the visual viewport (100dvh fallback), pads the top safe area,
          and the rail is replaced by the drawer. */}
      <div className="flex h-dvh overflow-hidden max-lg:fixed max-lg:inset-x-0 max-lg:top-[var(--vv-top,0px)] max-lg:h-[var(--vvh,100dvh)] max-lg:pt-[env(safe-area-inset-top)]">
        <AppSidebar />
        <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
          {!hideMobileTopBar && <MobileTopBar />}
          <SetupBanner />
          {children}
        </main>
      </div>
      <MobileNavDrawer open={navOpen} onOpenChange={setNavOpen} />
    </MobileNavContext.Provider>
  )
}
