'use client'

import { useState } from 'react'
import { NotebookResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Archive, ArchiveRestore, Trash2, Menu, MoreVertical } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useMobileNav } from '@/components/layout/mobile-nav-context'
import { useUpdateNotebook } from '@/lib/hooks/use-notebooks'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { formatDistanceToNow } from 'date-fns'
import { getDateLocale } from '@/lib/utils/date-locale'
import { InlineEdit } from '@/components/common/InlineEdit'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'

interface NotebookHeaderProps {
  notebook: NotebookResponse
}

export function NotebookHeader({ notebook }: NotebookHeaderProps) {
  const { t, language } = useTranslation()
  const { isAdmin } = useAuth()
  const dfLocale = getDateLocale(language)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const { openNav, setTopBarActions } = useMobileNav()
  
  const updateNotebook = useUpdateNotebook()

  const handleUpdateName = async (name: string) => {
    if (!name || name === notebook.name) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { name }
    })
  }

  const handleUpdateDescription = async (description: string) => {
    if (description === notebook.description) return
    
    await updateNotebook.mutateAsync({
      id: notebook.id,
      data: { description: description || undefined }
    })
  }

  const handleArchiveToggle = () => {
    updateNotebook.mutate({
      id: notebook.id,
      data: { archived: !notebook.archived }
    })
  }

  const createdLabel = t('common.created', { time: formatDistanceToNow(new Date(notebook.created), { addSuffix: true, locale: dfLocale }) })
  const updatedLabel = t('common.updated', { time: formatDistanceToNow(new Date(notebook.updated), { addSuffix: true, locale: dfLocale }) })

  return (
    <>
      {/* M1 (< lg): compact top bar — menu · title (one line, ellipsis) ·
          [session slot, filled by the visible chat panel] · more. Description,
          dates and Archive/Delete move into the "more" popover; tablet shows the
          updated time next to the title again. */}
      <div className="flex h-[52px] items-center gap-1 border-b bg-card pl-0.5 pr-1 sm:h-14 sm:pr-2 lg:hidden">
        <button
          type="button"
          onClick={openNav}
          aria-label={t('common.openNavigation')}
          className="inline-flex size-11 flex-shrink-0 items-center justify-center rounded-md text-muted-foreground active:bg-muted"
        >
          <Menu className="size-5" />
        </button>
        <div className="mx-1 flex min-w-0 flex-1 items-center gap-2">
          {isAdmin ? (
            <InlineEdit
              id="notebook-name-mobile"
              name="notebook-name-mobile"
              value={notebook.name}
              onSave={handleUpdateName}
              className="mx-0 min-w-0 truncate whitespace-nowrap break-normal font-display text-[15.5px] font-semibold leading-5 tracking-[-0.01em] sm:text-[17px]"
              inputClassName="font-display text-[16px] font-semibold"
              placeholder={t('notebooks.namePlaceholder')}
            />
          ) : (
            <h1 className="min-w-0 truncate font-display text-[15.5px] font-semibold leading-5 tracking-[-0.01em] sm:text-[17px]">
              {notebook.name}
            </h1>
          )}
          {notebook.archived && (
            <Badge variant="secondary" className="flex-shrink-0">{t('notebooks.archived')}</Badge>
          )}
        </div>
        <span className="mr-1 hidden flex-shrink-0 whitespace-nowrap text-xs text-muted-foreground sm:inline">
          {updatedLabel}
        </span>
        <div ref={setTopBarActions} className="flex flex-shrink-0 items-center" />
        <Popover open={moreOpen} onOpenChange={setMoreOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={t('common.moreOptions')}
              className="inline-flex size-11 flex-shrink-0 items-center justify-center rounded-md text-muted-foreground active:bg-muted"
            >
              <MoreVertical className="size-5" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-[min(320px,calc(100vw-24px))] space-y-3 p-3">
            {(isAdmin || notebook.description) && (
              isAdmin ? (
                <InlineEdit
                  id="notebook-description-mobile"
                  name="notebook-description-mobile"
                  value={notebook.description || ''}
                  onSave={handleUpdateDescription}
                  className="break-normal break-words text-sm text-muted-foreground"
                  inputClassName="text-base text-muted-foreground"
                  placeholder={t('notebooks.addDescription')}
                  multiline
                  emptyText={t('notebooks.addDescription')}
                />
              ) : (
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{notebook.description}</p>
              )
            )}
            <div className="space-y-0.5 text-xs text-muted-foreground">
              <p>{createdLabel}</p>
              <p>{updatedLabel}</p>
            </div>
            {isAdmin && (
              <div className="flex gap-2 border-t pt-3">
                <Button
                  variant="outline"
                  className="h-11 flex-1"
                  onClick={() => {
                    setMoreOpen(false)
                    handleArchiveToggle()
                  }}
                >
                  {notebook.archived ? (
                    <>
                      <ArchiveRestore className="h-4 w-4 mr-2" />
                      {t('notebooks.unarchive')}
                    </>
                  ) : (
                    <>
                      <Archive className="h-4 w-4 mr-2" />
                      {t('notebooks.archive')}
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  className="h-11 flex-1 text-destructive hover:text-destructive"
                  onClick={() => {
                    setMoreOpen(false)
                    setShowDeleteDialog(true)
                  }}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('common.delete')}
                </Button>
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>

      {/* Below lg: the original stacked header. From lg up (design B): one
          56px top bar — name · description · dates … Archive / Delete. The
          same elements are reflowed with responsive classes (no duplicate
          InlineEdit instances), so every edit affordance stays available. */}
      <div className="border-b pb-6 max-lg:hidden lg:pb-0">
        <div className="space-y-2 lg:flex lg:min-h-14 lg:items-center lg:gap-4 lg:space-y-0 lg:px-6 lg:py-2">
          <div className="flex items-center justify-between lg:contents">
            <div className="flex items-center gap-3 flex-1 lg:max-w-[40%] lg:flex-none lg:min-w-0">
              {isAdmin ? (
                <InlineEdit
                  id="notebook-name"
                  name="notebook-name"
                  value={notebook.name}
                  onSave={handleUpdateName}
                  className="font-display text-2xl font-bold tracking-tight lg:mx-0 lg:truncate lg:text-lg"
                  inputClassName="font-display text-2xl font-bold tracking-tight lg:text-lg"
                  placeholder={t('notebooks.namePlaceholder')}
                />
              ) : (
                <h1 className="font-display text-2xl font-bold tracking-tight lg:truncate lg:text-lg">
                  {notebook.name}
                </h1>
              )}
              {notebook.archived && (
                <Badge variant="secondary">{t('notebooks.archived')}</Badge>
              )}
            </div>
            {isAdmin && (
              <div className="flex gap-2 lg:order-last lg:flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleArchiveToggle}
                >
                  {notebook.archived ? (
                    <>
                      <ArchiveRestore className="h-4 w-4 mr-2" />
                      {t('notebooks.unarchive')}
                    </>
                  ) : (
                    <>
                      <Archive className="h-4 w-4 mr-2" />
                      {t('notebooks.archive')}
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDeleteDialog(true)}
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('common.delete')}
                </Button>
              </div>
            )}
          </div>

          {/* Signature: one short flat fern underline — one hue, no show */}
          <div aria-hidden className="h-[3px] w-14 rounded-[1px] bg-fern lg:hidden" />

          {(isAdmin || notebook.description) && (
            <div className="lg:min-w-0 lg:flex-1">
              {isAdmin ? (
                <InlineEdit
                  id="notebook-description"
                  name="notebook-description"
                  value={notebook.description || ''}
                  onSave={handleUpdateDescription}
                  className="text-muted-foreground lg:truncate lg:text-sm"
                  inputClassName="text-muted-foreground"
                  placeholder={t('notebooks.addDescription')}
                  multiline
                  emptyText={t('notebooks.addDescription')}
                />
              ) : (
                <p className="text-muted-foreground whitespace-pre-wrap lg:truncate lg:whitespace-nowrap lg:text-sm">
                  {notebook.description}
                </p>
              )}
            </div>
          )}
          {/* Keeps the bar's actions right-aligned when there is no description. */}
          {!isAdmin && !notebook.description && <div aria-hidden className="hidden lg:block lg:flex-1" />}

          <div className="text-xs text-muted-foreground lg:hidden xl:block xl:flex-shrink-0 xl:whitespace-nowrap">
            {createdLabel} • 
            {updatedLabel}
          </div>
        </div>
      </div>

      <NotebookDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        notebookId={notebook.id}
        notebookName={notebook.name}
        redirectAfterDelete
      />
    </>
  )
}