'use client'

import { useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronDown, ChevronRight, Trash2, Wand2, Edit, MoreHorizontal } from 'lucide-react'
import { Transformation } from '@/lib/types/transformations'
import { useDeleteTransformation } from '@/lib/hooks/use-transformations'
import { useTranslation } from '@/lib/hooks/use-translation'

interface TransformationCardProps {
  transformation: Transformation
  onPlayground?: () => void
  onEdit?: () => void
}

export function TransformationCard({ transformation, onPlayground, onEdit }: TransformationCardProps) {
  const { t } = useTranslation()
  const [isExpanded, setIsExpanded] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const deleteTransformation = useDeleteTransformation()

  const handleDelete = () => {
    deleteTransformation.mutate(transformation.id)
    setShowDeleteDialog(false)
  }

  return (
    <>
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <CollapsibleTrigger className="flex-1 text-left">
                <div className="flex items-center gap-3">
                  {isExpanded ? (
                    <ChevronDown className="size-[15px] shrink-0" />
                  ) : (
                    <ChevronRight className="size-[15px] shrink-0" />
                  )}
                  <div className="flex flex-col">
                    <span className="font-semibold">{transformation.name}</span>
                    {/* Description stays in the header in both states (no jump) */}
                    {transformation.description && (
                      <span className="text-sm text-muted-foreground">{transformation.description}</span>
                    )}
                  </div>
                  {transformation.apply_default && (
                    <Badge variant="secondary">{t('common.default')}</Badge>
                  )}
                </div>
              </CollapsibleTrigger>

              <div className="flex items-center gap-2">
                {onPlayground && (
                  <Button variant="outline" size="sm" onClick={onPlayground}>
                    <Wand2 className="h-4 w-4 mr-2" />
                    {t('transformations.playground')}
                  </Button>
                )}
                {/* Edit / Delete in the "..." menu; same editor and confirm flows.
                    Non-modal so the dialogs it opens never inherit a pointer-events lock. */}
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" aria-label={t('common.actions')} title={t('common.actions')}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {onEdit && (
                      <DropdownMenuItem onSelect={onEdit}>
                        <Edit className="h-4 w-4" />
                        {t('common.edit')}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem variant="destructive" onSelect={() => setShowDeleteDialog(true)}>
                      <Trash2 className="h-4 w-4" />
                      {t('common.delete')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </CardHeader>

          <CollapsibleContent>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">{t('common.title')}</p>
                <p className="text-sm font-medium">{transformation.title || t('sources.untitledSource')}</p>
              </div>

              <div>
                <p className="text-sm text-muted-foreground">{t('transformations.systemPrompt')}</p>
                <pre className="mt-2 max-h-[40vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm font-mono">
                  {transformation.prompt}
                </pre>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>

      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title={t('transformations.deleteTitle')}
        description={t('transformations.deleteConfirm')}
        confirmText={t('common.delete')}
        confirmVariant="destructive"
        onConfirm={handleDelete}
        isLoading={deleteTransformation.isPending}
      />
    </>
  )
}
