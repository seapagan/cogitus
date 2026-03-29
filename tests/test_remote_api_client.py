"""Tests for the low-level remote API client."""

from __future__ import annotations

import httpx
import pytest

from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaUpdateRequest,
)
from cogitus.backends import api_client as api_client_module
from cogitus.backends.api_client import RemoteAPIClient
from tests.remote_api_support import (
    REMOTE_USERNAME,
    MockRemoteAPI,
    StoredGroup,
    StoredIdea,
    remote_secret,
    wrong_remote_secret,
)


def test_remote_api_client_fetch_snapshot_reauths_after_unauthorized() -> None:
    """The remote client should reauthenticate once after a 401."""
    api = MockRemoteAPI()
    api.expire_next_token()
    client = RemoteAPIClient(
        base_url="http://remote.test",
        username=REMOTE_USERNAME,
        password=remote_secret(),
        transport=api.transport(),
    )

    snapshot = client.fetch_snapshot()

    assert api.token_requests == 2
    assert [group.name for group in snapshot.groups] == ["default"]
    assert [tag.name for tag in snapshot.tags] == ["python"]
    assert [idea.title for idea in snapshot.ideas] == ["Seed idea"]


def test_remote_api_client_requires_complete_config() -> None:
    """The remote client should reject incomplete remote configuration."""
    client = RemoteAPIClient(
        base_url="",
        username=REMOTE_USERNAME,
        password=remote_secret(),
    )

    with pytest.raises(ValueError, match="not fully configured"):
        client.fetch_snapshot()


def test_remote_api_client_crud_methods_cover_all_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client CRUD helpers should hit all route wrappers correctly."""
    api = MockRemoteAPI()
    api.groups[2] = StoredGroup(
        pk=2,
        created_at=4,
        updated_at=4,
        name="backend",
    )
    api.ideas[2] = StoredIdea(
        pk=2,
        created_at=5,
        updated_at=5,
        title="Second idea",
        body="Second body",
        group_pk=2,
        tag_pks=[1],
    )
    api._next_group_pk = 3
    api._next_idea_pk = 3
    client = RemoteAPIClient(
        base_url="http://remote.test",
        username=REMOTE_USERNAME,
        password=remote_secret(),
        transport=api.transport(),
    )
    monkeypatch.setattr(api_client_module, "_IDEA_PAGE_SIZE", 1)

    ideas = client.list_all_ideas()
    created = client.create_idea(
        IdeaCreateRequest(
            title="Remote idea",
            body="Serve remotely",
            tags=["fastapi"],
            group_pk=1,
        )
    )
    updated = client.update_idea(
        created.pk,
        IdeaUpdateRequest(
            title="Updated remote idea",
            body="Changed body",
            tags=["httpx"],
            group_pk=1,
            last_known_updated_at=created.updated_at,
        ),
    )
    created_group = client.create_group("platform")
    renamed_group = client.rename_group(created_group.pk, "services")
    client.delete_group(renamed_group.pk, move_to_group_pk=1)
    client.delete_idea(updated.pk)

    assert [idea.title for idea in ideas] == ["Second idea", "Seed idea"]
    assert updated.title == "Updated remote idea"
    assert renamed_group.name == "services"
    assert [group.name for group in client.list_groups()] == [
        "backend",
        "default",
    ]


def test_remote_api_client_raises_for_network_and_auth_failures() -> None:
    """Client should surface transport and auth failures clearly."""

    def failing_transport(request: httpx.Request) -> httpx.Response:
        message = "boom"
        if request.url.path == "/api/v1/auth/token":
            raise httpx.ConnectError(message, request=request)
        return httpx.Response(500)

    network_client = RemoteAPIClient(
        base_url="http://remote.test",
        username=REMOTE_USERNAME,
        password=remote_secret(),
        transport=httpx.MockTransport(failing_transport),
    )
    with pytest.raises(ValueError, match="Could not reach the remote API"):
        network_client.list_groups()

    auth_client = RemoteAPIClient(
        base_url="http://remote.test",
        username=REMOTE_USERNAME,
        password=wrong_remote_secret(),
        transport=MockRemoteAPI().transport(),
    )
    with pytest.raises(
        ValueError,
        match="Incorrect username or password",
    ):
        auth_client.list_groups()


def test_remote_api_client_uses_generic_errors_for_bad_responses() -> None:
    """Client should handle generic API failures and malformed payloads."""

    def error_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/token":
            return httpx.Response(
                200,
                json={"access_token": "token", "token_type": "bearer"},
            )
        return httpx.Response(500, json={})

    client = RemoteAPIClient(
        base_url="http://remote.test",
        username=REMOTE_USERNAME,
        password=remote_secret(),
        transport=httpx.MockTransport(error_transport),
    )
    with pytest.raises(ValueError, match="Remote API request failed"):
        client.list_groups()

    response = httpx.Response(500, text="not-json")
    assert RemoteAPIClient._detail_from_response(response) == ""
    assert (
        RemoteAPIClient._detail_from_response(
            httpx.Response(500, json=["not-a-dict"])
        )
        == ""
    )
    with pytest.raises(
        TypeError,
        match="Remote API returned an unexpected response body",
    ):
        RemoteAPIClient._parse_model_list(
            {"unexpected": True},
            lambda payload: payload,
        )
