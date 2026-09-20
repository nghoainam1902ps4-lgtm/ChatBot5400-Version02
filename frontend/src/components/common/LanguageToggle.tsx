'use client'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Languages } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuthStore } from '@/lib/stores/auth-store'

interface LanguageToggleProps {
  iconOnly?: boolean
}

// Language names are shown as endonyms (in their own language), independent of
// the active UI language.
const LANGUAGES: { code: string; label: string }[] = [
  { code: 'vi-VN', label: 'Tiếng Việt' },
  { code: 'en-US', label: 'English' },
]

export function LanguageToggle({ iconOnly = false }: LanguageToggleProps) {
  const { language, setLanguage, t } = useTranslation()
  const updatePreferences = useAuthStore((s) => s.updatePreferences)

  const currentLang = language || 'vi-VN'

  const handleSelect = async (code: string) => {
    await setLanguage(code)
    // Persist the choice to the user's account so it follows them.
    void updatePreferences({ language: code })
  }

  const isActive = (code: string) =>
    currentLang === code || currentLang.startsWith(code.split('-')[0])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={iconOnly ? 'ghost' : 'outline'}
          size={iconOnly ? 'icon' : 'default'}
          className={
            iconOnly
              ? 'h-9 w-full sidebar-menu-item'
              : 'w-full justify-start gap-2 sidebar-menu-item'
          }
        >
          <Languages className="h-[1.2rem] w-[1.2rem]" />
          {!iconOnly && <span>{t('common.language')}</span>}
          <span className="sr-only">{t('navigation.language')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGUAGES.map((lang) => (
          <DropdownMenuItem
            key={lang.code}
            onClick={() => handleSelect(lang.code)}
            className={isActive(lang.code) ? 'bg-accent' : ''}
          >
            <span>{lang.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
