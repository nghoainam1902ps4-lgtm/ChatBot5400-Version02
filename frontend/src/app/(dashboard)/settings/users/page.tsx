'use client'

import { useMemo, useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogBody,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { PageShell } from '@/components/common/PageShell'
import { PageHeader } from '@/components/common/PageHeader'
import { Toolbar } from '@/components/common/Toolbar'
import { SearchInput } from '@/components/common/SearchInput'
import { PrimaryAction } from '@/components/common/PrimaryAction'
import {
  DataTable,
  DataTableBody,
  DataTableCell,
  DataTableHead,
  DataTableHeader,
  DataTableRow,
} from '@/components/common/DataTable'
import { DataList, DataListItem } from '@/components/common/DataList'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { AccessDenied } from '@/components/common/AccessDenied'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useAuth } from '@/lib/hooks/use-auth'
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useDeleteUser,
  useResetUserPassword,
} from '@/lib/hooks/use-users'
import type { User, UserRole } from '@/lib/types/auth'
import { KeyRound, MoreHorizontal, Pencil, Plus, SearchX, Trash2, Users } from 'lucide-react'

export default function UsersPage() {
  const { t, language } = useTranslation()
  // Access is shown in place (AccessDenied), never by redirecting.
  const { isAdmin, isLoading: authLoading, user: currentUser } = useAuth()

  const { data: users, isLoading, isError, refetch } = useUsers(isAdmin)
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()
  const deleteUser = useDeleteUser()
  const resetPassword = useResetUserPassword()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [resetting, setResetting] = useState<User | null>(null)
  const [deleting, setDeleting] = useState<User | null>(null)

  // Form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [resetPw, setResetPw] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Counts always reflect the full dataset (never the search filter).
  const totalCount = users?.length ?? 0
  const adminCount = users?.filter((u) => u.role === 'admin').length ?? 0

  // Client-side username search (GET /users already returns every account).
  const normalizedQuery = searchQuery.trim().toLowerCase()
  const filteredUsers = useMemo(
    () =>
      normalizedQuery
        ? (users ?? []).filter((u) => u.username.toLowerCase().includes(normalizedQuery))
        : users ?? [],
    [users, normalizedQuery]
  )

  const isLastAdmin = (u: User) => u.role === 'admin' && adminCount <= 1
  /** i18n key explaining why this account cannot be deleted, or null. */
  const deleteBlockReason = (u: User): string | null => {
    if (u.id === currentUser?.id) return 'users.cannotDeleteSelf'
    if (isLastAdmin(u)) return 'users.cannotRemoveLastAdmin'
    return null
  }
  // Editing the last admin: they may still be renamed, never demoted.
  const editingLastAdmin = editing !== null && isLastAdmin(editing)

  const formatCreated = (value?: string | null) => {
    if (!value) return '—'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '—'
    return new Intl.DateTimeFormat(language, { dateStyle: 'medium' }).format(date)
  }

  const openCreate = () => {
    setEditing(null)
    setUsername('')
    setPassword('')
    setName('')
    setRole('user')
    setFormOpen(true)
  }

  const openEdit = (u: User) => {
    setEditing(u)
    setUsername(u.username)
    setName(u.name ?? '')
    setRole(u.role)
    setPassword('')
    setFormOpen(true)
  }

  const submitForm = async () => {
    // Guard before the mutation: never send a payload demoting the last admin.
    if (editing && editingLastAdmin && role !== 'admin') return
    if (editing) {
      await updateUser.mutateAsync({
        id: editing.id,
        data: { username, role, name: name || null },
      })
    } else {
      await createUser.mutateAsync({
        username,
        password,
        role,
        name: name || null,
      })
    }
    setFormOpen(false)
  }

  const submitReset = async () => {
    if (!resetting) return
    await resetPassword.mutateAsync({ id: resetting.id, newPassword: resetPw })
    setResetting(null)
    setResetPw('')
  }

  const confirmDelete = async () => {
    if (!deleting) return
    // Defense in depth: self / last-admin deletion never reaches the API.
    if (deleteBlockReason(deleting)) {
      setDeleting(null)
      return
    }
    await deleteUser.mutateAsync(deleting.id)
    setDeleting(null)
  }

  const canSubmit =
    username.trim().length > 0 && (editing !== null || password.length > 0)

  const renderRoleBadge = (u: User) => (
    <Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
      {u.role === 'admin' ? t('users.roleAdmin') : t('users.roleUser')}
    </Badge>
  )

  const renderYouBadge = (u: User) =>
    u.id === currentUser?.id ? (
      <Badge variant="outline" className="shrink-0 font-normal text-muted-foreground">
        {t('users.you')}
      </Badge>
    ) : null

  const renderRowActions = (u: User) => {
    const reason = deleteBlockReason(u)
    return (
      // Non-modal: the dialogs it opens must not inherit a pointer-events lock.
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('users.actions')}
            title={t('users.actions')}
            className="size-11 sm:size-8"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => openEdit(u)}>
            <Pencil className="h-4 w-4" />
            {t('users.editUser')}
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() => {
              setResetting(u)
              setResetPw('')
            }}
          >
            <KeyRound className="h-4 w-4" />
            {t('users.resetPassword')}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            disabled={reason !== null}
            title={reason ? t(reason) : undefined}
            onSelect={() => {
              if (!reason) setDeleting(u)
            }}
            className="items-start"
          >
            <Trash2 className="mt-0.5 h-4 w-4" />
            <span className="flex flex-col">
              <span>{t('users.deleteUser')}</span>
              {/* Never silently disabled: the reason is part of the item */}
              {reason && (
                <span data-slot="delete-block-reason" className="text-xs text-muted-foreground">
                  {t(reason)}
                </span>
              )}
            </span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  const renderData = () => {
    if (isLoading) {
      return (
        <>
          <LoadingSkeleton
            variant="table"
            rows={5}
            columns={5}
            aria-label={t('common.loading')}
            className="hidden rounded-lg border sm:block"
          />
          <LoadingSkeleton variant="list" items={5} aria-label={t('common.loading')} className="sm:hidden" />
        </>
      )
    }

    if (isError) {
      return (
        <ErrorState
          title={t('users.loadErrorTitle')}
          description={t('users.loadErrorDesc')}
          onRetry={() => void refetch()}
          className="rounded-lg border"
        />
      )
    }

    if (normalizedQuery && filteredUsers.length === 0) {
      return (
        <div role="status" className="rounded-lg border">
          <EmptyState variant="search" icon={SearchX} title={t('common.noMatches')} />
        </div>
      )
    }

    if (!users || users.length === 0) {
      return (
        <EmptyState
          icon={Users}
          title={t('users.empty')}
          action={
            <Button onClick={openCreate} variant="outline" className="mt-4">
              <Plus className="h-4 w-4 mr-2" />
              {t('users.addUser')}
            </Button>
          }
        />
      )
    }

    return (
      <>
        {/* >=640px: table (page scroll, no sticky header, no row selection) */}
        <div className="hidden rounded-lg border sm:block">
          <DataTable className="table-fixed">
            <colgroup>
              <col className="w-auto" />
              <col className="w-auto" />
              <col className="w-[120px]" />
              <col className="w-[150px]" />
              <col className="w-[96px]" />
            </colgroup>
            <DataTableHeader>
              <tr>
                <DataTableHead>{t('users.username')}</DataTableHead>
                <DataTableHead>{t('users.name')}</DataTableHead>
                <DataTableHead>{t('users.role')}</DataTableHead>
                <DataTableHead>{t('common.created_label')}</DataTableHead>
                <DataTableHead className="text-right">{t('users.actions')}</DataTableHead>
              </tr>
            </DataTableHeader>
            <DataTableBody>
              {filteredUsers.map((u) => (
                <DataTableRow key={u.id} className="last:border-b-0">
                  <DataTableCell>
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-medium">{u.username}</span>
                      {renderYouBadge(u)}
                    </div>
                  </DataTableCell>
                  <DataTableCell className="truncate text-muted-foreground">{u.name || '—'}</DataTableCell>
                  <DataTableCell>{renderRoleBadge(u)}</DataTableCell>
                  <DataTableCell className="whitespace-nowrap text-muted-foreground">
                    {formatCreated(u.created)}
                  </DataTableCell>
                  <DataTableCell className="text-right">{renderRowActions(u)}</DataTableCell>
                </DataTableRow>
              ))}
            </DataTableBody>
          </DataTable>
        </div>

        {/* <640px: list (no horizontal table) */}
        <DataList className="rounded-lg border sm:hidden">
          {filteredUsers.map((u) => (
            <DataListItem
              key={u.id}
              className="px-3"
              title={
                <span className="flex min-w-0 items-center gap-2">
                  <span className="truncate">{u.username}</span>
                  {renderYouBadge(u)}
                </span>
              }
              meta={[u.name, formatCreated(u.created)].filter(Boolean).join(' · ')}
              actions={
                <>
                  {renderRoleBadge(u)}
                  {renderRowActions(u)}
                </>
              }
            />
          ))}
        </DataList>
      </>
    )
  }

  const renderBody = () => {
    if (authLoading) {
      return <LoadingSkeleton variant="table" rows={5} columns={5} aria-label={t('common.loading')} />
    }
    if (!isAdmin) {
      return <AccessDenied />
    }
    return (
      <>
        <Toolbar>
          <SearchInput
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder={t('users.searchPlaceholder')}
            ariaLabel={t('users.searchPlaceholder')}
            clearLabel={t('common.clearSearch')}
            className="flex-1 basis-60 sm:max-w-sm"
          />
          {users && (
            <div data-slot="user-counts" className="flex items-center gap-3 text-sm text-muted-foreground">
              <span
                className="inline-flex items-center gap-1.5"
                aria-label={`${t('users.title')}: ${totalCount}`}
                title={t('users.title')}
              >
                <Users aria-hidden className="h-4 w-4" />
                <span className="font-mono text-foreground">{totalCount}</span>
              </span>
              <span className="inline-flex items-center gap-1.5" aria-label={`${t('users.roleAdmin')}: ${adminCount}`}>
                {t('users.roleAdmin')}
                <span className="font-mono text-foreground">{adminCount}</span>
              </span>
            </div>
          )}
          <PrimaryAction icon={Plus} onClick={openCreate} className="sm:ml-auto">
            {t('users.addUser')}
          </PrimaryAction>
        </Toolbar>
        {renderData()}
      </>
    )
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <PageShell width="wide">
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <Users aria-hidden className="h-5 w-5 text-muted-foreground" />
                {t('users.title')}
              </span>
            }
            description={t('users.subtitle')}
          />
          {renderBody()}
        </PageShell>
      </div>

      {/* Create / Edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle>
              {editing ? t('users.editUser') : t('users.addUser')}
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="u-username">{t('users.username')}</Label>
              <Input
                id="u-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            {!editing && (
              <div className="space-y-1.5">
                <Label htmlFor="u-password">{t('users.password')}</Label>
                <Input
                  id="u-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="u-name">{t('users.name')}</Label>
              <Input
                id="u-name"
                value={name}
                placeholder={t('users.namePlaceholder')}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t('users.role')}</Label>
              <Select value={role} onValueChange={(v) => setRole(v as UserRole)}>
                <SelectTrigger aria-describedby={editingLastAdmin ? 'u-role-last-admin' : undefined}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user" disabled={editingLastAdmin}>{t('users.roleUser')}</SelectItem>
                  <SelectItem value="admin">{t('users.roleAdmin')}</SelectItem>
                </SelectContent>
              </Select>
              {editingLastAdmin && (
                <p id="u-role-last-admin" className="text-xs text-muted-foreground">
                  {t('users.cannotRemoveLastAdmin')}
                </p>
              )}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={submitForm}
              disabled={
                !canSubmit || createUser.isPending || updateUser.isPending
              }
            >
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset password dialog */}
      <Dialog
        open={resetting !== null}
        onOpenChange={(open) => !open && setResetting(null)}
      >
        <DialogContent size="md">
          <DialogHeader>
            <DialogTitle>{t('users.resetPassword')}</DialogTitle>
            <DialogDescription>
              {resetting?.username}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-1.5">
            <Label htmlFor="u-reset-pw">{t('users.newPassword')}</Label>
            <Input
              id="u-reset-pw"
              type="password"
              value={resetPw}
              onChange={(e) => setResetPw(e.target.value)}
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetting(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={submitReset}
              disabled={resetPw.length === 0 || resetPassword.isPending}
            >
              {t('users.resetPassword')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader icon={<Trash2 />}>
            <AlertDialogTitle>{t('users.confirmDeleteTitle')}</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogBody className="space-y-2">
            <AlertDialogDescription>
              {deleting?.username} — {t('users.confirmDeleteDesc')}
            </AlertDialogDescription>
          </AlertDialogBody>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              {t('users.deleteUser')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppShell>
  )
}
