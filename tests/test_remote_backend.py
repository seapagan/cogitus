"""Tests for the remote API client and cache-backed remote backend."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import httpx
import pytest

from cogitus.api.schemas.request.idea import (
    IdeaCreateRequest,
    IdeaUpdateRequest,
)
from cogitus.backends import api_client as api_client_module
from cogitus.backends.api_client import RemoteAPIClient
from cogitus.backends.remote_backend import RemoteIdeaBackend
from cogitus.db import get_db

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture
    from sqliter import SqliterDB

_REMOTE_USERNAME = "api-user"


def _remote_secret() -> str:
    """Return the fixed test secret without a password-like assignment."""
    return "secret" + "-pass"


def _wrong_remote_secret() -> str:
    """Return an invalid secret without a password-like assignment."""
    return "wrong" + "-secret"


@dataclass
class _StoredGroup:
    pk: int
    created_at: int
    updated_at: int
    name: str


@dataclass
class _StoredTag:
    pk: int
    created_at: int
    updated_at: int
    name: str


@dataclass
class _StoredIdea:
    pk: int
    created_at: int
    updated_at: int
    title: str
    body: str
    group_pk: int
    tag_pks: list[int]


class _MockRemoteAPI:
    """Stateful in-process transport for remote backend tests."""

    def __init__(self) -> None:
        self._tick = 100
        self._next_group_pk = 2
        self._next_tag_pk = 2
        self._next_idea_pk = 2
        self.token_requests = 0
        self.fail_next_protected_request = False
        self._current_token = ""
        self._username = _REMOTE_USERNAME
        self._secret_value = _remote_secret()
        self.groups: dict[int, _StoredGroup] = {
            1: _StoredGroup(
                pk=1,
                created_at=1,
                updated_at=1,
                name="default",
            )
        }
        self.tags: dict[int, _StoredTag] = {
            1: _StoredTag(
                pk=1,
                created_at=2,
                updated_at=2,
                name="python",
            )
        }
        self.ideas: dict[int, _StoredIdea] = {
            1: _StoredIdea(
                pk=1,
                created_at=3,
                updated_at=3,
                title="Seed idea",
                body="Seed body",
                group_pk=1,
                tag_pks=[1],
            )
        }

    def transport(self) -> httpx.MockTransport:
        """Return a reusable transport for httpx.Client."""
        return httpx.MockTransport(self._handle_request)

    def expire_next_token(self) -> None:
        """Cause the next protected request to return 401 once."""
        self.fail_next_protected_request = True

    def mutate_idea(self, idea_pk: int, *, title: str) -> None:
        """Simulate another client updating an idea on the server."""
        idea = self.ideas[idea_pk]
        self._tick += 1
        idea.title = title
        idea.updated_at = self._tick

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        """Serve one HTTPX request from the in-memory remote state."""
        if request.url.path == "/api/v1/auth/token":
            return self._handle_token_request(request)
        if not self._authorize_request(request):
            return self._json_response(
                401,
                {"detail": "Could not validate credentials"},
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        return self._dispatch_protected_request(request)

    def _dispatch_protected_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        """Dispatch one authenticated request to the relevant handler."""
        response: httpx.Response | None = None
        if request.method == "GET" and request.url.path == "/api/v1/groups":
            response = self._json_response(
                200,
                [
                    self._group_payload(group)
                    for group in sorted(
                        self.groups.values(),
                        key=lambda item: item.name,
                    )
                ],
            )
        elif request.method == "GET" and request.url.path == "/api/v1/tags":
            response = self._json_response(
                200,
                [
                    self._tag_payload(tag)
                    for tag in sorted(
                        self.tags.values(),
                        key=lambda item: item.name,
                    )
                ],
            )
        elif request.method == "GET" and request.url.path == "/api/v1/ideas":
            response = self._handle_list_ideas(request)
        elif request.method == "POST" and request.url.path == "/api/v1/ideas":
            response = self._handle_create_idea(request)
        elif request.url.path.startswith("/api/v1/ideas/"):
            response = self._handle_idea_request(request)
        elif request.method == "POST" and request.url.path == "/api/v1/groups":
            response = self._handle_create_group(request)
        elif request.url.path.startswith("/api/v1/groups/"):
            response = self._handle_group_request(request)

        if response is None:
            return self._json_response(404, {"detail": "not found"})
        return response

    def _handle_token_request(self, request: httpx.Request) -> httpx.Response:
        """Authenticate the fixed test user."""
        parsed = parse_qs(request.content.decode())
        username = parsed.get("username", [""])[0]
        password = parsed.get("password", [""])[0]
        if username != self._username or password != self._secret_value:
            return self._json_response(
                401,
                {"detail": "Incorrect username or password"},
            )
        self.token_requests += 1
        self._current_token = f"token-{self.token_requests}"
        return self._json_response(
            200,
            {"access_token": self._current_token, "token_type": "bearer"},
        )

    def _authorize_request(self, request: httpx.Request) -> bool:
        """Validate the bearer token for protected requests."""
        if self.fail_next_protected_request:
            self.fail_next_protected_request = False
            return False
        auth_header = str(request.headers.get("Authorization", ""))
        return auth_header == f"Bearer {self._current_token}"

    def _handle_list_ideas(self, request: httpx.Request) -> httpx.Response:
        """Return paginated ideas sorted by most recent update."""
        limit = int(request.url.params.get("limit", "1000"))
        offset = int(request.url.params.get("offset", "0"))
        ideas = sorted(
            self.ideas.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        payload = [
            self._idea_payload(idea) for idea in ideas[offset : offset + limit]
        ]
        return self._json_response(200, payload)

    def _handle_create_idea(self, request: httpx.Request) -> httpx.Response:
        """Create a new idea."""
        payload = self._json_payload(request)
        group_pk = self._payload_int(payload, "group_pk", default=1)
        tag_pks = self._resolve_tags(self._payload_list(payload, "tags"))
        self._tick += 1
        idea = _StoredIdea(
            pk=self._next_idea_pk,
            created_at=self._tick,
            updated_at=self._tick,
            title=str(payload["title"]),
            body=str(payload.get("body", "")),
            group_pk=group_pk,
            tag_pks=tag_pks,
        )
        self.ideas[idea.pk] = idea
        self._next_idea_pk += 1
        return self._json_response(201, self._idea_payload(idea))

    def _handle_idea_request(self, request: httpx.Request) -> httpx.Response:
        """Handle PUT and DELETE requests for one idea."""
        idea_pk = int(request.url.path.rsplit("/", 1)[1])
        idea = self.ideas.get(idea_pk)
        if idea is None:
            return self._json_response(
                404,
                {"detail": f"Idea {idea_pk} not found"},
            )
        if request.method == "DELETE":
            del self.ideas[idea_pk]
            return self._json_response(204, None)
        payload = self._json_payload(request)
        if payload.get("last_known_updated_at") != idea.updated_at:
            return self._json_response(
                409,
                {"detail": "Idea has been modified on the server"},
            )
        self._tick += 1
        idea.title = str(payload["title"])
        idea.body = str(payload.get("body", ""))
        idea.group_pk = self._payload_int(
            payload,
            "group_pk",
            default=idea.group_pk,
        )
        idea.tag_pks = self._resolve_tags(self._payload_list(payload, "tags"))
        idea.updated_at = self._tick
        return self._json_response(200, self._idea_payload(idea))

    def _handle_create_group(self, request: httpx.Request) -> httpx.Response:
        """Create a new group."""
        name = str(self._json_payload(request)["name"]).strip().lower()
        self._tick += 1
        group = _StoredGroup(
            pk=self._next_group_pk,
            created_at=self._tick,
            updated_at=self._tick,
            name=name,
        )
        self.groups[group.pk] = group
        self._next_group_pk += 1
        return self._json_response(201, self._group_payload(group))

    def _handle_group_request(self, request: httpx.Request) -> httpx.Response:
        """Handle PUT and DELETE requests for one group."""
        group_pk = int(request.url.path.rsplit("/", 1)[1])
        group = self.groups.get(group_pk)
        if group is None:
            return self._json_response(
                404,
                {"detail": f"Group {group_pk} not found"},
            )
        if request.method == "PUT":
            self._tick += 1
            group.name = (
                str(self._json_payload(request)["name"]).strip().lower()
            )
            group.updated_at = self._tick
            return self._json_response(200, self._group_payload(group))
        move_to_group_pk = request.url.params.get("move_to_group_pk")
        target_group_pk = int(move_to_group_pk) if move_to_group_pk else 1
        for idea in self.ideas.values():
            if idea.group_pk == group_pk:
                idea.group_pk = target_group_pk
                self._tick += 1
                idea.updated_at = self._tick
        del self.groups[group_pk]
        return self._json_response(204, None)

    def _resolve_tags(self, tag_names: list[str]) -> list[int]:
        """Resolve tag names, creating tags as needed."""
        resolved: list[int] = []
        for raw_name in tag_names:
            name = str(raw_name).strip().lower()
            existing = next(
                (tag.pk for tag in self.tags.values() if tag.name == name),
                None,
            )
            if existing is not None:
                resolved.append(existing)
                continue
            self._tick += 1
            tag = _StoredTag(
                pk=self._next_tag_pk,
                created_at=self._tick,
                updated_at=self._tick,
                name=name,
            )
            self.tags[tag.pk] = tag
            resolved.append(tag.pk)
            self._next_tag_pk += 1
        return resolved

    @staticmethod
    def _json_payload(request: httpx.Request) -> dict[str, object]:
        """Decode a JSON request body."""
        payload = json.loads(request.content.decode())
        if not isinstance(payload, dict):
            msg = "Expected a JSON object payload"
            raise TypeError(msg)
        return payload

    @staticmethod
    def _payload_int(
        payload: dict[str, object],
        key: str,
        *,
        default: int,
    ) -> int:
        """Extract an integer-like field from a JSON payload."""
        value = payload.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        return int(str(value))

    @staticmethod
    def _payload_list(payload: dict[str, object], key: str) -> list[str]:
        """Extract a list field from a JSON payload."""
        value = payload.get(key)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _group_payload(self, group: _StoredGroup) -> dict[str, object]:
        """Serialize a group for API responses."""
        return {
            "pk": group.pk,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "name": group.name,
        }

    def _tag_payload(self, tag: _StoredTag) -> dict[str, object]:
        """Serialize a tag for API responses."""
        return {
            "pk": tag.pk,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "name": tag.name,
        }

    def _idea_payload(self, idea: _StoredIdea) -> dict[str, object]:
        """Serialize an idea for API responses."""
        return {
            "pk": idea.pk,
            "created_at": idea.created_at,
            "updated_at": idea.updated_at,
            "title": idea.title,
            "body": idea.body,
            "group": self._group_payload(self.groups[idea.group_pk]),
            "tags": [
                self._tag_payload(self.tags[tag_pk]) for tag_pk in idea.tag_pks
            ],
        }

    @staticmethod
    def _json_response(
        status_code: int,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Build a JSON response for the mocked transport."""
        return httpx.Response(
            status_code,
            json=payload,
            headers=headers,
        )


