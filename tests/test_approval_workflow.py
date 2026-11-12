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
from api.models import ReviewerResponse
from open_notebook.domain.notebook import (
    Notebook,
    Source,
    _keep_approved_results,
    _search_until_filled,
    remove_duplicate_notebook_links,
)
from open_notebook.exceptions import (
    AuthorizationError,
    InvalidInputError,
    NotFoundError,
)

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
    async def test_approve_is_targeted_update_and_embeds_when_claim_won(self):
        # The in-memory copy predates extraction (no text); the claim is decided
        # by the DB, which has the text.
        source = Source(id="source:1", approval_status="pending", full_text=None)
        repo = AsyncMock(side_effect=[[{"id": "source:1"}], [{"id": "source:1"}]])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch.object(Source, "save", new=AsyncMock()) as save,
            patch(f"{DOMAIN}.submit_command", return_value="command:9") as submit,
        ):
            cmd = await source.approve("user:admin")
        # Approval is written with a targeted UPDATE, never a full-record save.
        save.assert_not_awaited()
        assert "SET approval_status = 'approved'" in repo.await_args_list[0].args[0]
        assert "approval_embed_queued" in repo.await_args_list[1].args[0]
        assert source.approval_status == "approved"
        assert source.reviewed_by == "user:admin"
        assert cmd == "command:9"
        submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_does_not_embed_when_claim_lost(self):
        # Claim returns nothing: text not extracted yet, or the processing job
        # already claimed the embedding. Either way approve() must not queue it.
        source = Source(id="source:1", approval_status="pending", full_text="x")
        repo = AsyncMock(side_effect=[[{"id": "source:1"}], []])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch(f"{DOMAIN}.submit_command") as submit,
        ):
            cmd = await source.approve("user:admin")
        assert cmd == ""
        submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_review_embed_is_single_conditional_update(self):
        source = Source(id="source:1")
        repo = AsyncMock(return_value=[{"id": "source:1"}])
        with patch(f"{DOMAIN}.repo_query", new=repo):
            assert await source.claim_review_embed() is True
        query = repo.await_args.args[0]
        assert query.startswith("UPDATE $id SET approval_embed_queued = true")
        # Only review-approved sources with text, and only once.
        for clause in (
            "approval_status = 'approved'",
            "reviewed_at != NONE",
            "full_text",
            "approval_embed_queued != true",
        ):
            assert clause in query
        with patch(f"{DOMAIN}.repo_query", new=AsyncMock(return_value=[])):
            assert await source.claim_review_embed() is False

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

    @pytest.mark.asyncio
    async def test_update_save_rejects_edited_approval_fields(self):
        # Editing an approval field and calling save() must fail loudly rather
        # than silently writing nothing.
        source = Source(id="source:1", approval_status="pending")
        source.assigned_approver = "user:p"
        update = AsyncMock()
        with patch(f"{BASE}.repo_update", new=update):
            # The caller must get InvalidInputError itself, not a generic
            # DatabaseOperationError wrapping it.
            with pytest.raises(InvalidInputError, match="assigned_approver"):
                await source.save()
        update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_save_after_approve_is_allowed(self):
        # approve() refreshes the snapshot, so a later ordinary save() of the
        # same object (e.g. a title edit) is not mistaken for an approval edit.
        source = Source(id="source:1", approval_status="pending")
        with patch(
            f"{DOMAIN}.repo_query",
            new=AsyncMock(side_effect=[[{"id": "source:1"}], []]),
        ):
            await source.approve("user:admin")
        source.title = "renamed"
        update = AsyncMock(return_value=[{"id": "source:1", "title": "renamed"}])
        with patch(f"{BASE}.repo_update", new=update):
            await source.save()
        written = update.await_args.args[2]
        assert written["title"] == "renamed"
        assert "approval_status" not in written

    @pytest.mark.asyncio
    async def test_approve_refuses_a_source_that_is_not_pending(self):
        # The conditional UPDATE matched nothing: already approved (or gone).
        source = Source(id="source:1", approval_status="approved")
        repo = AsyncMock(return_value=[])
        with (
            patch(f"{DOMAIN}.repo_query", new=repo),
            patch(f"{DOMAIN}.submit_command") as submit,
        ):
            with pytest.raises(InvalidInputError, match="awaiting approval"):
                await source.approve("user:p")
        assert "WHERE approval_status = 'pending'" in repo.await_args.args[0]
        submit.assert_not_called()

    def test_create_save_writes_approval_fields(self):
        source = Source(approval_status="pending", submitted_by="user:c")
        data = source._prepare_save_data()
        assert data["approval_status"] == "pending"
        assert str(data["submitted_by"]) == "user:c"

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
        # Text-search shape: an insight hit's parent_id is the insight itself.
        results = [
            {"id": "source:ok", "title": "approved"},
            {"id": "source:pend", "title": "pending"},
            {"id": "source_insight:i1", "parent_id": "source_insight:i1"},
            {"id": "source_insight:i2", "parent_id": "source_insight:i2"},
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
            kept = await _keep_approved_results(results)
        assert [r["id"] for r in kept] == [
            "source:ok",
            "source_insight:i2",
            "note:n1",
        ]

    @pytest.mark.asyncio
    async def test_vector_hits_need_single_query(self):
        # Vector-search shape: parent_id already names the owning source, so no
        # insight lookup is needed, just the one approval query.
        results = [
            {"id": "source:ok", "parent_id": "source:ok"},
            {"id": "source_insight:i1", "parent_id": "source:pend"},
        ]
        repo = AsyncMock(return_value=["source:pend"])
        with patch(f"{DOMAIN}.repo_query", new=repo):
            kept = await _keep_approved_results(results)
        assert [r["id"] for r in kept] == ["source:ok"]
        assert repo.await_count == 1

    @pytest.mark.asyncio
    async def test_notes_only_results_cost_no_query(self):
        repo = AsyncMock()
        with patch(f"{DOMAIN}.repo_query", new=repo):
            kept = await _keep_approved_results([{"id": "note:1"}, {"id": "note:2"}])
        assert len(kept) == 2
        repo.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetches_more_when_pending_hits_underfill_the_page(self):
        # Ranked index: 3 pending hits on top, approved ones below.
        index = [{"id": f"source:p{i}"} for i in range(3)] + [
            {"id": f"source:a{i}"} for i in range(5)
        ]
        requested = []

        async def fetch(count):
            requested.append(count)
            return index[:count]

        async def keep(rows):
            return [r for r in rows if not r["id"].startswith("source:p")]

        with patch(f"{DOMAIN}._keep_approved_results", new=keep):
            kept = await _search_until_filled(fetch, 2)
        # First window (2) was all pending, so a larger one was fetched.
        assert requested == [2, 8]
        assert [r["id"] for r in kept] == ["source:a0", "source:a1"]

    @pytest.mark.asyncio
    async def test_single_fetch_when_nothing_is_dropped(self):
        requested = []

        async def fetch(count):
            requested.append(count)
            return [{"id": "note:1"}]  # fewer than requested, none pending

        async def keep(rows):
            return rows

        with patch(f"{DOMAIN}._keep_approved_results", new=keep):
            kept = await _search_until_filled(fetch, 5)
        assert requested == [5]
        assert kept == [{"id": "note:1"}]

    @pytest.mark.asyncio
    async def test_stops_when_index_is_exhausted(self):
        requested = []

        async def fetch(count):
            requested.append(count)
            return [{"id": "source:p0"}]  # the only hit, and it is pending

        async def keep(rows):
            return []

        with patch(f"{DOMAIN}._keep_approved_results", new=keep):
            kept = await _search_until_filled(fetch, 3)
        assert requested == [3, 12]
        assert kept == []


class TestSourceVisibility:
    @pytest.fixture(autouse=True)
    def _enforce_auth(self, monkeypatch: pytest.MonkeyPatch):
        # The suite disables auth globally; visibility rules only apply with it on.
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)
        approvals_service.invalidate_scope_cache()

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
            await approvals_service.assert_can_view_source(user, Source(**self.PENDING))

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
            await approvals_service.assert_can_view_source(user, Source(**self.PENDING))

    @pytest.mark.asyncio
    async def test_pending_hidden_from_other_contributor(self):
        user = TokenUser(id="user:other", username="o", role="contributor")
        with pytest.raises(NotFoundError):
            await approvals_service.assert_can_view_source(user, Source(**self.PENDING))

    @pytest.mark.asyncio
    async def test_scope_lookup_is_cached_for_view_checks(self):
        # The UI polls a processing source every ~2s; the approver's scope must
        # not be re-resolved on every poll.
        user = TokenUser(id="user:q", username="q", role="approver")
        scope = AsyncMock(return_value=["notebook:1"])
        with (
            patch.object(Notebook, "managed_scope_ids", new=scope),
            patch.object(
                Source,
                "referenced_notebook_ids",
                new=AsyncMock(return_value=["notebook:1"]),
            ),
        ):
            for _ in range(3):
                await approvals_service.assert_can_view_source(
                    user, Source(**self.PENDING)
                )
            assert scope.await_count == 1
            approvals_service.invalidate_scope_cache()
            await approvals_service.assert_can_view_source(user, Source(**self.PENDING))
            assert scope.await_count == 2


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
        where, nb_filter, params = Source._pending_scope(["notebook:1"], "user:p")
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


