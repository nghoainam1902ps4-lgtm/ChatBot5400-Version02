'use client'

import { memo, useCallback, useState, useRef, useEffect, useId, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Bot, User, Send, Loader2, FileText, Lightbulb, StickyNote, Clock, BookOpen } from 'lucide-react'
import { MarkdownRenderer } from '@/components/ui/markdown-renderer'
import {
  SourceChatMessage,
  SourceChatContextIndicator,
  BaseChatSession
} from '@/lib/types/api'
import { ModelSelector } from './ModelSelector'
import { ContextIndicator } from '@/components/common/ContextIndicator'
import { SessionManager } from '@/components/sources/SessionManager'
import { MessageActions } from '@/components/sources/MessageActions'
import { convertReferencesToCompactMarkdown, createCompactReferenceLinkComponent } from '@/lib/utils/source-references'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface NotebookContextStats {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
}

interface ChatPanelProps {
  messages: SourceChatMessage[]
  isStreaming: boolean
  contextIndicators: SourceChatContextIndicator | null
  onSendMessage: (message: string, modelOverride?: string) => void
  modelOverride?: string
  onModelChange?: (model?: string) => void
  // Session management props
  sessions?: BaseChatSession[]
  currentSessionId?: string | null
  onCreateSession?: (title: string) => void
  onSelectSession?: (sessionId: string) => void
  onDeleteSession?: (sessionId: string) => void
  onUpdateSession?: (sessionId: string, title: string) => void
  loadingSessions?: boolean
  // Generic props for reusability
  title?: string
  contextType?: 'source' | 'notebook'
  // Notebook context stats (for notebook chat)
  notebookContextStats?: NotebookContextStats
  // Notebook ID for saving notes
  notebookId?: string
}

export function ChatPanel({
  messages,
  isStreaming,
  contextIndicators,
  onSendMessage,
  modelOverride,
  onModelChange,
  sessions = [],
  currentSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onUpdateSession,
  loadingSessions = false,
  title,
  contextType = 'source',
  notebookContextStats,
  notebookId
}: ChatPanelProps) {
  const { t } = useTranslation()
  const [sessionManagerOpen, setSessionManagerOpen] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { openModal } = useModalManager()

  // Stable reference-click handler so memoized messages don't re-render on
  // composer keystrokes (which no longer re-render this component at all, since
  // the input state lives in the ChatComposer child).
  const handleReferenceClick = useCallback((type: string, id: string) => {
    const modalType = type === 'source_insight' ? 'insight' : type as 'source' | 'note' | 'insight'

    try {
      openModal(modalType, id)
      // Note: The modal system uses URL parameters and doesn't throw errors for missing items.
      // The modal component itself will handle displaying "not found" states.
      // This try-catch is here for future enhancements or unexpected errors.
    } catch {
      toast.error(t('common.noResults'))
    }
  }, [openModal, t])

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Context chip(s) rendered inside the composer: source-chat indicators or
  // the notebook context summary. Same data and conditions as before.
  const contextChip = (
    <>
      {contextIndicators && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {contextIndicators.sources?.length > 0 && (
            <Badge variant="outline" className="gap-1">
              <FileText className="h-3 w-3" />
              {contextIndicators.sources.length} {t('navigation.sources')}
            </Badge>
          )}
          {contextIndicators.insights?.length > 0 && (
            <Badge variant="outline" className="gap-1">
              <Lightbulb className="h-3 w-3" />
              {contextIndicators.insights.length} {contextIndicators.insights.length === 1 ? t('common.insight') : t('common.insights')}
            </Badge>
          )}
          {contextIndicators.notes?.length > 0 && (
            <Badge variant="outline" className="gap-1">
              <StickyNote className="h-3 w-3" />
              {contextIndicators.notes.length} {contextIndicators.notes.length === 1 ? t('common.note') : t('common.notes')}
            </Badge>
          )}
        </div>
      )}
      {notebookContextStats && (
        <ContextIndicator
          sourcesInsights={notebookContextStats.sourcesInsights}
          sourcesFull={notebookContextStats.sourcesFull}
          notesCount={notebookContextStats.notesCount}
          tokenCount={notebookContextStats.tokenCount}
          charCount={notebookContextStats.charCount}
          className="min-w-0 shrink flex-wrap gap-y-1 border-t-0 bg-transparent px-1 py-0 [&_div]:flex-wrap"
        />
      )}
    </>
  )

  return (
    <>
    {/* Flat chat surface (design B). Below lg the original card frame is kept. */}
    <section
      className={cn(
        'flex flex-col h-full flex-1 overflow-hidden',
        'max-lg:bg-card max-lg:text-card-foreground max-lg:rounded-lg max-lg:border max-lg:gap-6 max-lg:py-6'
      )}
    >
      <div className="flex-shrink-0 pb-3 px-6 lg:flex lg:h-12 lg:items-center lg:border-b lg:pb-0">
        <div className="flex flex-1 items-center justify-between">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.13em] text-muted-foreground">
            <span aria-hidden className="h-3.5 w-[3px] rounded-full bg-teal" />
            {title || (contextType === 'source' ? t('chat.chatWith', { name: t('navigation.sources') }) : t('chat.chatWith', { name: t('common.notebook') }))}
          </h2>
          {onSelectSession && onCreateSession && onDeleteSession && (
            <Dialog open={sessionManagerOpen} onOpenChange={setSessionManagerOpen}>
              <Button
                variant="ghost"
                size="sm"
                className="gap-2 text-muted-foreground"
                onClick={() => setSessionManagerOpen(true)}
                disabled={loadingSessions}
              >
                <Clock className="h-4 w-4" />
                <span className="text-xs">{t('chat.sessions')}</span>
              </Button>
              <DialogContent className="sm:max-w-[420px] p-0 overflow-hidden">
                <DialogTitle className="sr-only">{t('chat.sessionsTitle')}</DialogTitle>
                <SessionManager
                  sessions={sessions}
                  currentSessionId={currentSessionId ?? null}
                  onCreateSession={(title) => onCreateSession?.(title)}
                  onSelectSession={(sessionId) => {
                    onSelectSession(sessionId)
                    setSessionManagerOpen(false)
                  }}
                  onUpdateSession={(sessionId, title) => onUpdateSession?.(sessionId, title)}
                  onDeleteSession={(sessionId) => onDeleteSession?.(sessionId)}
                  loadingSessions={loadingSessions}
                />
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>
      <div className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 min-h-0" ref={scrollAreaRef}>
          {/* Centered reading column */}
          <div className="mx-auto w-full max-w-[760px] space-y-6 px-4 py-4 lg:px-6 lg:py-8">
            {messages.length === 0 ? (
              <div className="text-center text-muted-foreground py-8 lg:py-16">
                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-sm">
                  {t('chat.startConversation', { type: contextType === 'source' ? t('navigation.sources') : t('common.notebook') })}
                </p>
                <p className="text-xs mt-2">{t('chat.askQuestions')}</p>
              </div>
            ) : (
              messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  notebookId={notebookId}
                  onReferenceClick={handleReferenceClick}
                />
              ))
            )}
            {isStreaming && (
              <div className="flex gap-3 justify-start">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-teal-tint flex items-center justify-center">
                    <Bot className="h-4 w-4 text-teal" />
                  </div>
                </div>
                <div className="flex items-center py-2">
                  <Loader2 className="h-4 w-4 animate-spin text-teal" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Area */}
        <ChatComposer
          onSendMessage={onSendMessage}
          isStreaming={isStreaming}
          modelOverride={modelOverride}
          onModelChange={onModelChange}
          contextChip={(contextIndicators || notebookContextStats) ? contextChip : null}
        />
      </div>
    </section>

    </>
  )
}

