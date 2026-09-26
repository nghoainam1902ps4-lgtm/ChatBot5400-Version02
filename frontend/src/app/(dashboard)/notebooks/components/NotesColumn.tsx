'use client'

import { useState, useMemo } from 'react'
import { NoteResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Plus, StickyNote, Bot, User, MoreVertical, Trash2, ListChecks, ChevronDown } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/badge'
import { NoteEditorDialog } from './NoteEditorDialog'
import { getDateLocale } from '@/lib/utils/date-locale'
import { formatDistanceToNow } from 'date-fns'
import { ContextToggle } from '@/components/common/ContextToggle'
import type { NoteContextMode } from '../[id]/page'
import type { NoteContextDefault } from '@/lib/utils/source-context'
import { useDeleteNote } from '@/lib/hooks/use-notes'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotesColumnProps {
  notes?: NoteResponse[]
  isLoading: boolean
  notebookId: string
  contextSelections?: Record<string, NoteContextMode>
  onContextModeChange?: (noteId: string, mode: NoteContextMode) => void
  onBulkContextModeChange?: (action: NoteContextDefault) => void
  /** Render as a tab body inside the desktop ContextPanel: no Card shell, no
   * per-column collapse (the panel owns collapse), compact list rows. */
  embedded?: boolean
}