# --- Review findings 5-9 --------------------------------------------------
class TestAssignedReviewer:
    @pytest.mark.asyncio
    async def test_assigned_approver_can_review_outside_scope(self):
        # Routed directly to this approver and in no notebook they manage
        # (e.g. submitted without a notebook): they must still be able to act.
        approver = TokenUser(id="user:p", username="p", role="approver")
        source = Source(
            id="source:1", approval_status="pending", assigned_approver="user:p"
        )
        scope = AsyncMock(return_value=[])
        with patch.object(Notebook, "managed_scope_ids", new=scope):
            await approvals_service.assert_can_review_source(approver, source)
        scope.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_approver_still_blocked(self):
        other = TokenUser(id="user:q", username="q", role="approver")
        source = Source(
            id="source:1", approval_status="pending", assigned_approver="user:p"
        )
        with patch.object(
            Notebook, "managed_scope_ids", new=AsyncMock(return_value=[])
        ):
            with pytest.raises(AuthorizationError):
                await approvals_service.assert_can_review_source(other, source)

    @pytest.mark.asyncio
    async def test_reviewer_must_be_eligible(self):
        approvals_service.invalidate_scope_cache()
        eligible = [ReviewerResponse(id="user:p", username="p")]
        with patch.object(
            approvals_service,
            "_eligible_reviewers",
            new=AsyncMock(return_value=eligible),
        ):
            await approvals_service.assert_valid_reviewer("user:p", ["notebook:1"])
            with pytest.raises(InvalidInputError):
                await approvals_service.assert_valid_reviewer(
                    "user:someone-else", ["notebook:1"]
                )


