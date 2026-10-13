# API Reference

Complete REST API for Open Notebook. All endpoints are served from the API backend (default: `http://localhost:5055`).

**Base URL**: `http://localhost:5055` (development) or environment-specific production URL

**Interactive Docs**: Use FastAPI's built-in Swagger UI at `http://localhost:5055/docs` for live testing and exploration. This is the primary reference for all endpoints, request/response schemas, and real-time testing.

---

## Quick Start

### 1. Authentication

Account-based login (username + password) returns a JWT that you send on every
request as a Bearer token:

```bash
# 1. Log in to get a JWT (default seeded admin is admin/admin — change it!)
TOKEN=$(curl -s -X POST http://localhost:5055/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

# 2. Send the token on protected requests
curl http://localhost:5055/api/notebooks \
  -H "Authorization: Bearer $TOKEN"
```

Tokens are stateless and expire after `OPEN_NOTEBOOK_JWT_EXPIRE_MINUTES` (default
12h). For a trusted single-user deployment you can set
`OPEN_NOTEBOOK_DISABLE_AUTH=true` to turn enforcement off (all requests then run
as a synthetic admin).

> **📖 See [Authentication, RBAC & Data Isolation](authentication.md)** for roles,
> per-user data isolation, and configuration.

### 2. Base API Flow

Most operations follow this pattern:
1. Create a **Notebook** (container for research)
2. Add **Sources** (PDFs, URLs, text)
3. Query via **Chat** or **Search**
4. View results and **Notes**

### 3. Testing Endpoints

Instead of memorizing endpoints, use the interactive API docs:
- Navigate to `http://localhost:5055/docs`
- Try requests directly in the browser
- See request/response schemas in real-time
- Test with your own data

---

## API Endpoints Overview

### Main Resource Types

**Notebooks** - Research projects containing sources and notes
- `GET/POST /notebooks` - List and create
- `GET/PUT/DELETE /notebooks/{id}` - Read, update, delete

**Sources** - Content items (PDFs, URLs, text)
- `GET/POST /sources` - List and add content
- `GET /sources/{id}` - Fetch source details
- `POST /sources/{id}/retry` - Retry failed processing
- `GET /sources/{id}/download` - Download original file

**Notes** - User-created or AI-generated research notes
- `GET/POST /notes` - List and create
- `GET/PUT/DELETE /notes/{id}` - Read, update, delete

**Chat** - Conversational AI interface
- `GET/POST /chat/sessions` - Manage chat sessions
- `POST /chat/execute` - Send message and get response
- `POST /chat/context` - Prepare context for chat

**Search** - Find content by text or semantic similarity
- `POST /search` - Full-text or vector search
- `POST /search/ask` - Ask a question (search + synthesize)
- Both accept an optional `notebook_ids` list (or a single `notebook_id`) to scope results to specific notebooks; omit for the whole knowledge base

**Transformations** - Custom prompts for extracting insights
- `GET/POST /transformations` - Create custom extraction rules
- `POST /sources/{id}/insights` - Apply transformation to source

**Models** - Configure AI providers
- `GET /models` - Available models
- `GET /models/defaults` - Current defaults
- `POST /models/config` - Set defaults

**Credentials** - Manage AI provider credentials
- `GET/POST /credentials` - List and create credentials
- `GET/PUT/DELETE /credentials/{id}` - CRUD operations
- `POST /credentials/{id}/test` - Test connection
- `POST /credentials/{id}/discover` - Discover models from provider
- `POST /credentials/{id}/register-models` - Register discovered models
- `GET /credentials/status` - Provider status overview
- `GET /credentials/env-status` - Environment variable status
- `POST /credentials/migrate-from-env` - Migrate env vars to credentials

**Health & Status**
- `GET /health` - Health check
- `GET /commands/{id}` - Track async operations

---

## Authentication

The API uses **account-based authentication**: users sign in with a username and
password, and the API issues a **JWT** that must be sent on every protected
request. There are two roles — `admin` (manages the knowledge base and user
accounts) and `user` (read-only knowledge base plus their own chats and notes) —
and chat sessions and notes are isolated per user.

### 1. Log in

```bash
curl -X POST http://localhost:5055/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}'
```

Response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {"id": "user:...", "username": "admin", "role": "admin"}
}
```

A fresh database seeds one admin account (`admin` / `admin`). **Change this
password immediately** via `POST /api/auth/change-password` or the profile menu.

### 2. Call protected endpoints

Send the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:5055/api/notebooks
```

Public endpoints (no token required): `GET /api/auth/status`,
`POST /api/auth/login`, `GET /api/config`, `GET /health`, and the docs
(`/docs`, `/openapi.json`, `/redoc`).

