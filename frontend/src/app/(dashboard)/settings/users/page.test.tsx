import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UsersPage from './page'
import { useAuth } from '@/lib/hooks/use-auth'
import { useUsers } from '@/lib/hooks/use-users'
import type { User } from '@/lib/types/auth'

// useTranslation is mocked globally in setup.ts (t returns the key string)

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/settings/users',
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const updateMutate = vi.fn()
const deleteMutate = vi.fn()
const createMutate = vi.fn()
const resetMutate = vi.fn()
vi.mock('@/lib/hooks/use-users', () => ({
  useUsers: vi.fn(),
  useCreateUser: () => ({ mutateAsync: createMutate, isPending: false }),
  useUpdateUser: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteUser: () => ({ mutateAsync: deleteMutate, isPending: false }),
  useResetUserPassword: () => ({ mutateAsync: resetMutate, isPending: false }),
}))

const u = (id: string, username: string, role: 'admin' | 'user', extra: Partial<User> = {}): User => ({
  id,
  username,
  role,
  name: null,
  created: '2026-03-15T08:00:00Z',
  ...extra,
})

const ALICE = u('user:alice', 'alice', 'admin', { name: 'Alice Nguyễn' })
const BOB = u('user:bob', 'Bob.Tran', 'user', { name: 'Admin Helper' })
const CAROL = u('user:carol', 'carol', 'user', { created: null })

const refetch = vi.fn()
function setup(users: User[] | undefined, query: Partial<ReturnType<typeof useUsers>> = {}, me: User = ALICE) {
  vi.mocked(useAuth).mockReturnValue({ isAdmin: true, isLoading: false, user: me } as unknown as ReturnType<typeof useAuth>)
  vi.mocked(useUsers).mockReturnValue({
    data: users,
    isLoading: false,
    isError: false,
    refetch,
    ...query,
  } as unknown as ReturnType<typeof useUsers>)
  return render(<UsersPage />)
}

const header = () => screen.getByRole('heading', { level: 1, name: /users\.title/ })
const tableRows = () => Array.from(document.querySelectorAll('[data-slot="data-table-row"]')) as HTMLElement[]
const rowOf = (username: string) => tableRows().find((r) => r.textContent?.includes(username)) as HTMLElement
const searchBox = () => screen.getByRole('textbox', { name: 'users.searchPlaceholder' })
const rowNames = () => tableRows().map((r) => r.querySelector('td span.truncate')?.textContent)

function openRowMenu(row: HTMLElement) {
  fireEvent.keyDown(within(row).getByRole('button', { name: 'users.actions' }), { key: 'Enter' })
  return screen.getByRole('menu')
}

describe('UsersPage (P1C) — access', () => {
  beforeEach(() => vi.clearAllMocks())

  it('auth loading: header + skeleton, no toolbar', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: true, user: null } as unknown as ReturnType<typeof useAuth>)
    vi.mocked(useUsers).mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof useUsers>)
    render(<UsersPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"]')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeNull()
  })

  it('non-admin: header + AccessDenied, no redirect', () => {
    vi.mocked(useAuth).mockReturnValue({ isAdmin: false, isLoading: false, user: BOB } as unknown as ReturnType<typeof useAuth>)
    vi.mocked(useUsers).mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof useUsers>)
    render(<UsersPage />)
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="access-denied"]')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('admin: wide PageShell, header (neutral icon), toolbar with search, counts and Add User', () => {
    setup([ALICE, BOB, CAROL])
    expect(document.querySelector('[data-slot="page-shell"]')).toHaveAttribute('data-width', 'wide')
    expect(header().querySelector('svg')?.getAttribute('class')).toContain('text-muted-foreground')
    expect(header().querySelector('svg')?.getAttribute('class')).not.toContain('text-teal')
    const toolbar = document.querySelector('[data-slot="toolbar"]') as HTMLElement
    expect(within(toolbar).getByRole('search')).toBeInTheDocument()
    expect(within(toolbar).getByRole('button', { name: /users\.addUser/ })).toBeInTheDocument()
    expect(within(toolbar).getByLabelText('users.title: 3')).toBeInTheDocument()
    expect(within(toolbar).getByLabelText('users.roleAdmin: 1')).toBeInTheDocument()
    // Add User is not in the header
    expect(within(document.querySelector('[data-slot="page-header"]') as HTMLElement).queryByRole('button')).toBeNull()
  })
})

