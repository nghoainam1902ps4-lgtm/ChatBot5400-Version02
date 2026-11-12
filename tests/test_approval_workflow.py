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
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import AuthorizationError


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
            ("approver", True, True, False),
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

    @pytest.mark.parametrize("role", ["admin", "approver", "contributor"])
    def test_require_submitter_allows_submitters(self, role):
        assert require_submitter(_req_as(role)).role == role

    def test_require_submitter_blocks_plain_user(self):
        with pytest.raises(AuthorizationError):
            require_submitter(_req_as("user"))


# --- Source approve / reject ---------------------------------------------
class TestSourceReview:
    @pytest.mark.asyncio
    async def test_approve_marks_approved_and_embeds(self):
        source = Source(id="source:1", approval_status="pending", full_text="hello")
        with (
            patch.object(Source, "save", new=AsyncMock(return_value=None)),
            patch.object(
                Source, "vectorize", new=AsyncMock(return_value="command:9")
            ) as vectorize,
        ):
            cmd = await source.approve("user:admin")
        assert source.approval_status == "approved"
        assert source.reviewed_by == "user:admin"
        assert source.reviewed_at is not None
        assert cmd == "command:9"
        vectorize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_without_text_skips_embed(self):
        source = Source(id="source:1", approval_status="pending", full_text=None)
        with (
            patch.object(Source, "save", new=AsyncMock(return_value=None)),
            patch.object(Source, "vectorize", new=AsyncMock()) as vectorize,
        ):
            cmd = await source.approve("user:admin")
        assert source.approval_status == "approved"
        assert cmd == ""
        vectorize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reject_marks_rejected_with_note(self):
        source = Source(id="source:1", approval_status="pending")
        with patch.object(Source, "save", new=AsyncMock(return_value=None)):
            await source.reject("user:admin", "duplicate")
        assert source.approval_status == "rejected"
        assert source.reviewed_by == "user:admin"
        assert source.review_note == "duplicate"


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