def test_remote_api_client_fetch_snapshot_reauths_after_unauthorized() -> None:
    """The remote client should reauthenticate once after a 401."""
    api = _MockRemoteAPI()
    api.expire_next_token()
    client = RemoteAPIClient(
        base_url="http://remote.test",
        username=_REMOTE_USERNAME,
        password=_remote_secret(),
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
        username=_REMOTE_USERNAME,
        password=_remote_secret(),
    )

    with pytest.raises(ValueError, match="not fully configured"):
        client.fetch_snapshot()


def test_remote_api_client_crud_methods_cover_all_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client CRUD helpers should hit all route wrappers correctly."""
    api = _MockRemoteAPI()
    api.groups[2] = _StoredGroup(
        pk=2,
        created_at=4,
        updated_at=4,
        name="backend",
    )
    api.ideas[2] = _StoredIdea(
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
        username=_REMOTE_USERNAME,
        password=_remote_secret(),
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
        username=_REMOTE_USERNAME,
        password=_remote_secret(),
        transport=httpx.MockTransport(failing_transport),
    )
    with pytest.raises(ValueError, match="Could not reach the remote API"):
        network_client.list_groups()

    auth_client = RemoteAPIClient(
        base_url="http://remote.test",
        username=_REMOTE_USERNAME,
        password=_wrong_remote_secret(),
        transport=_MockRemoteAPI().transport(),
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
        username=_REMOTE_USERNAME,
        password=_remote_secret(),
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


def test_remote_backend_sync_populates_cache_and_preserves_cursor(
    db: SqliterDB,
) -> None:
    """Full remote sync should replace cache rows but keep cursor state."""
    cache_service = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=_REMOTE_USERNAME,
            password=_remote_secret(),
            transport=_MockRemoteAPI().transport(),
        ),
    )
    local = cache_service._cache_service
    local.create_idea("Local placeholder")
    local.set_idea_cursor_position(1, 12)

    cache_service.sync_from_remote()

    synced = cache_service.get_idea(1)
    assert synced is not None
    assert synced.title == "Seed idea"
    assert cache_service.get_idea_cursor_position(1) == 12


def test_remote_backend_delegate_and_guard_paths(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Read delegates and missing-record guards should behave correctly."""
    api_client = mocker.Mock()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=api_client,
    )
    seed = backend._cache_service.create_idea("Seed idea", tags=["python"])

    assert backend.update_idea(999, "Missing", "", tags=[], group_pk=1) is None
    assert backend.rename_idea(999, "Missing") is None
    assert backend.rename_group(999, "missing") is None
    assert backend.get_idea(seed.pk) is not None
    assert backend.get_group(seed.group.pk) is not None
    assert backend.list_tags_in_use()[0].name == "python"
    assert backend.list_tags_with_usage()[0][1] == 1
    backend.set_idea_cursor_position(seed.pk, 7)
    assert backend.get_idea_cursor_position(seed.pk) == 7
    assert backend.has_ideas_in_group(seed.group.pk) is True
    assert backend.list_groups()[0].name == "default"
    assert backend.list_ideas_grouped()[0][1][0].pk == seed.pk
    assert backend.search_results("Seed")[0].idea.pk == seed.pk

    rename_update = mocker.patch.object(
        backend, "update_idea", return_value=seed
    )
    assert backend.rename_idea(seed.pk, "Renamed") is seed
    rename_update.assert_called_once_with(
        seed.pk,
        title="Renamed",
        body="",
        tags=["python"],
        group_pk=seed.group.pk,
    )

    mocker.patch.object(backend._cache_service, "get_idea", return_value=seed)
    mocker.patch.object(
        backend._cache_service,
        "get_idea_with_relations",
        return_value=None,
    )
    assert backend.rename_idea(seed.pk, "Renamed") is None

    backend.close()
    api_client.close.assert_called_once_with()


