'use client'

import { useEffect } from 'react'

/**
 * Mobile keyboard support (M1). Below 1024px, mirrors the visual viewport into
 * two CSS variables on <html>:
 *   --vvh     visual viewport height (shrinks while the software keyboard is open)
 *   --vv-top  visual viewport offset (iOS scrolls the layout viewport on focus)
 * The mobile app shell sizes itself with `var(--vvh, 100dvh)` so the composer
 * and send button stay above the keyboard. At lg+ the variables are removed and
 * nothing reads them, so desktop layout is untouched.
 */
export function useVisualViewportVars() {
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return

    const root = document.documentElement
    const desktop = window.matchMedia('(min-width: 1024px)')

    const clear = () => {
      root.style.removeProperty('--vvh')
      root.style.removeProperty('--vv-top')
    }

    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (desktop.matches) {
          clear()
          return
        }
        root.style.setProperty('--vvh', `${Math.round(vv.height)}px`)
        root.style.setProperty('--vv-top', `${Math.round(vv.offsetTop)}px`)
      })
    }

    update()
    vv.addEventListener('resize', update)
    vv.addEventListener('scroll', update)
    desktop.addEventListener('change', update)
    return () => {
      cancelAnimationFrame(frame)
      vv.removeEventListener('resize', update)
      vv.removeEventListener('scroll', update)
      desktop.removeEventListener('change', update)
      clear()
    }
  }, [])
}
