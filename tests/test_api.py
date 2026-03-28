"""Tests for the FastAPI API."""

from fastapi.testclient import TestClient


def test_health_returns_ok(api_client: TestClient) -> None:
    """Health endpoint should return a simple OK payload."""
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_idea_crud_roundtrip(api_client: TestClient) -> None:
    """Ideas should support full CRUD via the API."""
    group = api_client.post("/api/v1/groups", json={"name": "backend"})
    assert group.status_code == 201
    group_pk = group.json()["pk"]

    created = api_client.post(
        "/api/v1/ideas",
        json={
            "title": "API idea",
            "body": "Serve ideas remotely",
            "tags": ["fastapi", "remote"],
            "group_pk": group_pk,
        },
    )

    assert created.status_code == 201
    created_body = created.json()
    idea_pk = created_body["pk"]
    assert created_body["group"]["name"] == "backend"
    assert [tag["name"] for tag in created_body["tags"]] == [
        "fastapi",
        "remote",
    ]

    fetched = api_client.get(f"/api/v1/ideas/{idea_pk}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "API idea"

    updated = api_client.put(
        f"/api/v1/ideas/{idea_pk}",
        json={
            "title": "Updated API idea",
            "body": "Updated body",
            "tags": ["rest"],
            "group_pk": group_pk,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated API idea"
    assert [tag["name"] for tag in updated.json()["tags"]] == ["rest"]

    deleted = api_client.delete(f"/api/v1/ideas/{idea_pk}")
    assert deleted.status_code == 204

    missing = api_client.get(f"/api/v1/ideas/{idea_pk}")
    assert missing.status_code == 404


def test_idea_list_supports_query_limit_and_offset(
    api_client: TestClient,
) -> None:
    """Idea listing should support search query and pagination."""
    api_client.post(
        "/api/v1/ideas",
        json={"title": "Alpha", "body": "python api", "tags": []},
    )
    api_client.post(
        "/api/v1/ideas",
        json={"title": "Beta", "body": "rust cli", "tags": []},
    )
    api_client.post(
        "/api/v1/ideas",
        json={"title": "Gamma", "body": "python search", "tags": []},
    )

    queried = api_client.get("/api/v1/ideas", params={"query": "python"})
    assert queried.status_code == 200
    assert {idea["title"] for idea in queried.json()} == {"Alpha", "Gamma"}

    paged = api_client.get("/api/v1/ideas", params={"limit": 1, "offset": 1})
    assert paged.status_code == 200
    assert len(paged.json()) == 1


def test_create_idea_with_missing_group_returns_not_found(
    api_client: TestClient,
) -> None:
    """Idea creation should reject unknown groups."""
    response = api_client.post(
        "/api/v1/ideas",
        json={
            "title": "Broken",
            "body": "",
            "tags": [],
            "group_pk": 99999,
        },
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_and_delete_missing_idea_return_not_found(
    api_client: TestClient,
) -> None:
    """Missing ideas should return 404 for write operations."""
    update = api_client.put(
        "/api/v1/ideas/99999",
        json={
            "title": "Missing",
            "body": "",
            "tags": [],
            "group_pk": None,
        },
    )
    delete = api_client.delete("/api/v1/ideas/99999")

    assert update.status_code == 404
    assert delete.status_code == 404


def test_update_idea_with_missing_group_returns_not_found(
    api_client: TestClient,
) -> None:
    """Idea updates should reject unknown group targets."""
    created = api_client.post(
        "/api/v1/ideas",
        json={"title": "Idea", "body": "", "tags": []},
    )
    assert created.status_code == 201

    response = api_client.put(
        f"/api/v1/ideas/{created.json()['pk']}",
        json={
            "title": "Idea",
            "body": "",
            "tags": [],
            "group_pk": 99999,
        },
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_group_crud_and_reassign_delete(api_client: TestClient) -> None:
    """Groups should support CRUD and reassignment on delete."""
    source = api_client.post("/api/v1/groups", json={"name": "source"})
    target = api_client.post("/api/v1/groups", json={"name": "target"})
    assert source.status_code == 201
    assert target.status_code == 201

    source_pk = source.json()["pk"]
    target_pk = target.json()["pk"]

    renamed = api_client.put(
        f"/api/v1/groups/{source_pk}",
        json={"name": "source-renamed"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "source-renamed"

    idea = api_client.post(
        "/api/v1/ideas",
        json={
            "title": "Grouped",
            "body": "",
            "tags": [],
            "group_pk": source_pk,
        },
    )
    assert idea.status_code == 201

    deleted = api_client.delete(
        f"/api/v1/groups/{source_pk}",
        params={"move_to_group_pk": target_pk},
    )
    assert deleted.status_code == 204

    moved_idea = api_client.get(f"/api/v1/ideas/{idea.json()['pk']}")
    assert moved_idea.status_code == 200
    assert moved_idea.json()["group"]["pk"] == target_pk

    fetched_group = api_client.get(f"/api/v1/groups/{target_pk}")
    assert fetched_group.status_code == 200
    assert fetched_group.json()["name"] == "target"


def test_delete_default_group_returns_conflict(
    api_client: TestClient,
) -> None:
    """Deleting the default group should be rejected."""
    groups = api_client.get("/api/v1/groups")
    assert groups.status_code == 200
    default_group = next(
        group for group in groups.json() if group["name"] == "default"
    )

    response = api_client.delete(f"/api/v1/groups/{default_group['pk']}")

    assert response.status_code == 409


def test_group_missing_and_validation_paths(api_client: TestClient) -> None:
    """Group endpoints should surface missing and validation errors."""
    create_invalid = api_client.post("/api/v1/groups", json={"name": "   "})
    existing = api_client.post("/api/v1/groups", json={"name": "backend"})
    assert existing.status_code == 201
    update_invalid = api_client.put(
        f"/api/v1/groups/{existing.json()['pk']}",
        json={"name": "   "},
    )
    get_missing = api_client.get("/api/v1/groups/99999")
    update_missing = api_client.put(
        "/api/v1/groups/99999",
        json={"name": "backend"},
    )

    created = api_client.post("/api/v1/groups", json={"name": "source"})
    assert created.status_code == 201
    delete_bad_target = api_client.delete(
        f"/api/v1/groups/{created.json()['pk']}",
        params={"move_to_group_pk": 99999},
    )
    delete_missing = api_client.delete("/api/v1/groups/99999")

    assert create_invalid.status_code == 422
    assert update_invalid.status_code == 422
    assert get_missing.status_code == 404
    assert update_missing.status_code == 404
    assert delete_bad_target.status_code == 404
    assert delete_missing.status_code == 404


def test_tag_crud_and_delete_detaches_ideas(api_client: TestClient) -> None:
    """Tags should support CRUD and detach from ideas on delete."""
    created_tag = api_client.post("/api/v1/tags", json={"name": "python"})
    assert created_tag.status_code == 201
    tag_pk = created_tag.json()["pk"]

    renamed = api_client.put(
        f"/api/v1/tags/{tag_pk}",
        json={"name": "fastapi"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "fastapi"

    idea = api_client.post(
        "/api/v1/ideas",
        json={
            "title": "Tagged",
            "body": "",
            "tags": ["fastapi"],
        },
    )
    assert idea.status_code == 201

    deleted = api_client.delete(f"/api/v1/tags/{tag_pk}")
    assert deleted.status_code == 204

    refetched = api_client.get(f"/api/v1/ideas/{idea.json()['pk']}")
    assert refetched.status_code == 200
    assert refetched.json()["tags"] == []

    fetched_tag = api_client.get(f"/api/v1/tags/{tag_pk}")
    assert fetched_tag.status_code == 404


def test_duplicate_group_and_tag_create_return_conflict(
    api_client: TestClient,
) -> None:
    """Duplicate standalone resource creation should return 409."""
    first_group = api_client.post("/api/v1/groups", json={"name": "backend"})
    second_group = api_client.post("/api/v1/groups", json={"name": "backend"})
    assert first_group.status_code == 201
    assert second_group.status_code == 409

    first_tag = api_client.post("/api/v1/tags", json={"name": "python"})
    second_tag = api_client.post("/api/v1/tags", json={"name": "python"})
    assert first_tag.status_code == 201
    assert second_tag.status_code == 409


def test_tag_list_get_missing_and_validation_paths(
    api_client: TestClient,
) -> None:
    """Tag endpoints should surface list, missing, and validation paths."""
    created = api_client.post("/api/v1/tags", json={"name": "python"})
    assert created.status_code == 201
    tag_pk = created.json()["pk"]

    listed = api_client.get("/api/v1/tags")
    fetched = api_client.get(f"/api/v1/tags/{tag_pk}")
    create_invalid = api_client.post("/api/v1/tags", json={"name": "   "})
    update_invalid = api_client.put(
        f"/api/v1/tags/{tag_pk}",
        json={"name": "   "},
    )
    update_missing = api_client.put(
        "/api/v1/tags/99999",
        json={"name": "fastapi"},
    )
    delete_missing = api_client.delete("/api/v1/tags/99999")

    assert listed.status_code == 200
    assert [tag["name"] for tag in listed.json()] == ["python"]
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "python"
    assert create_invalid.status_code == 422
    assert update_invalid.status_code == 422
    assert update_missing.status_code == 404
    assert delete_missing.status_code == 404