export function NotesColumn({
  notes,
  isLoading,
  notebookId,
  contextSelections,
  onContextModeChange,
  onBulkContextModeChange,
  embedded = false
}: NotesColumnProps) {
  const { t, language } = useTranslation()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingNote, setEditingNote] = useState<NoteResponse | undefined>()
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [noteToDelete, setNoteToDelete] = useState<string | null>(null)

  const deleteNote = useDeleteNote()

  // Collapsible column state
  const { notesCollapsed, toggleNotes } = useNotebookColumnsStore()
  const notesLabel = t('common.notes')
  const collapseButton = useMemo(
    () => createCollapseButton(toggleNotes, notesLabel),
    [toggleNotes, notesLabel]
  )

  const handleDeleteClick = (noteId: string) => {
    setNoteToDelete(noteId)
    setDeleteDialogOpen(true)
  }

  const handleOpenEditor = (note?: NoteResponse) => {
    setEditingNote(note)
    setEditorOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!noteToDelete) return

    try {
      await deleteNote.mutateAsync(noteToDelete)
      setDeleteDialogOpen(false)
      setNoteToDelete(null)
    } catch (error) {
      console.error('Failed to delete note:', error)
    }
  }

  const headerActions = (
    <>
      {onBulkContextModeChange && notes && notes.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="text-muted-foreground" title={t('sources.bulkContext')}>
              <ListChecks className="h-4 w-4" />
              <ChevronDown className="h-4 w-4 ml-1" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onBulkContextModeChange('include')}>
              {t('sources.includeAllInContext')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onBulkContextModeChange('exclude')}>
              {t('sources.excludeAllFromContext')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <Button size="sm" onClick={() => handleOpenEditor()}>
        <Plus className="h-4 w-4 mr-2" />
        {t('common.writeNote')}
      </Button>
    </>
  )

  const renderNoteToggle = (note: NoteResponse) =>
    onContextModeChange && contextSelections?.[note.id] ? (
      <div onClick={(event) => event.stopPropagation()}>
        <ContextToggle
          mode={contextSelections[note.id]}
          hasInsights={false}
          onChange={(mode) => onContextModeChange(note.id, mode)}
        />
      </div>
    ) : null

  const renderNoteMenu = (note: NoteResponse, triggerClassName: string) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={triggerClassName}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreVertical className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation()
            handleDeleteClick(note.id)
          }}
          className="text-destructive focus:text-destructive"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          {t('notebooks.deleteNote')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  const listBody = isLoading ? (
    <div className="flex items-center justify-center py-8">
      <LoadingSpinner />
    </div>
  ) : !notes || notes.length === 0 ? (
    <EmptyState
      icon={StickyNote}
      title={t('notebooks.noNotesYet')}
      description={t('sources.createFirstNote')}
    />
  ) : embedded ? (
    // Context-panel rows: same rhythm, separator and hover as SourceCard's row variant.
    <div>
      {notes.map((note) => (
        <div
          key={note.id}
          className="group relative flex items-start gap-2.5 border-b border-border/70 px-2 py-2.5 last:border-b-0 cursor-pointer transition-colors duration-150 hover:bg-accent/40"
          onClick={() => handleOpenEditor(note)}
        >
          <span
            aria-hidden
            className={`mt-[7px] size-2 flex-shrink-0 rounded-full ${note.note_type === 'ai' ? 'bg-type-ai' : 'bg-type-note'}`}
          />
          <div className="min-w-0 flex-1">
            <h4 className="truncate text-sm font-medium leading-snug" title={note.title || undefined}>
              {note.title || note.content}
            </h4>
            <div className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
              {note.note_type === 'ai' ? (
                <Bot className="h-3 w-3 flex-shrink-0 text-teal" />
              ) : (
                <User className="h-3 w-3 flex-shrink-0" />
              )}
              <span className="flex-shrink-0">
                {note.note_type === 'ai' ? t('common.aiGenerated') : t('common.human')}
              </span>
              <span aria-hidden>·</span>
              <span className="truncate">
                {formatDistanceToNow(new Date(note.updated), {
                  addSuffix: true,
                  locale: getDateLocale(language)
                })}
              </span>
            </div>
            {note.title && note.content && (
              <p className="mt-1 text-xs text-muted-foreground line-clamp-2 break-words">
                {note.content}
              </p>
            )}
          </div>
          <div className="flex flex-shrink-0 items-center gap-0.5">
            {renderNoteToggle(note)}
            {renderNoteMenu(note, 'h-7 w-7 p-0 text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity')}
          </div>
        </div>
      ))}
    </div>
  ) : (
    <div className="space-y-2">
      {notes.map((note) => (
        <div
          key={note.id}
          className="p-3 border rounded-md bg-card shadow-none card-hover group relative cursor-pointer"
          onClick={() => handleOpenEditor(note)}
        >
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center gap-2">
              {note.note_type === 'ai' ? (
                <Bot className="h-4 w-4 text-teal" />
              ) : (
                <User className="h-4 w-4 text-muted-foreground" />
              )}
              <Badge variant="secondary" className="text-xs">
                {note.note_type === 'ai' ? t('common.aiGenerated') : t('common.human')}
              </Badge>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {formatDistanceToNow(new Date(note.updated), { 
                  addSuffix: true,
                  locale: getDateLocale(language)
                })}
              </span>

              {/* Context toggle - only show if handler provided */}
              {renderNoteToggle(note)}

              {/* Ellipsis menu for delete action */}
              {renderNoteMenu(note, 'h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity')}
            </div>
          </div>

          {note.title && (
            <h4 className="text-sm font-medium mb-2 break-all">{note.title}</h4>
          )}

          {note.content && (
            <p className="text-sm text-muted-foreground line-clamp-3 break-all">
              {note.content}
            </p>
          )}
        </div>
      ))}
    </div>
  )

  const dialogs = (
    <>
      <NoteEditorDialog
        open={editorOpen}
        onOpenChange={(open) => {
          setEditorOpen(open)
          if (!open) {
            setEditingNote(undefined)
          }
        }}
        notebookId={notebookId}
        note={editingNote}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title={t('notebooks.deleteNote')}
        description={t('notebooks.deleteNoteConfirm')}
        confirmText={t('common.delete')}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteNote.isPending}
        confirmVariant="destructive"
      />
    </>
  )

  if (embedded) {
    return (
      <>
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex flex-shrink-0 items-center justify-end gap-2 px-3 py-2">
            {headerActions}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-3">
            {listBody}
          </div>
        </div>
        {dialogs}
      </>
    )
  }

  return (
    <>
      <CollapsibleColumn
        isCollapsed={notesCollapsed}
        onToggle={toggleNotes}
        collapsedIcon={StickyNote}
        collapsedLabel={notesLabel}
      >
        <Card className="h-full flex flex-col flex-1 overflow-hidden">
          <CardHeader className="pb-3 flex-shrink-0">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">
                <span aria-hidden className="h-3.5 w-[3px] rounded-full bg-gold" />
                {notesLabel}
              </CardTitle>
              <div className="flex items-center gap-2">
                {headerActions}
                {collapseButton}
              </div>
            </div>
          </CardHeader>

          <CardContent className="flex-1 overflow-y-auto min-h-0">
            {listBody}
          </CardContent>
        </Card>
      </CollapsibleColumn>

      {dialogs}
    </>
  )
}
