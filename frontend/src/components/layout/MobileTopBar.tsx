'use client'

import Image from 'next/image'
import { Menu } from 'lucide-react'
import { useMobileNav } from './mobile-nav-context'
import { useTranslation } from '@/lib/hooks/use-translation'

/**
 * Generic M1 top bar (< 1024px) for pages without their own mobile bar:
 * hamburger + brand. Hidden from lg up, where the sidebar rail is shown.
 */
export function MobileTopBar() {
  const { t } = useTranslation()
  const { openNav } = useMobileNav()
  return (
    <div className="flex h-[52px] flex-shrink-0 items-center gap-1 border-b bg-card pl-0.5 pr-1 sm:h-14 lg:hidden">
      <button
        type="button"
        onClick={openNav}
        aria-label={t('common.openNavigation')}
        className="inline-flex size-11 flex-shrink-0 items-center justify-center rounded-md text-muted-foreground active:bg-muted"
      >
        <Menu className="size-5" />
      </button>
      <Image src="/agribank-logo.svg" alt="" width={28} height={28} className="object-contain" unoptimized />
      <span className="ml-1.5 min-w-0 truncate font-display text-[15px] font-bold text-primary">Agribank Lâm Đồng</span>
    </div>
  )
}