// Composer owns the input state so keystrokes (including IME composition) only
// re-render this small component instead of the whole message history.
interface ChatComposerProps {
  onSendMessage: (message: string, modelOverride?: string) => void
  isStreaming: boolean
  modelOverride?: string
  onModelChange?: (model?: string) => void
  contextChip?: ReactNode
}

function ChatComposer({
  onSendMessage,
  isStreaming,
  modelOverride,
  onModelChange,
  contextChip
}: ChatComposerProps) {
  const { t } = useTranslation()
  const chatInputId = useId()
  const [input, setInput] = useState('')

  const handleSend = () => {
    if (input.trim() && !isStreaming) {
      onSendMessage(input.trim(), modelOverride)
      setInput('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Detect platform for correct modifier key
    const isMac = typeof navigator !== 'undefined' && navigator.userAgent.toUpperCase().indexOf('MAC') >= 0
    const isModifierPressed = isMac ? e.metaKey : e.ctrlKey

    if (e.key === 'Enter' && isModifierPressed) {
      e.preventDefault()
      handleSend()
    }
  }

  // Detect platform for placeholder text
  const isMac = typeof navigator !== 'undefined' && navigator.userAgent.toUpperCase().indexOf('MAC') >= 0
  const keyHint = isMac ? '⌘+Enter' : 'Ctrl+Enter'

  return (
    <div className="flex-shrink-0 border-t px-4 pb-4 pt-3 lg:border-t-0 lg:px-6 lg:pb-6 lg:pt-2">
      <div className="mx-auto w-full max-w-[760px]">
        <div className="rounded-2xl border bg-card shadow-sm transition-shadow focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
          <Textarea
            id={chatInputId}
            name="chat-message"
            autoComplete="off"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`${t('chat.sendPlaceholder')} (${t('chat.pressToSend', { key: keyHint })})`}
            disabled={isStreaming}
            className="min-h-[52px] max-h-[160px] w-full min-w-0 resize-none border-0 bg-transparent px-4 pt-3 pb-1 shadow-none focus-visible:ring-0 dark:bg-transparent"
            rows={1}
          />
          <div className="flex items-end justify-between gap-2 px-2 pb-2">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
              {/* Model chip */}
              {onModelChange && (
                <div className="flex flex-shrink-0 items-center" title={t('chat.model')}>
                  <span className="sr-only">{t('chat.model')}</span>
                  <ModelSelector
                    currentModel={modelOverride}
                    onModelChange={onModelChange}
                    disabled={isStreaming}
                  />
                </div>
              )}
              {/* Context chip */}
              {contextChip}
            </div>
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              size="icon"
              className="h-9 w-9 flex-shrink-0 rounded-full"
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Single chat message row. Memoized so historical messages don't re-render when
// unrelated state (e.g. the composer input) changes.
interface ChatMessageProps {
  message: SourceChatMessage
  notebookId?: string
  onReferenceClick: (type: string, id: string) => void
}

const ChatMessage = memo(function ChatMessage({
  message,
  notebookId,
  onReferenceClick
}: ChatMessageProps) {
  if (message.type === 'ai') {
    // AI answer: no bubble, full width of the reading column.
    return (
      <div className="flex gap-3 justify-start">
        <div className="flex-shrink-0">
          <div className="h-8 w-8 rounded-full bg-teal-tint flex items-center justify-center">
            <Bot className="h-4 w-4 text-teal" />
          </div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2 pt-0.5">
          <AIMessageContent
            content={message.content}
            onReferenceClick={onReferenceClick}
          />
          <MessageActions
            content={message.content}
            notebookId={notebookId}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 justify-end">
      <div className="flex flex-col gap-2 max-w-[80%]">
        <div className="rounded-2xl px-4 py-2.5 bg-muted">
          <p className="text-sm break-all">{message.content}</p>
        </div>
      </div>
      <div className="flex-shrink-0">
        <div className="h-8 w-8 rounded-full bg-muted border flex items-center justify-center">
          <User className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
    </div>
  )
})

// Helper component to render AI messages with clickable references
function AIMessageContent({
  content,
  onReferenceClick
}: {
  content: string
  onReferenceClick: (type: string, id: string) => void
}) {
  const { t } = useTranslation()
  // Convert references to compact markdown with numbered citations
  const referencesLabel = t('common.references')
  const markdownWithCompactRefs = convertReferencesToCompactMarkdown(content, referencesLabel)

  // Create custom link component for compact references
  const LinkComponent = createCompactReferenceLinkComponent(onReferenceClick)

  // Presentation only: the reference list that convertReferencesToCompactMarkdown
  // appended ("\n\n<label>:" + one line per reference) is shown in its own
  // "Nguồn dẫn" block instead of inline. Nothing is re-parsed — the output is
  // split at the marker the converter itself wrote. When the converter found no
  // references it returns the content unchanged, so nothing is split.
  const marker = `\n\n${referencesLabel}:`
  const markerIndex = markdownWithCompactRefs !== content ? markdownWithCompactRefs.lastIndexOf(marker) : -1
  const body = markerIndex >= 0 ? markdownWithCompactRefs.slice(0, markerIndex) : markdownWithCompactRefs
  const referenceLines = markerIndex >= 0
    ? markdownWithCompactRefs.slice(markerIndex + marker.length).split('\n').filter(line => line.trim())
    : []

  return (
    <>
      <MarkdownRenderer components={{
        a: LinkComponent
      }}>
        {body}
      </MarkdownRenderer>
      {referenceLines.length > 0 && (
        <SourceCitations lines={referenceLines} linkComponent={LinkComponent} />
      )}
    </>
  )
}

// "Nguồn dẫn" block: renders the reference lines produced above, with the same
// clickable link component used for the inline [n] chips.
function SourceCitations({
  lines,
  linkComponent
}: {
  lines: string[]
  linkComponent: ReturnType<typeof createCompactReferenceLinkComponent>
}) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border bg-muted/30 px-4 py-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        <span className="inline-flex items-center gap-1.5 font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          <BookOpen className="h-3.5 w-3.5" />
          {t('chat.citationsTitle')}
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">{t('chat.answeredFromCount', { count: lines.length })}</span>
      </div>
      <ol className="space-y-1 [&_.prose]:!text-sm [&_p]:!my-0 [&_p]:!leading-6">
        {lines.map((line, index) => (
          <li key={index}>
            <MarkdownRenderer components={{
              a: linkComponent,
              p: ({ children }) => <p className="my-0">{children}</p>
            }}>
              {line}
            </MarkdownRenderer>
          </li>
        ))}
      </ol>
    </div>
  )
}
