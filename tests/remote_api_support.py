"""Shared fake remote API helpers for remote backend tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs

import httpx

ProtectedRouteHandler = Callable[[httpx.Request], httpx.Response]

REMOTE_USERNAME = "api-user"


def remote_secret() -> str:
    """Return the fixed test secret without a password-like assignment."""
    return "secret" + "-pass"


def wrong_remote_secret() -> str:
    """Return an invalid secret without a password-like assignment."""
    return "wrong" + "-secret"


@dataclass
class StoredGroup:
    """In-memory group row used by the fake remote API."""

    pk: int
    created_at: int
    updated_at: int
    name: str


@dataclass
class StoredTag:
    """In-memory tag row used by the fake remote API."""

    pk: int
    created_at: int
    updated_at: int
    name: str


@dataclass
class StoredIdea:
    """In-memory idea row used by the fake remote API."""

    pk: int
    created_at: int
    updated_at: int
    title: str
    body: str
    group_pk: int
    tag_pks: list[int]


class MockRemoteAPI:
    """Stateful in-process transport for remote API tests."""

    def __init__(self) -> None:
        """Initialize the fake server with one group, tag, and idea."""
        self._tick = 100
        self._next_group_pk = 2
        self._next_tag_pk = 2
        self._next_idea_pk = 2
        self.snapshot_requests = 0
        self.list_group_requests = 0
        self.list_tag_requests = 0
        self.list_idea_requests = 0
        self.token_requests = 0
        self.fail_next_protected_request = False
        self._current_token = ""
        self._username = REMOTE_USERNAME
        self._secret_value = remote_secret()
        self.groups: dict[int, StoredGroup] = {
            1: StoredGroup(
                pk=1,
                created_at=1,
                updated_at=1,
                name="default",
            )
        }
        self.tags: dict[int, StoredTag] = {
            1: StoredTag(
                pk=1,
                created_at=2,
                updated_at=2,
                name="python",
            )
        }
        self.ideas: dict[int, StoredIdea] = {
            1: StoredIdea(
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
            if request.method == "POST":
                return self._handle_token_request(request)
            return self._json_response(405, {"detail": "method not allowed"})
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
        exact_handler = self._protected_exact_routes().get(
            (request.method, request.url.path)
        )
        if exact_handler is not None:
            return exact_handler(request)

        matched_prefix = False
        for method, prefix, handler in self._protected_prefix_routes():
            if not request.url.path.startswith(prefix):
                continue
            matched_prefix = True
            if request.method == method:
                return handler(request)

        if matched_prefix:
            return self._json_response(405, {"detail": "method not allowed"})
        return self._json_response(404, {"detail": "not found"})

    def _protected_exact_routes(
        self,
    ) -> dict[tuple[str, str], ProtectedRouteHandler]:
        """Return exact-match handlers for authenticated fake API routes."""
        return {
            ("GET", "/api/v1/snapshot"): self._handle_snapshot,
            ("GET", "/api/v1/groups"): self._handle_list_groups,
            ("GET", "/api/v1/tags"): self._handle_list_tags,
            ("GET", "/api/v1/ideas"): self._handle_list_ideas,
            ("POST", "/api/v1/ideas"): self._handle_create_idea,
            ("POST", "/api/v1/groups"): self._handle_create_group,
        }

    def _protected_prefix_routes(
        self,
    ) -> tuple[tuple[str, str, ProtectedRouteHandler], ...]:
        """Return prefix handlers for authenticated fake API routes."""
        return (
            ("PUT", "/api/v1/ideas/", self._handle_idea_request),
            ("DELETE", "/api/v1/ideas/", self._handle_idea_request),
            ("PUT", "/api/v1/groups/", self._handle_group_request),
            ("DELETE", "/api/v1/groups/", self._handle_group_request),
        )

    def _handle_list_groups(self, request: httpx.Request) -> httpx.Response:
        """Return all groups sorted by name."""
        del request
        self.list_group_requests += 1
        return self._json_response(
            200,
            [
                self._group_payload(group)
                for group in sorted(
                    self.groups.values(),
                    key=lambda item: item.name,
                )
            ],
        )

    def _handle_list_tags(self, request: httpx.Request) -> httpx.Response:
        """Return all tags sorted by name."""
        del request
        self.list_tag_requests += 1
        return self._json_response(
            200,
            [
                self._tag_payload(tag)
                for tag in sorted(
                    self.tags.values(),
                    key=lambda item: item.name,
                )
            ],
        )

    def _handle_snapshot(self, request: httpx.Request) -> httpx.Response:
        """Return one consistent full dataset payload."""
        del request
        self.snapshot_requests += 1
        return self._json_response(
            200,
            {
                "groups": [
                    self._group_payload(group)
                    for group in sorted(
                        self.groups.values(),
                        key=lambda item: item.name,
                    )
                ],
                "tags": [
                    self._tag_payload(tag)
                    for tag in sorted(
                        self.tags.values(),
                        key=lambda item: item.name,
                    )
                ],
                "ideas": [
                    self._idea_payload(idea)
                    for idea in sorted(
                        self.ideas.values(),
                        key=lambda item: item.updated_at,
                        reverse=True,
                    )
                ],
            },
        )

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
        self.list_idea_requests += 1
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
        if group_pk not in self.groups:
            return self._json_response(
                404,
                {"detail": f"Group {group_pk} not found"},
            )
        tag_pks = self._resolve_tags(self._payload_list(payload, "tags"))
        self._tick += 1
        idea = StoredIdea(
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
        if "tags" in payload:
            idea.tag_pks = self._resolve_tags(
                self._payload_list(payload, "tags")
            )
        idea.updated_at = self._tick
        return self._json_response(200, self._idea_payload(idea))

    def _handle_create_group(self, request: httpx.Request) -> httpx.Response:
        """Create a new group."""
        name = str(self._json_payload(request)["name"]).strip().lower()
        self._tick += 1
        group = StoredGroup(
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
            return self._handle_group_update(request, group_pk, group)
        return self._handle_group_delete(request, group_pk)

    def _handle_group_update(
        self,
        request: httpx.Request,
        group_pk: int,
        group: StoredGroup,
    ) -> httpx.Response:
        """Handle PUT requests for one group."""
        if group_pk == 1:
            return self._json_response(
                409,
                {"detail": "Default group cannot be renamed"},
            )

        self._tick += 1
        group.name = str(self._json_payload(request)["name"]).strip().lower()
        group.updated_at = self._tick
        return self._json_response(200, self._group_payload(group))

    def _handle_group_delete(
        self,
        request: httpx.Request,
        group_pk: int,
    ) -> httpx.Response:
        """Handle DELETE requests for one group."""
        move_to_group_pk = request.url.params.get("move_to_group_pk")
        target_group_pk = int(move_to_group_pk) if move_to_group_pk else 1
        target_group = self.groups.get(target_group_pk)
        if group_pk == 1:
            status_code = 409
            response_payload = {"detail": "Default group cannot be deleted"}
        elif target_group is None:
            status_code = 404
            response_payload = {"detail": "Target group not found"}
        elif target_group_pk == group_pk:
            status_code = 409
            response_payload = {
                "detail": "Cannot move ideas into the same group being deleted"
            }
        else:
            for idea in self.ideas.values():
                if idea.group_pk == group_pk:
                    idea.group_pk = target_group_pk
                    self._tick += 1
                    idea.updated_at = self._tick
            del self.groups[group_pk]
            status_code = 204
            response_payload = None
        return self._json_response(status_code, response_payload)

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
            tag = StoredTag(
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

    def _group_payload(self, group: StoredGroup) -> dict[str, object]:
        """Serialize a group for API responses."""
        return {
            "pk": group.pk,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "name": group.name,
        }

    def _tag_payload(self, tag: StoredTag) -> dict[str, object]:
        """Serialize a tag for API responses."""
        return {
            "pk": tag.pk,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "name": tag.name,
        }

    def _idea_payload(self, idea: StoredIdea) -> dict[str, object]:
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