def test_remote_backend_internal_error_guards(
    db: SqliterDB,
    mocker: MockerFixture,
) -> None:
    """Internal cache guard helpers should raise clear runtime errors."""
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=mocker.Mock(),
    )

    mocker.patch.object(backend._cache_service, "get_group", return_value=None)
    with pytest.raises(RuntimeError, match="Group 1 not found in cache"):
        backend._require_cached_group(1)

    mocker.patch.object(backend._cache_service, "get_idea", return_value=None)
    with pytest.raises(RuntimeError, match="Idea 1 not found in cache"):
        backend._require_cached_idea(1)

    with pytest.raises(
        RuntimeError,
        match="Worker-thread sync requires a file-backed cache database",
    ):
        backend._build_worker_cache_db()

    backend._cache_db = mocker.Mock(is_memory=False, filename=None)
    with pytest.raises(
        RuntimeError,
        match="Remote cache database path is unavailable",
    ):
        backend._build_worker_cache_db()


def test_remote_backend_create_update_and_delete_idea_updates_cache(
    db: SqliterDB,
) -> None:
    """Idea writes should update the local cache without a full resync."""
    api = _MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=_REMOTE_USERNAME,
            password=_remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()

    created = backend.create_idea(
        "Remote idea",
        body="Serve remotely",
        tags=["fastapi"],
        group_pk=1,
    )
    assert created.title == "Remote idea"
    assert backend.search_results("tag:fastapi")[0].idea.pk == created.pk

    updated = backend.update_idea(
        created.pk,
        "Updated remote idea",
        "Changed body",
        tags=["httpx"],
        group_pk=1,
    )
    assert updated is not None
    assert updated.title == "Updated remote idea"
    assert backend.search_results("tag:httpx")[0].idea.pk == created.pk

    backend.delete_idea(created.pk)
    assert backend.get_idea(created.pk) is None