class TestReleaseApprover:
    RELEASE = (
        "UPDATE notebook SET managers -= $uid",
        "SET assigned_approver = NONE",
        "approval_status = 'pending'",
    )

    @pytest.mark.asyncio
    async def test_demotion_is_one_transaction(self):
        repo = AsyncMock(return_value=[])
        with patch("api.approvals_service.repo_query", new=repo):
            await approvals_service.demote_approver("user:p", "user")
        assert repo.await_count == 1
        query, params = repo.await_args.args
        assert query.startswith("BEGIN TRANSACTION;")
        assert query.endswith("COMMIT TRANSACTION;")
        for clause in (*self.RELEASE, "UPDATE $uid SET role = $role"):
            assert clause in query
        assert params["role"] == "user"

    @pytest.mark.asyncio
    async def test_deletion_is_one_transaction(self):
        repo = AsyncMock(return_value=[])
        with patch("api.approvals_service.repo_query", new=repo):
            await approvals_service.delete_approver("user:p")
        assert repo.await_count == 1
        query = repo.await_args.args[0]
        assert query.startswith("BEGIN TRANSACTION;")
        for clause in (*self.RELEASE, "DELETE $uid"):
            assert clause in query


class TestReviewGuards:
    @pytest.mark.asyncio
    async def test_assignment_grants_nothing_once_approved(self):
        # assigned_approver stays on the record after approval; it must not let
        # that approver act on (e.g. reject = delete) the approved document.
        approver = TokenUser(id="user:p", username="p", role="approver")
        source = Source(
            id="source:1", approval_status="approved", assigned_approver="user:p"
        )
        with patch.object(
            Notebook, "managed_scope_ids", new=AsyncMock(return_value=[])
        ):
            with pytest.raises(AuthorizationError):
                await approvals_service.assert_can_review_source(approver, source)

    def test_reject_refuses_an_approved_source(self):
        from fastapi.testclient import TestClient

        from api.main import app

        approved = Source(id="source:1", approval_status="approved")
        with (
            patch(
                "api.routers.approvals.Source.get",
                new=AsyncMock(return_value=approved),
            ),
            patch.object(Source, "delete", new=AsyncMock()) as delete,
        ):
            response = TestClient(app).post(
                "/api/approvals/sources/source:1/reject", json={}
            )
        assert response.status_code == 400
        delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reviewer_validation_is_cached_for_a_batch(self):
        approvals_service.invalidate_scope_cache()
        lookup = AsyncMock(return_value=[ReviewerResponse(id="user:p", username="p")])
        with patch.object(approvals_service, "_eligible_reviewers", new=lookup):
            for _ in range(5):  # five files of one batch upload
                await approvals_service.assert_valid_reviewer("user:p", ["notebook:1"])
            assert lookup.await_count == 1
            approvals_service.invalidate_scope_cache()
            await approvals_service.assert_valid_reviewer("user:p", ["notebook:1"])
            assert lookup.await_count == 2


