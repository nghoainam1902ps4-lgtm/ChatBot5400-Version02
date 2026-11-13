"""Server-side role checks on administrator functions (Phase 9B review, P1-P3).

The UI hides model, credential, transformation and maintenance pages from
non-admins, but the backend is the source of truth: before this fix any
logged-in account could repoint a provider credential (sending the stored API
key and all later chat traffic to another host), probe internal addresses
through "test connection" regardless of the URL-ingestion switch, or rebuild
every embedding.

No network and no database: the role dependency answers before the handler.
"""

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ADMIN_ONLY = [
    # provider credentials: every write, and the calls that contact base_url
    ("post", "/api/credentials"),
    ("put", "/api/credentials/credential:x"),
    ("delete", "/api/credentials/credential:x"),
    ("post", "/api/credentials/credential:x/test"),
    ("post", "/api/credentials/credential:x/discover"),
    ("post", "/api/credentials/credential:x/register-models"),
    ("post", "/api/credentials/migrate-from-provider-config"),
    ("post", "/api/credentials/migrate-from-env"),
    # models
    ("post", "/api/models"),
    ("delete", "/api/models/model:x"),
    ("post", "/api/models/model:x/test"),
    ("put", "/api/models/defaults"),
    ("post", "/api/models/sync/openai"),
    ("post", "/api/models/sync"),
    ("post", "/api/models/auto-assign"),
    # transformations (shared prompts) and maintenance
    ("post", "/api/transformations"),
    ("post", "/api/transformations/execute"),
    ("put", "/api/transformations/default-prompt"),
    ("put", "/api/transformations/transformation:x"),
    ("delete", "/api/transformations/transformation:x"),
    ("post", "/api/embed"),
    ("post", "/api/embeddings/rebuild"),
    ("delete", "/api/insights/source_insight:x"),
]

