'use client'

import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCreateNotebook, useNotebooks } from '@/lib/hooks/use-notebooks'
import { useAuth } from '@/lib/hooks/use-auth'
import { useTranslation } from '@/lib/hooks/use-translation'

const createNotebookSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
})

type CreateNotebookFormData = z.infer<typeof createNotebookSchema>

interface CreateNotebookDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Sentinel for the "no parent / top-level category" option (admins only).
const NO_PARENT = '__none__'

export function CreateNotebookDialog({ open, onOpenChange }: CreateNotebookDialogProps) {
  const { t } = useTranslation()
  const createNotebook = useCreateNotebook()
  const { isAdmin, isApprover, user } = useAuth()
  const { data: notebooks } = useNotebooks(false)

  // Approvers may only create sub-notebooks under a category they manage;
  // admins may also create top-level categories under any/no parent.
  const parentOptions = useMemo(() => {
    const categories = (notebooks ?? []).filter((nb) => !nb.parent)
    if (isAdmin) return categories
    return categories.filter((c) => (c.managers ?? []).includes(user?.id ?? ''))
  }, [notebooks, isAdmin, user?.id])

  const needsParent = isApprover && !isAdmin
  const [parentId, setParentId] = useState<string>(NO_PARENT)

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
    reset,
  } = useForm<CreateNotebookFormData>({
    resolver: zodResolver(createNotebookSchema),
    mode: 'onChange',
    defaultValues: {
      name: '',
      description: '',
    },
  })

  const closeDialog = () => onOpenChange(false)

  const onSubmit = async (data: CreateNotebookFormData) => {
    const parent = parentId && parentId !== NO_PARENT ? parentId : undefined
    await createNotebook.mutateAsync({ ...data, parent })
    closeDialog()
    reset()
    setParentId(NO_PARENT)
  }

  useEffect(() => {
    if (!open) {
      reset()
      setParentId(NO_PARENT)
    }
  }, [open, reset])

  const noManagedCategories = needsParent && parentOptions.length === 0
  const parentMissing = needsParent && (parentId === NO_PARENT || !parentId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>{t('notebooks.createNew')}</DialogTitle>
          <DialogDescription>
            {t('notebooks.createNewDesc')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
          <DialogBody className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="notebook-name">{t('common.name')} *</Label>
            <Input
              id="notebook-name"
              {...register('name')}
              placeholder={t('notebooks.namePlaceholder')}
              autoComplete="off"
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          {/* Parent category: optional for admins, required for approvers. */}
          {(isAdmin || isApprover) && (
            <div className="space-y-2">
              <Label htmlFor="notebook-parent">
                {t('notebooks.parentCategory')}
                {needsParent ? ' *' : ''}
              </Label>
              {noManagedCategories ? (
                <p className="text-sm text-muted-foreground">
                  {t('notebooks.noManagedCategories')}
                </p>
              ) : (
                <Select value={parentId} onValueChange={setParentId}>
                  <SelectTrigger id="notebook-parent">
                    <SelectValue placeholder={t('notebooks.parentCategoryPlaceholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {isAdmin && (
                      <SelectItem value={NO_PARENT}>
                        {t('notebooks.noParentOption')}
                      </SelectItem>
                    )}
                    {parentOptions.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {needsParent && (
                <p className="text-xs text-muted-foreground">
                  {t('notebooks.subNotebookHint')}
                </p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="notebook-description">{t('common.description')}</Label>
            <Textarea
              id="notebook-description"
              {...register('description')}
              placeholder={t('notebooks.descPlaceholder')}
              rows={4}
            />
          </div>

          </DialogBody>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeDialog}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={
                !isValid ||
                createNotebook.isPending ||
                noManagedCategories ||
                parentMissing
              }
            >
              {createNotebook.isPending ? t('common.creating') : t('notebooks.createNew')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
