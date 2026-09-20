import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  accountApi,
  CreateUserRequest,
  UpdateUserRequest,
  usersApi,
} from '@/lib/api/users'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'

export const USER_QUERY_KEYS = {
  all: ['users'] as const,
}

export function useUsers(enabled = true) {
  return useQuery({
    queryKey: USER_QUERY_KEYS.all,
    queryFn: () => usersApi.list(),
    enabled,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateUserRequest) => usersApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast({ title: t('common.success'), description: t('users.userCreated') })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('users.saveError')),
        variant: 'destructive',
      })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateUserRequest }) =>
      usersApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast({ title: t('common.success'), description: t('users.userUpdated') })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('users.saveError')),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteUser() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast({ title: t('common.success'), description: t('users.userDeleted') })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('users.deleteError')),
        variant: 'destructive',
      })
    },
  })
}

export function useResetUserPassword() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ id, newPassword }: { id: string; newPassword: string }) =>
      usersApi.resetPassword(id, newPassword),
    onSuccess: () => {
      toast({
        title: t('common.success'),
        description: t('users.passwordResetDone'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('users.saveError')),
        variant: 'destructive',
      })
    },
  })
}

export function useChangePassword() {
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({
      currentPassword,
      newPassword,
    }: {
      currentPassword: string
      newPassword: string
    }) => accountApi.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      toast({
        title: t('common.success'),
        description: t('auth.passwordChanged'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('auth.changePassword')),
        variant: 'destructive',
      })
    },
  })
}
