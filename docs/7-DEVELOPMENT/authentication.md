# Authentication, RBAC & Data Isolation

ChatBot5400 adds account-based authentication with two roles, role-based access
control (RBAC), and per-user data isolation on top of Open Notebook.

- **Authentication** — users sign in with a username + password; the API issues
  a JWT that the frontend sends on every request.
- **Authorization (RBAC)** — an `admin` role manages the knowledge base and user
  accounts; a `user` role has read-only access to that knowledge base plus their
  own chats and notes.
- **Data isolation** — chat sessions and notes are private to the user who
  created them. Even an admin cannot read another user's chats or notes.

## Roles & permissions

| Capability | admin | user |
|---|:---:|:---:|
| View notebooks & sources | ✅ | ✅ |
| Create / edit / delete notebooks | ✅ | ❌ |
| Add / edit / delete sources, add sources to notebooks | ✅ | ❌ |
| Create / delete source insights, embed content | ✅ | ❌ |
| Chat in notebooks / sources | ✅ | ✅ |
| Create & manage **their own** notes | ✅ | ✅ |
| See **other users'** chats / notes | ❌ | ❌ |
| Manage users (create/edit/delete, reset password) | ✅ | ❌ |
| Models, transformations, settings, advanced | ✅ | ❌ |
| Change **their own** password | ✅ | ✅ |

Regular users get a read-only knowledge base they can think on top of (chat +
notes); everything that mutates the shared knowledge base or the app is admin-only.

## Default admin & first login

On a fresh database, startup seeds one admin account:

```
username: admin
password: admin
```

**Change this password immediately** via the profile menu (sidebar → *Change
Password*). The seed is idempotent — it runs only when the `user` table is empty.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `OPEN_NOTEBOOK_JWT_SECRET` | derived from `OPEN_NOTEBOOK_ENCRYPTION_KEY` | HMAC secret used to sign JWTs. Set it explicitly for stable sessions across restarts / multiple workers. |
| `OPEN_NOTEBOOK_JWT_EXPIRE_MINUTES` | `720` (12h) | Access-token lifetime. |
| `OPEN_NOTEBOOK_DISABLE_AUTH` | unset (auth **enforced**) | Truthy (`1/true/yes/on`) turns OFF auth enforcement for a trusted single-user/self-hosted deployment. All requests then run as a synthetic admin and data isolation is not applied. A startup warning is logged. |

> `OPEN_NOTEBOOK_DISABLE_AUTH` is also how the test suite exercises protected
> endpoints without minting tokens (see `tests/conftest.py`). Leave it unset in
> any multi-user or exposed deployment.

## Backend

### Data model (SurrealDB, migration 26)

- `user` table — `username` (unique index), `password_hash` (bcrypt), `role`
  (`admin` | `user`), `name`, timestamps.
- `note.user_id` and `chat_session.user_id` — optional `record<user>` owner
  links (+ indexes). Optional so rows created before auth remain valid.

Migration files: `open_notebook/database/migrations/26.surrealql` (+ `26_down`),
registered in `open_notebook/database/async_migrate.py`.

### Domain

- `open_notebook/domain/user.py` — `User` model with `get_by_username`,
  `authenticate`, `create`, `set_password`, `count`, and `seed_default_admin()`.
- `open_notebook/utils/passwords.py` — `hash_password` / `verify_password`
  (bcrypt, 72-byte safe).

### Auth layer (`api/auth.py`)

- `create_access_token(user_id, username, role)` / `decode_token(token)` — JWT
  (HS256) mint/verify.
- `JWTAuthMiddleware` — app-wide **requireAuth**: rejects any `/api` request
  without a valid Bearer token, except an allowlist (login, auth status, config,
  health/docs). Stores the identity on `request.state.user`.
- `get_current_user(request) -> TokenUser` — dependency returning the caller.
- `require_admin(request) -> TokenUser` — dependency enforcing `role == admin`
  (raises `AuthorizationError` → HTTP 403).

### Endpoints

Auth (`api/routers/auth.py`):

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/auth/status` | public | Whether auth is enforced |
| `POST /api/auth/login` | public | `{username,password}` → `{access_token, user}` |
| `POST /api/auth/logout` | user | Client discards the token (stateless) |
| `GET /api/auth/me` | user | Current user profile |
| `POST /api/auth/change-password` | user | `{current_password, new_password}` |

User management (`api/routers/users.py`, **admin only**):

| Method & path | Purpose |
|---|---|
| `GET /api/users` | List users |
| `POST /api/users` | Create user |
| `GET /api/users/{id}` | Get user |
| `PUT /api/users/{id}` | Update username / role / name |
| `DELETE /api/users/{id}` | Delete user (blocks self-delete / last admin) |
| `POST /api/users/{id}/reset-password` | Admin resets a user's password |

RBAC on existing endpoints: notebook & source create/update/delete (and
add/remove source, insight creation) are wrapped with `require_admin`; reads stay
available to any authenticated user. Notes and chat endpoints set `user_id` on
create and filter by owner on read/update/delete.

### Adding a new admin-only endpoint

```python
from fastapi import Depends
from api.auth import require_admin

@router.post("/things", dependencies=[Depends(require_admin)])
async def create_thing(...): ...
```

For per-user data, take the caller and scope by it:

```python
from api.auth import TokenUser, get_current_user

@router.get("/things")
async def list_things(current: TokenUser = Depends(get_current_user)):
    return await Thing.for_user(current.id)
```

## Frontend

- **State** — `src/lib/stores/auth-store.ts` (Zustand, persisted as
  `auth-storage`) holds the JWT + current `user`. `apiClient` auto-attaches the
  token; SSE streams attach it explicitly.
- **Login & guard** — `src/components/auth/LoginForm.tsx`; the dashboard layout
  redirects unauthenticated users to `/login`. `useAuth()` exposes `user` and
  `isAdmin`.
- **User management** — admin-only page at `/settings/users`.
- **Change password** — `ChangePasswordDialog` from the sidebar profile area.
- **RBAC in the UI** — create/edit/delete controls for notebooks & sources are
  gated behind `useAuth().isAdmin`; the admin-only "Manage" section and its pages
  (models, transformations, settings, advanced, users) are hidden and
  route-guarded via `useAdminGuard()` for non-admins.

> The UI hiding is a convenience; the backend is the source of truth and returns
> 401/403 regardless of what the client renders.

## Testing

- `tests/test_passwords.py` — hashing/verification.
- `tests/test_user_domain.py` — `User` queries, `authenticate`, `create`, seeding.
- `tests/test_auth.py` — JWT round-trip, middleware, `require_admin`, the
  disable flag.

Run: `uv run pytest tests/test_auth.py tests/test_passwords.py tests/test_user_domain.py`