### Auth-related endpoints

- `POST /api/auth/login` — authenticate, returns a JWT
- `GET /api/auth/me` — current user profile
- `POST /api/auth/logout` — stateless (client discards the token)
- `POST /api/auth/change-password` — change own password
- `PUT /api/auth/preferences` — update UI language / theme
- `GET /api/auth/status` — report whether auth is enforced (public)

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `OPEN_NOTEBOOK_JWT_SECRET` | derived from `OPEN_NOTEBOOK_ENCRYPTION_KEY` | HMAC secret used to sign JWTs. Set explicitly for stable sessions across restarts / multiple workers. |
| `OPEN_NOTEBOOK_JWT_EXPIRE_MINUTES` | `720` (12h) | Access-token lifetime. |
| `OPEN_NOTEBOOK_DISABLE_AUTH` | unset (auth **enforced**) | Truthy (`1/true/yes/on`) turns OFF enforcement for a trusted single-user deployment — all requests run as a synthetic admin and data isolation is not applied. |

> **📖 See [Authentication, RBAC & Data Isolation](authentication.md)** for the
> full role matrix, data model, and data-isolation details, and
> [Security Configuration](../5-CONFIGURATION/security.md) for production hardening.

---

## Common Patterns

### Pagination

```bash
# List sources with limit/offset
curl 'http://localhost:5055/sources?limit=20&offset=10'
```

### Filtering & Sorting

```bash
# Filter by notebook, sort by date
curl 'http://localhost:5055/sources?notebook_id=notebook:abc&sort_by=created&sort_order=asc'

# Search sources by title / uploaded file name (case- and accent-insensitive,
# applied before limit/offset; combines with notebook_id and sorting)
curl 'http://localhost:5055/sources?q=quy%20dinh&limit=30&offset=0'
```

### Async Operations

Some operations (source processing, podcast generation) return immediately with a command ID:

```bash
# Submit async operation
curl -X POST http://localhost:5055/sources -F async_processing=true
# Response: {"id": "source:src001", "command_id": "command:cmd123"}

# Poll status
curl http://localhost:5055/commands/command:cmd123
```

### Streaming Responses

The `/ask` endpoint streams responses as Server-Sent Events:

```bash
curl -N 'http://localhost:5055/ask' \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AI?"}'

# Outputs: data: {"type":"strategy",...}
#          data: {"type":"answer",...}
#          data: {"type":"final_answer",...}
```

### Multipart File Upload

```bash
curl -X POST http://localhost:5055/sources \
  -F "type=upload" \
  -F "notebook_id=notebook:abc" \
  -F "file=@document.pdf"
```

---

## Error Handling

All errors return JSON with status code:

```json
{"detail": "Notebook not found"}
```

### Common Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Operation completed |
| 400 | Bad Request | Invalid input |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource already exists |
| 500 | Server Error | Database/processing error |

---

## Tips for Developers

1. **Start with interactive docs** (`http://localhost:5055/docs`) - this is the definitive reference
2. **Enable logging** for debugging (check API logs: `docker logs`)
3. **Streaming endpoints** require special handling (Server-Sent Events, not standard JSON)
4. **Async operations** return immediately; always poll status before assuming completion
5. **Vector search** requires embedding model configured (check `/models`)
6. **Model overrides** are per-request; set in body, not config
7. **CORS enabled** in development; configure for production

---

## Learning Path

1. **Authentication**: `POST /auth/login` to get a JWT, then send it as `Authorization: Bearer <token>`
2. **Create a notebook**: `POST /notebooks` with name and description
3. **Add a source**: `POST /sources` with file, URL, or text
4. **Query your content**: `POST /chat/execute` to ask questions
5. **Explore advanced features**: Search, transformations, streaming

---

## Production Considerations

- Harden JWT auth: set a stable `OPEN_NOTEBOOK_JWT_SECRET`, change the default `admin/admin` account, and keep `OPEN_NOTEBOOK_DISABLE_AUTH` unset (see [Authentication](authentication.md) and [Security](../5-CONFIGURATION/security.md))
- Add rate limiting via reverse proxy (Nginx, CloudFlare, Kong)
- Enable CORS restrictions (currently allows all origins)
- Use HTTPS via reverse proxy (see [Reverse Proxy](../5-CONFIGURATION/reverse-proxy.md))
- Set up API versioning strategy (currently implicit)

See [Security Configuration](../5-CONFIGURATION/security.md) and [Reverse Proxy Setup](../5-CONFIGURATION/reverse-proxy.md) for complete production setup.
