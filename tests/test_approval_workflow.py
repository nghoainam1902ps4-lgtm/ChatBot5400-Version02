"""Tests for the ChatBot5400 approval workflow: roles, auth dependencies,
source approve/reject, and approver scope resolution."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from starlette.types import Scope

from api import approvals_service
from api.auth import (
    TokenUser,
    require_approver,
    require_submitter,
)
from open_notebook.domain.notebook import Notebook, Source, _drop_unapproved_results
from open_notebook.exceptions import AuthorizationError, NotFoundError

DOMAIN = "open_notebook.domain.notebook"
BASE = "open_notebook.domain.base"


def _make_request() -> Request:
    scope: Scope = {"type": "http", "method": "GET", "path": "/api/x", "headers": []}
    return Request(scope)


def _req_as(role: str) -> Request:
    req = _make_request()
    req.state.user = TokenUser(id="user:1", username="u", role=role)
    return req


# --- Role capabilities ----------------------------------------------------
class TestTokenUserRoles:
    @pytest.mark.parametrize(
        "role,submit,review,needs_approval",
        [
            ("admin", True, True, False),
            # Approver is a checker: reviews but does NOT submit new sources.
            ("approver", False, True, False),
            ("contributor", True, False, True),
            ("user", False, False, False),
        ],
    )
    def test_role_capabilities(self, role, submit, review, needs_approval):
        u = TokenUser(id="user:1", username="u", role=role)
        assert u.can_submit_sources is submit
        assert u.can_review is review
        assert u.requires_approval is needs_approval

    def test_role_flags(self):
        assert TokenUser(id="u:1", username="u", role="approver").is_approver
        assert TokenUser(id="u:1", username="u", role="contributor").is_contributor


# --- Auth dependencies ----------------------------------------------------
class TestApprovalDependencies:
    def test_require_approver_allows_admin_and_approver(self):
        for role in ("admin", "approver"):
            assert require_approver(_req_as(role)).role == role

    @pytest.mark.parametrize("role", ["contributor", "user"])
    def test_require_approver_blocks_others(self, role):
        with pytest.raises(AuthorizationError):
            require_approver(_req_as(role))

    @pytest.mark.parametrize("role", ["admin", "contributor"])
    def test_require_submitter_allows_submitters(self, role):
        assert require_submitter(_req_as(role)).role == role

    # Approver (checker) and plain user may not submit new sources.
    @pytest.mark.parametrize("role", ["approver", "user"])
    def test_require_submitter_blocks_non_submitters(self, role):
        with pytest.raises(AuthorizationError):
            require_submitter(_req_as(role))


# --- Source approve / reject ---------------------------------------------
class TestSourceReview:
    @pytest.mark.asyncio
    async def test_approve_is_targeted_update_and_embeds_fresh_text(self):
        # The in-memory copy predates extraction (no text); the DB now has it.
        source = Source(id="source:1", approval_status="pending", full_text=None)
        repo = AsyncMock(side_effect=[[], ["extracted text"]])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch.object(Source, "save", new=AsyncMock()) as save,
            patch.object(
                Source, "vectorize", new=AsyncMock(return_value="command:9")
            ) as vectorize,
        ):
            cmd = await source.approve("user:admin")
        # Approval is written with a targeted UPDATE, never a full-record save.
        save.assert_not_awaited()
        assert "SET approval_status = 'approved'" in repo.await_args_list[0].args[0]
        assert source.approval_status == "approved"
        assert source.reviewed_by == "user:admin"
        assert cmd == "command:9"
        vectorize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_while_still_processing_skips_embed(self):
        source = Source(id="source:1", approval_status="pending", full_text=None)
        repo = AsyncMock(side_effect=[[], [None]])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch.object(Source, "vectorize", new=AsyncMock()) as vectorize,
        ):
            cmd = await source.approve("user:admin")
        assert cmd == ""
        vectorize.assert_not_awaited()

    def test_update_save_never_writes_approval_fields(self):
        # A stale copy (e.g. the processing job's) must not revert an approval.
        source = Source(
            id="source:1",
            approval_status="pending",
            submitted_by="user:c",
            assigned_approver="user:p",
            title="t",
        )
        data = source._prepare_save_data()
        for field in (
            "approval_status",
            "submitted_by",
            "reviewed_by",
            "review_note",
            "submitted_at",
            "reviewed_at",
            "assigned_approver",
        ):
            assert field not in data
        assert data["title"] == "t"

    def test_create_save_writes_approval_fields(self):
        source = Source(approval_status="pending", submitted_by="user:c")
        data = source._prepare_save_data()
        assert data["approval_status"] == "pending"
        assert str(data["submitted_by"]) == "user:c"

    @pytest.mark.asyncio
    async def test_was_approved_by_review(self):
        source = Source(id="source:1")
        cases = [
            ([{"approval_status": "approved", "reviewed_at": "2026-01-01"}], True),
            # Added directly by an admin: approved but never reviewed.
            ([{"approval_status": "approved", "reviewed_at": None}], False),
            ([{"approval_status": "pending", "reviewed_at": None}], False),
        ]
        for rows, expected in cases:
            with patch(f"{DOMAIN}.repo_query", new=AsyncMock(return_value=rows)):
                assert await source.was_approved_by_review() is expected

    @pytest.mark.asyncio
    async def test_delete_removes_notebook_links(self):
        # Rejection deletes the source; its reference edges must go too.
        source = Source(id="source:1", approval_status="pending")
        repo = AsyncMock(return_value=[])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch(f"{BASE}.repo_delete", new=AsyncMock(return_value=True)),
        ):
            await source.delete()
        queries = [c.args[0] for c in repo.await_args_list]
        assert any(q.startswith("DELETE reference WHERE in") for q in queries)


class TestSearchHidesPending:
    @pytest.mark.asyncio
    async def test_drops_pending_source_and_its_insights(self):
        results = [
            {"id": "source:ok", "title": "approved"},
            {"id": "source:pend", "title": "pending"},
            {"id": "source_insight:i1", "title": "insight of pending"},
            {"id": "source_insight:i2", "title": "insight of approved"},
            {"id": "note:n1", "title": "note"},
        ]
        repo = AsyncMock(
            side_effect=[
                [
                    {"id": "source_insight:i1", "source": "source:pend"},
                    {"id": "source_insight:i2", "source": "source:ok"},
                ],
                ["source:pend"],
            ]
        )
        with patch(f"{DOMAIN}.repo_query", new=repo):
            kept = await _drop_unapproved_results(results, limit=10)
        assert [r["id"] for r in kept] == [
            "source:ok",
            "source_insight:i2",
            "note:n1",
        ]

    @pytest.mark.asyncio
    async def test_truncates_to_requested_count(self):
        results = [{"id": f"note:{i}"} for i in range(6)]
        with patch(f"{DOMAIN}.repo_query", new=AsyncMock(return_value=[])):
            kept = await _drop_unapproved_results(results, limit=3)
        assert len(kept) == 3


class TestSourceVisibility:
    @pytest.fixture(autouse=True)
    def _enforce_auth(self, monkeypatch: pytest.MonkeyPatch):
        # The suite disables auth globally; visibility rules only apply with it on.
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)

    PENDING = dict(
        id="source:1",
        approval_status="pending",
        submitted_by="user:c",
        assigned_approver="user:p",
    )

    @pytest.mark.asyncio
    async def test_approved_is_visible_to_everyone(self):
        user = TokenUser(id="user:u", username="u", role="user")
        await approvals_service.assert_can_view_source(
            user, Source(id="source:1", approval_status="approved")
        )

    @pytest.mark.asyncio
    async def test_pending_hidden_from_plain_user(self):
        user = TokenUser(id="user:u", username="u", role="user")
        with pytest.raises(NotFoundError):
            await approvals_service.assert_can_view_source(
                user, Source(**self.PENDING)
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "uid,role",
        [("user:c", "contributor"), ("user:p", "approver"), ("user:a", "admin")],
    )
    async def test_pending_visible_to_submitter_assignee_and_admin(self, uid, role):
        user = TokenUser(id=uid, username="x", role=role)
        await approvals_service.assert_can_view_source(user, Source(**self.PENDING))

    @pytest.mark.asyncio
    async def test_pending_visible_to_approver_in_scope(self):
        user = TokenUser(id="user:q", username="q", role="approver")
        with (
            patch.object(
                Notebook, "managed_scope_ids", new=AsyncMock(return_value=["notebook:1"])
            ),
            patch.object(
                Source,
                "referenced_notebook_ids",
                new=AsyncMock(return_value=["notebook:1"]),
            ),
        ):
            await approvals_service.assert_can_view_source(
                user, Source(**self.PENDING)
            )

    @pytest.mark.asyncio
    async def test_pending_hidden_from_other_contributor(self):
        user = TokenUser(id="user:other", username="o", role="contributor")
        with pytest.raises(NotFoundError):
            await approvals_service.assert_can_view_source(
                user, Source(**self.PENDING)
            )


# --- Approver scope -------------------------------------------------------
class TestApproverScope:
    @pytest.mark.asyncio
    async def test_scope_admin_is_global(self):
        admin = TokenUser(id="user:a", username="a", role="admin")
        assert await approvals_service.scope_ids_for(admin) is None

    @pytest.mark.asyncio
    async def test_scope_plain_user_is_empty(self):
        user = TokenUser(id="user:u", username="u", role="user")
        assert await approvals_service.scope_ids_for(user) == []

    @pytest.mark.asyncio
    async def test_scope_approver_uses_managed_ids(self):
        approver = TokenUser(id="user:p", username="p", role="approver")
        with patch.object(
            Notebook,
            "managed_scope_ids",
            new=AsyncMock(return_value=["notebook:1", "notebook:2"]),
        ):
            assert await approvals_service.scope_ids_for(approver) == [
                "notebook:1",
                "notebook:2",
            ]

    @pytest.mark.asyncio
    async def test_can_review_source_in_scope(self):
        approver = TokenUser(id="user:p", username="p", role="approver")
        source = Source(id="source:1", approval_status="pending")
        with (
            patch.object(
                Notebook,
                "managed_scope_ids",
                new=AsyncMock(return_value=["notebook:1"]),
            ),
            patch.object(
                Source,
                "referenced_notebook_ids",
                new=AsyncMock(return_value=["notebook:1"]),
            ),
        ):
            await approvals_service.assert_can_review_source(approver, source)

    @pytest.mark.asyncio
    async def test_cannot_review_source_out_of_scope(self):
        approver = TokenUser(id="user:p", username="p", role="approver")
        source = Source(id="source:1", approval_status="pending")
        with (
            patch.object(
                Notebook,
                "managed_scope_ids",
                new=AsyncMock(return_value=["notebook:1"]),
            ),
            patch.object(
                Source,
                "referenced_notebook_ids",
                new=AsyncMock(return_value=["notebook:9"]),
            ),
        ):
            with pytest.raises(AuthorizationError):
                await approvals_service.assert_can_review_source(approver, source)

    @pytest.mark.asyncio
    async def test_admin_can_review_any_source(self):
        admin = TokenUser(id="user:a", username="a", role="admin")
        source = Source(id="source:1", approval_status="pending")
        # No scope lookup needed for admins.
        await approvals_service.assert_can_review_source(admin, source)

    def test_pending_scope_admin_is_unfiltered(self):
        where, nb_filter, params = Source._pending_scope(None, None)
        assert where == "approval_status = 'pending'"
        assert nb_filter == ""
        assert params == {}

    def test_pending_scope_approver_matches_assignment_or_scope(self):
        where, nb_filter, params = Source._pending_scope(
            ["notebook:1"], "user:p"
        )
        assert "assigned_approver = $me" in where
        assert "assigned_approver = NONE" in where
        assert nb_filter == " AND out IN $ids"
        assert "me" in params and "ids" in params

    @pytest.mark.asyncio
    async def test_manage_notebook_scope_enforced(self):
        approver = TokenUser(id="user:p", username="p", role="approver")
        with patch.object(
            Notebook,
            "managed_scope_ids",
            new=AsyncMock(return_value=["notebook:1"]),
        ):
            await approvals_service.assert_can_manage_notebook(approver, "notebook:1")
            with pytest.raises(AuthorizationError):
                await approvals_service.assert_can_manage_notebook(
                    approver, "notebook:2"
                )
