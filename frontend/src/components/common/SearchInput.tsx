'use client'

import { useRef } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder: string
  ariaLabel: string
  clearLabel: string
  className?: string
}

/**
 * Generic search box (presentation + input interaction only): no debounce,
 * no data fetching, no domain copy — every string comes from the caller.
 * Same behaviour as SourceSearchInput: Escape clears, X clears and refocuses;
 * 44px tall below lg (with a 44px clear target), 36px from lg.
 */
export function SearchInput({ value, onChange, placeholder, ariaLabel, clearLabel, className }: SearchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const clear = () => {
    onChange('')
    inputRef.current?.focus()
  }

  return (
    <div role="search" className={cn('relative w-full min-w-0', className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        ref={inputRef}
        type="text"
        inputMode="search"
        enterKeyHint="search"
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && value) {
            e.preventDefault()
            e.stopPropagation()
            onChange('')
          }
        }}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className="h-11 pl-9 pr-11 lg:h-9 lg:pr-9"
      />
      {value && (
        <button
          type="button"
          onClick={clear}
          aria-label={clearLabel}
          title={clearLabel}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 lg:w-9"
        >
          <X className="size-4" />
        </button>
      )}
    </div>
  )
}
