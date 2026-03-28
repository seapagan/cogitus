"""HTTP client for the Cogitus remote API."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import httpx

from cogitus.api.schemas.request.group import (
    GroupCreateRequest,
    GroupUpdateRequest,
)
from cogitus.api.schemas.response.auth import TokenResponse
from cogitus.api.schemas.response.group import GroupResponse
from cogitus.api.schemas.response.idea import IdeaResponse
from cogitus.api.schemas.response.tag import TagResponse
from cogitus.backends.types import RemoteSnapshot
from cogitus.config import (
    normalize_api_auth_username,
    normalize_remote_api_base_url,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from cogitus.api.schemas.request.idea import (
        IdeaCreateRequest,
        IdeaUpdateRequest,
    )

_IDEA_PAGE_SIZE = 1000
_DEFAULT_TIMEOUT_SECONDS = 10.0
ModelT = TypeVar("ModelT")


class RemoteAPIClient:
    """Small authenticated client for the Cogitus FastAPI server."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Configure the client and its persisted credentials."""
        self._base_url = normalize_remote_api_base_url(base_url)
        self._username = normalize_api_auth_username(username)
        self._password = password
        self._access_token: str | None = None
        self._client = httpx.Client(
            base_url=self._base_url or "http://invalid.local",
            headers={"Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def fetch_snapshot(self) -> RemoteSnapshot:
        """Fetch groups, tags, and ideas for a full local-cache refresh."""
        return RemoteSnapshot(
            groups=self.list_groups(),
            tags=self.list_tags(),
            ideas=self.list_all_ideas(),
        )

    def list_groups(self) -> list[GroupResponse]:
        """Return all remote groups."""
        return self._parse_model_list(
            self._request("GET", "/api/v1/groups").json(),
            GroupResponse.model_validate,
        )

    def list_tags(self) -> list[TagResponse]:
        """Return all remote tags."""
        return self._parse_model_list(
            self._request("GET", "/api/v1/tags").json(),
            TagResponse.model_validate,
        )

    def list_all_ideas(self) -> list[IdeaResponse]:
        """Return all remote ideas using paginated list requests."""
        ideas: list[IdeaResponse] = []
        offset = 0
        while True:
            response = self._request(
                "GET",
                "/api/v1/ideas",
                params={"limit": _IDEA_PAGE_SIZE, "offset": offset},
            )
            page = self._parse_model_list(
                response.json(),
                IdeaResponse.model_validate,
            )
            ideas.extend(page)
            if len(page) < _IDEA_PAGE_SIZE:
                return ideas
            offset += _IDEA_PAGE_SIZE

    def create_idea(self, payload: IdeaCreateRequest) -> IdeaResponse:
        """Create an idea remotely."""
        return IdeaResponse.model_validate(
            self._request(
                "POST",
                "/api/v1/ideas",
                json=payload.model_dump(),
            ).json()
        )

    def update_idea(
        self,
        idea_pk: int,
        payload: IdeaUpdateRequest,
    ) -> IdeaResponse:
        """Update an existing remote idea."""
        return IdeaResponse.model_validate(
            self._request(
                "PUT",
                f"/api/v1/ideas/{idea_pk}",
                json=payload.model_dump(),
            ).json()
        )

    def delete_idea(self, idea_pk: int) -> None:
        """Delete a remote idea."""
        self._request("DELETE", f"/api/v1/ideas/{idea_pk}")

    def create_group(self, name: str) -> GroupResponse:
        """Create a remote group."""
        payload = GroupCreateRequest(name=name)
        return GroupResponse.model_validate(
            self._request(
                "POST",
                "/api/v1/groups",
                json=payload.model_dump(),
            ).json()
        )

    def rename_group(self, group_pk: int, name: str) -> GroupResponse:
        """Rename a remote group."""
        payload = GroupUpdateRequest(name=name)
        return GroupResponse.model_validate(
            self._request(
                "PUT",
                f"/api/v1/groups/{group_pk}",
                json=payload.model_dump(),
            ).json()
        )

    def delete_group(
        self,
        group_pk: int,
        move_to_group_pk: int | None = None,
    ) -> None:
        """Delete a remote group and optionally move its ideas."""
        params: dict[str, int] | None = None
        if move_to_group_pk is not None:
            params = {"move_to_group_pk": move_to_group_pk}
        self._request(
            "DELETE",
            f"/api/v1/groups/{group_pk}",
            params=params,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        data: dict[str, str] | None = None,
        params: dict[str, int] | None = None,
        retry_on_auth: bool = True,
    ) -> httpx.Response:
        """Send one authenticated request, retrying once after reauth."""
        if path != "/api/v1/auth/token":
            self._ensure_access_token()

        headers: dict[str, str] = {}
        if self._access_token is not None and path != "/api/v1/auth/token":
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            response = self._client.request(
                method,
                path,
                json=json,
                data=data,
                params=params,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            msg = "Could not reach the remote API"
            raise ValueError(msg) from exc

        if (
            response.status_code == httpx.codes.UNAUTHORIZED
            and path != "/api/v1/auth/token"
            and retry_on_auth
        ):
            self._access_token = None
            self._authenticate()
            return self._request(
                method,
                path,
                json=json,
                data=data,
                params=params,
                retry_on_auth=False,
            )

        if response.status_code == httpx.codes.CONFLICT:
            detail = self._detail_from_response(response)
            raise ValueError(detail or "Remote data changed on the server")
        if response.status_code == httpx.codes.UNAUTHORIZED:
            detail = self._detail_from_response(response)
            raise ValueError(detail or "Remote API authentication failed")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            detail = self._detail_from_response(response)
            raise ValueError(detail or "Remote API request failed")
        return response

    def _ensure_access_token(self) -> None:
        """Authenticate if the client has no current access token."""
        if self._access_token is None:
            self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with the configured username and password."""
        if not (self._base_url and self._username and self._password):
            msg = "Remote API is not fully configured"
            raise ValueError(msg)

        response = self._request(
            "POST",
            "/api/v1/auth/token",
            data={
                "username": self._username,
                "password": self._password,
            },
            retry_on_auth=False,
        )
        token = TokenResponse.model_validate(response.json())
        self._access_token = token.access_token

    @staticmethod
    def _detail_from_response(response: httpx.Response) -> str:
        """Extract a standard FastAPI detail message from a response."""
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, dict):
            return ""
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        return ""

    @staticmethod
    def _parse_model_list(
        payload: object,
        parser: Callable[[object], ModelT],
    ) -> list[ModelT]:
        """Parse a JSON list into a list of typed response models."""
        if not isinstance(payload, list):
            msg = "Remote API returned an unexpected response body"
            raise TypeError(msg)
        return [parser(item) for item in payload]