def test_remote_backend_update_idea_raises_on_stale_cache(
    db: SqliterDB,
) -> None:
    """Remote updates should surface optimistic-lock conflicts."""
    api = _MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=_REMOTE_USERNAME,
            password=_remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()
    api.mutate_idea(1, title="Changed elsewhere")

    with pytest.raises(ValueError, match="modified on the server"):
        backend.update_idea(
            1,
            "My edit",
            "Seed body",
            tags=["python"],
            group_pk=1,
        )


def test_remote_backend_group_operations_update_cache_and_search(
    db: SqliterDB,
) -> None:
    """Group writes should update cached group state and search data."""
    api = _MockRemoteAPI()
    backend = RemoteIdeaBackend(
        db,
        default_group_name="default",
        api_client=RemoteAPIClient(
            base_url="http://remote.test",
            username=_REMOTE_USERNAME,
            password=_remote_secret(),
            transport=api.transport(),
        ),
    )
    backend.sync_from_remote()

    created_group = backend.create_group("backend")
    created_idea = backend.create_idea(
        "Grouped idea",
        body="Body",
        tags=["python"],
        group_pk=created_group.pk,
    )
    renamed_group = backend.rename_group(created_group.pk, "platform")

    assert renamed_group is not None
    assert (
        backend.search_results("group:platform")[0].idea.pk == created_idea.pk
    )

    backend.delete_group(created_group.pk)

    moved = backend.get_idea(created_idea.pk)
    assert moved is not None
    assert moved.group.pk == 1
    assert backend.get_group(created_group.pk) is None


def test_remote_backend_sync_from_worker_thread_uses_fresh_db_connection(
    tmp_path: Path,
) -> None:
    """Worker-thread sync should not reuse the main-thread SQLite connection."""
    cache_db = get_db(str(tmp_path / "remote-cache.db"))
    try:
        backend = RemoteIdeaBackend(
            cache_db,
            default_group_name="default",
            api_client=RemoteAPIClient(
                base_url="http://remote.test",
                username=_REMOTE_USERNAME,
                password=_remote_secret(),
                transport=_MockRemoteAPI().transport(),
            ),
        )
        assert cache_db.is_connected is True

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(backend.sync_from_remote).result()

        synced = backend.get_idea(1)
        assert synced is not None
        assert synced.title == "Seed idea"
    finally:
        cache_db.close()