describe('UsersPage (P1C) — data states', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loading: table + list skeletons, header + toolbar kept', () => {
    setup(undefined, { isLoading: true })
    expect(header()).toBeInTheDocument()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"][data-variant="table"]')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="loading-skeleton"][data-variant="list"]')).toBeInTheDocument()
  })

  it('error: ErrorState with real retry (not the empty state); header + toolbar kept', () => {
    setup(undefined, { isError: true })
    const state = document.querySelector('[data-slot="error-state"]') as HTMLElement
    expect(within(state).getByText('users.loadErrorTitle')).toBeInTheDocument()
    expect(within(state).getByText('users.loadErrorDesc')).toBeInTheDocument()
    expect(screen.queryByText('users.empty')).toBeNull()
    expect(document.querySelector('[data-slot="toolbar"]')).toBeInTheDocument()
    fireEvent.click(within(state).getByRole('button', { name: 'common.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('actual empty: Users icon, users.empty and an Add User CTA', () => {
    setup([])
    const empty = document.querySelector('[data-slot="empty-state"]') as HTMLElement
    expect(empty).toHaveAttribute('data-variant', 'empty')
    expect(within(empty).getByText('users.empty')).toBeInTheDocument()
    expect(empty.querySelector('.lucide-users')).not.toBeNull()
    expect(within(empty).getByRole('button', { name: /users\.addUser/ })).toBeInTheDocument()
  })
})

describe('UsersPage (P1C) — search', () => {
  beforeEach(() => vi.clearAllMocks())

  it('matches username only, case-insensitively', () => {
    setup([ALICE, BOB, CAROL])
    fireEvent.change(searchBox(), { target: { value: 'BOB' } })
    expect(rowNames()).toEqual(['Bob.Tran'])
  })

  it('does not match on display name or role', () => {
    setup([ALICE, BOB, CAROL])
    fireEvent.change(searchBox(), { target: { value: 'Nguyễn' } })
    expect(rowNames()).toEqual([])
    fireEvent.change(searchBox(), { target: { value: 'admin' } })
    expect(rowNames()).toEqual([])
  })

  it('no result: search EmptyState (common.noMatches), no Add User CTA; counts stay on the full dataset', () => {
    setup([ALICE, BOB, CAROL])
    fireEvent.change(searchBox(), { target: { value: 'zzz' } })
    const empty = document.querySelector('[data-slot="empty-state"]') as HTMLElement
    expect(empty).toHaveAttribute('data-variant', 'search')
    expect(within(empty).getByText('common.noMatches')).toBeInTheDocument()
    expect(within(empty).queryByRole('button')).toBeNull()
    expect(screen.getByLabelText('users.title: 3')).toBeInTheDocument()
    expect(screen.getByLabelText('users.roleAdmin: 1')).toBeInTheDocument()
  })

  it('X and Escape clear back to the full list immediately', () => {
    setup([ALICE, BOB, CAROL])
    fireEvent.change(searchBox(), { target: { value: 'carol' } })
    expect(rowNames()).toEqual(['carol'])
    fireEvent.click(screen.getByRole('button', { name: 'common.clearSearch' }))
    expect(rowNames()).toEqual(['alice', 'Bob.Tran', 'carol'])

    fireEvent.change(searchBox(), { target: { value: 'carol' } })
    fireEvent.keyDown(searchBox(), { key: 'Escape' })
    expect(searchBox()).toHaveValue('')
    expect(rowNames()).toEqual(['alice', 'Bob.Tran', 'carol'])
  })
})

describe('UsersPage (P1C) — table / list', () => {
  beforeEach(() => vi.clearAllMocks())

  it('five columns in order, created date formatted for the active locale, null created → —', () => {
    setup([ALICE, BOB, CAROL])
    const heads = Array.from(document.querySelectorAll('[data-slot="data-table-head"]')).map((h) => h.textContent)
    expect(heads).toEqual(['users.username', 'users.name', 'users.role', 'common.created_label', 'users.actions'])
    const expected = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(new Date(ALICE.created as string))
    expect(within(rowOf('alice')).getByText(expected)).toBeInTheDocument()
    expect(within(rowOf('carol')).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('rows have default/hover only (no selected state, no row navigation)', () => {
    setup([ALICE, BOB])
    for (const row of tableRows()) {
      expect(row).not.toHaveAttribute('data-selected')
      expect(row).not.toHaveAttribute('tabindex')
      expect(row.className).toContain('hover:bg-muted')
    }
    expect(document.querySelector('[data-slot="data-table"]')).not.toHaveAttribute('tabindex')
  })

  it('role badge: admin stays default/primary, user secondary', () => {
    setup([ALICE, BOB])
    const adminBadge = within(rowOf('alice')).getByText('users.roleAdmin')
    const userBadge = within(rowOf('Bob.Tran')).getByText('users.roleUser')
    expect(adminBadge.className).toContain('text-primary')
    expect(adminBadge.className).not.toMatch(/success|teal/)
    expect(userBadge.className).toContain('text-muted-foreground')
  })

  it('mobile list: DataList hidden from sm, table hidden below sm, 44px action targets', () => {
    setup([ALICE, BOB])
    const list = document.querySelector('[data-slot="data-list"]') as HTMLElement
    expect(list.className).toContain('sm:hidden')
    expect((document.querySelector('[data-slot="data-table"]')?.parentElement as HTMLElement).className).toMatch(/(^| )hidden( |$)/)
    const trigger = within(list).getAllByRole('button', { name: 'users.actions' })[0]
    expect(trigger.className).toContain('size-11')
    expect(within(list).getByText('Alice Nguyễn', { exact: false })).toBeInTheDocument()
  })
})

describe('UsersPage (P1C) — actions, self and last admin', () => {
  beforeEach(() => vi.clearAllMocks())

  it('one non-modal "..." menu with Edit, Reset password and a destructive Delete', () => {
    setup([ALICE, BOB])
    const row = rowOf('Bob.Tran')
    expect(within(row).getAllByRole('button')).toHaveLength(1)
    const menu = openRowMenu(row)
    const items = within(menu).getAllByRole('menuitem').map((i) => i.textContent)
    expect(items).toEqual(['users.editUser', 'users.resetPassword', 'users.deleteUser'])
    expect(within(menu).getAllByRole('menuitem')[2]).toHaveAttribute('data-variant', 'destructive')
    expect(document.body.style.pointerEvents).not.toBe('none')
  })

  it('a regular user can be deleted through the confirm dialog', async () => {
    deleteMutate.mockResolvedValue(undefined)
    setup([ALICE, BOB])
    fireEvent.keyDown(within(openRowMenu(rowOf('Bob.Tran'))).getAllByRole('menuitem')[2], { key: 'Enter' })
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'users.deleteUser' }))
    })
    expect(deleteMutate).toHaveBeenCalledWith('user:bob')
  })

  it('self row: "you" badge; delete disabled with a visible reason; dialog never opens', () => {
    const second = u('user:root', 'root', 'admin')
    setup([ALICE, second, BOB])
    expect(within(rowOf('alice')).getByText('users.you')).toBeInTheDocument()
    expect(within(rowOf('root')).queryByText('users.you')).toBeNull()
    const del = within(openRowMenu(rowOf('alice'))).getAllByRole('menuitem')[2]
    expect(del).toHaveAttribute('data-disabled')
    expect(del).toHaveTextContent('users.cannotDeleteSelf')
    expect(del).toHaveAttribute('title', 'users.cannotDeleteSelf')
    fireEvent.keyDown(del, { key: 'Enter' })
    fireEvent.click(del)
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(deleteMutate).not.toHaveBeenCalled()
  })

  it('last admin (not self): delete disabled with cannotRemoveLastAdmin', () => {
    setup([ALICE, BOB], {}, BOB)
    const del = within(openRowMenu(rowOf('alice'))).getAllByRole('menuitem')[2]
    expect(del).toHaveAttribute('data-disabled')
    expect(del).toHaveTextContent('users.cannotRemoveLastAdmin')
  })

  it('last admin edit: rename allowed, "user" role disabled with explanation, demotion never sent', async () => {
    updateMutate.mockResolvedValue(undefined)
    setup([ALICE, BOB], {}, BOB)
    fireEvent.keyDown(within(openRowMenu(rowOf('alice'))).getAllByRole('menuitem')[0], { key: 'Enter' })
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('users.cannotRemoveLastAdmin')).toBeInTheDocument()

    fireEvent.keyDown(within(dialog).getByRole('combobox'), { key: 'Enter' })
    const userOption = await screen.findByRole('option', { name: 'users.roleUser' })
    expect(userOption).toHaveAttribute('data-disabled')
    // Close the select by picking the (still allowed) admin role
    fireEvent.click(screen.getByRole('option', { name: 'users.roleAdmin' }))

    fireEvent.change(within(screen.getByRole('dialog')).getByLabelText('users.username'), { target: { value: 'alice2' } })
    await act(async () => {
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'common.save' }))
    })
    expect(updateMutate).toHaveBeenCalledWith({ id: 'user:alice', data: { username: 'alice2', role: 'admin', name: 'Alice Nguyễn' } })
  })

  it('with two admins, a non-self admin can be deleted and demoted as before', async () => {
    updateMutate.mockResolvedValue(undefined)
    const root = u('user:root', 'root', 'admin')
    setup([ALICE, root, BOB])
    const del = within(openRowMenu(rowOf('root'))).getAllByRole('menuitem')[2]
    expect(del).not.toHaveAttribute('data-disabled')
    fireEvent.keyDown(del, { key: 'Escape' })

    fireEvent.keyDown(within(openRowMenu(rowOf('root'))).getAllByRole('menuitem')[0], { key: 'Enter' })
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).queryByText('users.cannotRemoveLastAdmin')).toBeNull()
    fireEvent.keyDown(within(dialog).getByRole('combobox'), { key: 'Enter' })
    const userOption = await screen.findByRole('option', { name: 'users.roleUser' })
    expect(userOption).not.toHaveAttribute('data-disabled')
    fireEvent.click(userOption)
    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('combobox')).toHaveTextContent('users.roleUser'))
    await act(async () => {
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'common.save' }))
    })
    expect(updateMutate).toHaveBeenCalledWith({ id: 'user:root', data: { username: 'root', role: 'user', name: null } })
  })

  it('submit guard: a pending demotion is not sent if the user became the last admin meanwhile', async () => {
    const root = u('user:root', 'root', 'admin')
    const view = setup([ALICE, root, BOB], {}, BOB)
    fireEvent.keyDown(within(openRowMenu(rowOf('root'))).getAllByRole('menuitem')[0], { key: 'Enter' })
    fireEvent.keyDown(within(screen.getByRole('dialog')).getByRole('combobox'), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: 'users.roleUser' }))

    // Another admin lost the role in the meantime: root is now the last admin.
    vi.mocked(useUsers).mockReturnValue({
      data: [u('user:alice', 'alice', 'user'), root, BOB],
      isLoading: false,
      isError: false,
      refetch,
    } as unknown as ReturnType<typeof useUsers>)
    view.rerender(<UsersPage />)

    await act(async () => {
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'common.save' }))
    })
    expect(updateMutate).not.toHaveBeenCalled()
  })
})