# Every non-GET route that deliberately has NO role dependency: personal data
# (chat, notes, feedback, own password) and features open to all accounts.
# A new mutating route must be added to one of the two lists on purpose.
OPEN_TO_ANY_ACCOUNT = {
    ("POST", "/api/auth/change-password"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("PUT", "/api/auth/preferences"),
    ("POST", "/api/chat/context"),
    ("POST", "/api/chat/execute"),
    ("POST", "/api/chat/sessions"),
    ("PUT", "/api/chat/sessions/{session_id}"),
    ("DELETE", "/api/chat/sessions/{session_id}"),
    ("PUT", "/api/feedback/messages/{message_id}/reaction"),
    ("POST", "/api/feedback/messages/{message_id}/report"),
    ("POST", "/api/insights/{insight_id}/save-as-note"),
    ("POST", "/api/notes"),
    ("PUT", "/api/notes/{note_id}"),
    ("DELETE", "/api/notes/{note_id}"),
    ("POST", "/api/search"),
    ("POST", "/api/search/ask"),
    ("POST", "/api/search/ask/simple"),
    ("POST", "/api/sources/{source_id}/chat/sessions"),
    ("PUT", "/api/sources/{source_id}/chat/sessions/{session_id}"),
    ("DELETE", "/api/sources/{source_id}/chat/sessions/{session_id}"),
    ("POST", "/api/sources/{source_id}/chat/sessions/{session_id}/messages"),
    # Podcasts are a feature of the "Create" section, shown to every account.
    # Whether they should be restricted is a product decision left to the
    # project owner (recorded in docs/ocr/OCR_PHASE9B_REPORT.md).
    ("POST", "/api/podcasts/generate"),
    ("POST", "/api/podcasts/episodes/{episode_id}/retry"),
    ("DELETE", "/api/podcasts/episodes/{episode_id}"),
    ("POST", "/api/episode-profiles"),
    ("PUT", "/api/episode-profiles/{profile_id}"),
    ("DELETE", "/api/episode-profiles/{profile_id}"),
    ("POST", "/api/episode-profiles/{profile_id}/duplicate"),
    ("POST", "/api/speaker-profiles"),
    ("PUT", "/api/speaker-profiles/{profile_id}"),
    ("DELETE", "/api/speaker-profiles/{profile_id}"),
    ("POST", "/api/speaker-profiles/{profile_id}/duplicate"),
}


@pytest.fixture(autouse=True)
def _enforce_auth(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", "test-secret-admin-route-tests")
    monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _token(role: str) -> dict[str, str]:
    from api.auth import create_access_token

    return {
        "Authorization": f"Bearer {create_access_token(f'user:{role}', role, role)}"
    }


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_unauthenticated_is_rejected(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("role", ["user", "contributor", "approver"])
@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_non_admin_is_forbidden_before_the_handler(client, role, method, path):
    """403 comes from the role dependency: the body is not even validated, so
    nothing is saved, tested or sent anywhere."""
    with (
        patch("api.routers.credentials.svc_test_credential", new=AsyncMock()) as probe,
        patch("api.routers.credentials.validate_url", new=AsyncMock()) as validate,
    ):
        r = client.request(method.upper(), path, headers=_token(role))
    assert r.status_code == 403, r.text
    probe.assert_not_called()
    validate.assert_not_called()


def test_admin_still_reaches_the_handler(client):
    with patch(
        "api.routers.credentials.svc_test_credential",
        new=AsyncMock(return_value={"success": True, "message": "ok"}),
    ) as probe:
        r = client.post("/api/credentials/credential:x/test", headers=_token("admin"))
    assert r.status_code == 200
    probe.assert_awaited_once_with("credential:x")


def _role_guards(route) -> set[str]:
    from api.auth import require_admin, require_approver, require_submitter

    names = {
        require_admin: "admin",
        require_approver: "approver",
        require_submitter: "submitter",
    }
    found: set[str] = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call in names:
                found.add(names[sub.call])
            walk(sub)

    walk(route.dependant)
    return found


def test_every_mutating_route_has_a_role_or_is_listed_as_open():
    """Pins the authorization surface: a new POST/PUT/DELETE route without a
    role check fails this test until someone decides which list it belongs to."""
    from api.main import app

    unguarded = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or _role_guards(route):
            continue
        for method in route.methods - {"GET", "HEAD", "OPTIONS"}:
            unguarded.add((method, route.path))
    assert unguarded == OPEN_TO_ANY_ACCOUNT


def test_admin_only_routes_are_guarded_by_require_admin():
    from api.main import app

    guards = {
        (m, r.path): _role_guards(r)
        for r in app.routes
        if isinstance(r, APIRoute)
        for m in r.methods
    }
    templates = {
        "credential:x": "{credential_id}",
        "model:x": "{model_id}",
        "transformation:x": "{transformation_id}",
        "source_insight:x": "{insight_id}",
        "/sync/openai": "/sync/{provider}",
    }
    for method, path in ADMIN_ONLY:
        for concrete, template in templates.items():
            path = path.replace(concrete, template)
        assert "admin" in guards[(method.upper(), path)], (method, path)


# --- P2: a source may only be built from a file the request uploaded ----------
def _upload_request(file_path="/app/data/uploads/someone-elses.pdf"):
    from api.models import SourceCreate

    return SourceCreate(type="upload", file_path=file_path, delete_source=True)


@pytest.mark.parametrize("role", ["contributor", "approver", "user"])
def test_server_file_path_is_refused_for_non_admins(role):
    from api.auth import TokenUser
    from api.routers.sources import _require_admin_for_server_file

    user = TokenUser(id=f"user:{role}", username=role, role=role)
    with pytest.raises(HTTPException) as exc:
        _require_admin_for_server_file(_upload_request(), None, user)
    assert exc.value.status_code == 403


def test_server_file_path_rule_leaves_other_requests_alone():
    from api.auth import TokenUser
    from api.models import SourceCreate
    from api.routers.sources import _require_admin_for_server_file

    admin = TokenUser(id="user:admin", username="admin", role="admin")
    contributor = TokenUser(id="user:c", username="c", role="contributor")
    # an administrator keeps the legacy behaviour
    _require_admin_for_server_file(_upload_request(), None, admin)
    # a real multipart upload (the server chose the path) is untouched
    _require_admin_for_server_file(
        SourceCreate(type="upload"),
        cast(UploadFile, object()),
        contributor,
    )
    # text sources are untouched, even with a stray file_path
    _require_admin_for_server_file(
        SourceCreate(type="text", content="x", file_path="/app/data/uploads/a.pdf"),
        None,
        contributor,
    )


@pytest.mark.parametrize("role", ["contributor", "approver"])
def test_json_endpoint_refuses_a_foreign_upload_path(client, role, tmp_path):
    """The reviewer's reproduction: a contributor pointing /api/sources/json at
    another user's file inside the uploads folder, with delete_source=true."""
    victim = tmp_path / "someone-elses.pdf"
    victim.write_bytes(b"%PDF-1.4 synthetic canary")
    body = {
        "type": "upload",
        "file_path": str(victim),
        "delete_source": True,
        "async_processing": True,
    }
    with (
        patch("api.routers.sources.UPLOADS_FOLDER", str(tmp_path)),
        patch("api.routers.sources._build_content_state", new=AsyncMock()) as build,
        patch(
            "api.routers.sources.CommandService.submit_command_job", new=AsyncMock()
        ) as submit,
    ):
        r = client.post("/api/sources/json", json=body, headers=_token(role))
    assert r.status_code == 403, r.text
    build.assert_not_called()
    submit.assert_not_called()
    assert (
        victim.read_bytes() == b"%PDF-1.4 synthetic canary"
    )  # neither read nor deleted
