'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
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
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
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
import { KeyRound, Pencil, Plus, Trash2, Users } from 'lucide-react'

export default function UsersPage() {
  const { t } = useTranslation()
  const { isAdmin, isLoading: authLoading, user: currentUser } = useAuth()
  const router = useRouter()

  const { data: users, isLoading } = useUsers(isAdmin)
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

  // Non-admins should never see this page.
  useEffect(() => {
    if (!authLoading && !isAdmin) {
      router.replace('/notebooks')
    }
  }, [authLoading, isAdmin, router])

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
    await deleteUser.mutateAsync(deleting.id)
    setDeleting(null)
  }

  if (authLoading || !isAdmin) {
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </AppShell>
    )
  }

  const canSubmit =
    username.trim().length > 0 && (editing !== null || password.length > 0)

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="p-6">
          <div className="max-w-4xl">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <Users className="h-6 w-6 text-teal" />
                <h1 className="font-display text-2xl font-bold tracking-tight">
                  {t('users.title')}
                </h1>
              </div>
              <Button onClick={openCreate} size="sm">
                <Plus className="h-4 w-4 mr-2" />
                {t('users.addUser')}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              {t('users.subtitle')}
            </p>

            {isLoading ? (
              <div className="py-12 flex justify-center">
                <LoadingSpinner />
              </div>
            ) : !users || users.length === 0 ? (
              <div className="py-12 text-center text-muted-foreground">
                {t('users.empty')}
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-left">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">
                        {t('users.username')}
                      </th>
                      <th className="px-4 py-2.5 font-medium">
                        {t('users.name')}
                      </th>
                      <th className="px-4 py-2.5 font-medium">
                        {t('users.role')}
                      </th>
                      <th className="px-4 py-2.5 font-medium text-right">
                        {t('users.actions')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-t border-border">
                        <td className="px-4 py-2.5 font-medium">{u.username}</td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {u.name || '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge
                            variant={u.role === 'admin' ? 'default' : 'secondary'}
                          >
                            {u.role === 'admin'
                              ? t('users.roleAdmin')
                              : t('users.roleUser')}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEdit(u)}
                              aria-label={t('users.editUser')}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setResetting(u)
                                setResetPw('')
                              }}
                              aria-label={t('users.resetPassword')}
                            >
                              <KeyRound className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDeleting(u)}
                              disabled={u.id === currentUser?.id}
                              aria-label={t('users.deleteUser')}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create / Edit dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing ? t('users.editUser') : t('users.addUser')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
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
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">{t('users.roleUser')}</SelectItem>
                  <SelectItem value="admin">{t('users.roleAdmin')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('users.resetPassword')}</DialogTitle>
            <DialogDescription>
              {resetting?.username}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label htmlFor="u-reset-pw">{t('users.newPassword')}</Label>
            <Input
              id="u-reset-pw"
              type="password"
              value={resetPw}
              onChange={(e) => setResetPw(e.target.value)}
            />
          </div>
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
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.confirmDeleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting?.username} — {t('users.confirmDeleteDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>
              {t('users.deleteUser')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppShell>
  )
}