class TestDuplicateLinkRepair:
    @pytest.mark.asyncio
    async def test_keeps_one_edge_per_source_notebook_pair(self):
        repo = AsyncMock(
            side_effect=[
                # groups: one duplicated pair, one clean pair
                [
                    {"in": "source:1", "out": "notebook:1", "n": 3},
                    {"in": "source:2", "out": "notebook:1", "n": 1},
                ],
                ["reference:a", "reference:b", "reference:c"],
                [],
                [],
            ]
        )
        with patch(f"{DOMAIN}.repo_query", new=repo):
            removed = await remove_duplicate_notebook_links()
        assert removed == 2
        deletes = [c for c in repo.await_args_list if c.args[0] == "DELETE $id"]
        assert [str(c.args[1]["id"]) for c in deletes] == [
            "reference:b",
            "reference:c",
        ]

    @pytest.mark.asyncio
    async def test_clean_data_is_a_single_read(self):
        repo = AsyncMock(return_value=[{"in": "source:1", "out": "notebook:1", "n": 1}])
        with patch(f"{DOMAIN}.repo_query", new=repo):
            assert await remove_duplicate_notebook_links() == 0
        assert repo.await_count == 1


class TestJobSurvivesDeletedSource:
    @pytest.mark.asyncio
    async def test_gone_only_when_db_says_so(self):
        from commands.source_commands import _source_is_gone

        target = "commands.source_commands.repo_query"
        with patch(target, new=AsyncMock(return_value=[])):
            assert await _source_is_gone("source:1") is True
        with patch(target, new=AsyncMock(return_value=["source:1"])):
            assert await _source_is_gone("source:1") is False
        # A DB outage must keep the job retrying, not be read as "deleted".
        with patch(target, new=AsyncMock(side_effect=RuntimeError("db down"))):
            assert await _source_is_gone("source:1") is False


class TestNotebookRouterGuards:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from api.main import app

        return TestClient(app)

    def test_sub_notebook_cannot_be_nested_two_levels(self, client):
        child = Notebook(
            id="notebook:child", name="c", description="", parent="notebook:cat"
        )
        with patch(
            "api.routers.notebooks.Notebook.get", new=AsyncMock(return_value=child)
        ):
            response = client.post(
                "/api/notebooks",
                json={"name": "grandchild", "parent": "notebook:child"},
            )
        assert response.status_code == 400
        assert "top-level category" in response.json()["detail"]

    def test_linking_an_already_linked_source_creates_no_duplicate(self, client):
        repo = AsyncMock(return_value=[{"id": "reference:1"}])
        with (
            patch(
                "api.routers.notebooks.Notebook.get",
                new=AsyncMock(
                    return_value=Notebook(id="notebook:1", name="n", description="")
                ),
            ),
            patch(
                "api.routers.notebooks.Source.get",
                new=AsyncMock(return_value=Source(id="source:1")),
            ),
            patch("api.routers.notebooks.repo_query", new=repo),
        ):
            response = client.post("/api/notebooks/notebook:1/sources/source:1")
        assert response.status_code == 200
        queries = [c.args[0] for c in repo.await_args_list]
        # The existence check follows the edge direction (source -> notebook)...
        assert "in = $source_id AND out = $notebook_id" in queries[0]
        # ...so an existing link is found and no second edge is created.
        assert not any(q.startswith("RELATE") for q in queries)
