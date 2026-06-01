"""Reusable OpenAPI examples for the Cogitus API."""

from __future__ import annotations

from typing import Final

JsonResponseExample = dict[str, dict[str, dict[str, object]]]
OpenApiExamples = dict[str, dict[str, object]]

GROUP_RESPONSE_EXAMPLE: Final = {
    "pk": 4,
    "created_at": 1763814050,
    "updated_at": 1763814050,
    "name": "api",
    "parent_pk": 3,
}
ROOT_GROUP_RESPONSE_EXAMPLE: Final = {
    "pk": 3,
    "created_at": 1763814000,
    "updated_at": 1763814000,
    "name": "backend",
}
GROUPS_RESPONSE_EXAMPLE: Final = [
    GROUP_RESPONSE_EXAMPLE,
    ROOT_GROUP_RESPONSE_EXAMPLE,
    {
        "pk": 1,
        "created_at": 1763810000,
        "updated_at": 1763810000,
        "name": "default",
    },
]
GROUP_NAMES_RESPONSE_EXAMPLE: Final = ["api", "backend", "default"]
GROUP_CREATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "root_group": {
        "summary": "Create a root group",
        "description": "Omit parent_pk to create a top-level group.",
        "value": {
            "name": "backend",
        },
    },
    "child_group": {
        "summary": "Create a child group",
        "description": (
            "Include parent_pk to nest the group under another group."
        ),
        "value": {
            "name": "api",
            "parent_pk": 3,
        },
    },
}
GROUP_UPDATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "rename_group": {
        "summary": "Rename a group",
        "value": {
            "name": "backend-services",
        },
    },
}

TAG_RESPONSE_EXAMPLE: Final = {
    "pk": 8,
    "created_at": 1763814100,
    "updated_at": 1763814100,
    "name": "sqlite",
}
TAGS_RESPONSE_EXAMPLE: Final = [
    TAG_RESPONSE_EXAMPLE,
    {
        "pk": 9,
        "created_at": 1763814200,
        "updated_at": 1763814200,
        "name": "search",
    },
    {
        "pk": 10,
        "created_at": 1763814300,
        "updated_at": 1763814300,
        "name": "performance",
    },
]
TAG_NAMES_RESPONSE_EXAMPLE: Final = ["sqlite", "search", "performance"]
TAG_CREATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "create_tag": {
        "summary": "Create a tag",
        "value": {
            "name": "sqlite",
        },
    },
}
TAG_UPDATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "rename_tag": {
        "summary": "Rename a tag",
        "value": {
            "name": "sqlite-fts",
        },
    },
}

IDEA_RESPONSE_EXAMPLE: Final = {
    "pk": 42,
    "created_at": 1763817600,
    "updated_at": 1763904000,
    "title": "Compare SQLite FTS query strategies",
    "body": (
        "Review prefix matching, tag filters, and ranking behavior before "
        "settling on the next search implementation."
    ),
    "detail_hash": (
        "7f83b1657ff1fc53b92dc18148a1d65dfa1359588e3e3b9543b34cba9f6d4c2f"
    ),
    "group": ROOT_GROUP_RESPONSE_EXAMPLE,
    "tags": TAGS_RESPONSE_EXAMPLE,
}
SECOND_IDEA_RESPONSE_EXAMPLE: Final = {
    "pk": 43,
    "created_at": 1763821200,
    "updated_at": 1763907600,
    "title": "Draft remote cache refresh notes",
    "body": (
        "Document when the client should refresh snapshots and when a "
        "lightweight hash check is enough."
    ),
    "detail_hash": (
        "b54d3c9f2a7e6c8041b6b65e27a458f8afbb9d42485d2abcc70f6d8f13e6a2c1"
    ),
    "group": GROUP_RESPONSE_EXAMPLE,
    "tags": [TAGS_RESPONSE_EXAMPLE[1]],
}
IDEAS_RESPONSE_EXAMPLE: Final = [
    SECOND_IDEA_RESPONSE_EXAMPLE,
    IDEA_RESPONSE_EXAMPLE,
]
IDEA_REFS_RESPONSE_EXAMPLE: Final = [
    {
        "pk": 42,
        "title": "Compare SQLite FTS query strategies",
        "group": "backend",
        "tags": ["sqlite", "search", "performance"],
        "updated_at": 1763904000,
    },
    {
        "pk": 43,
        "title": "Draft remote cache refresh notes",
        "group": "api",
        "tags": ["search"],
        "updated_at": 1763907600,
    },
]
IDEA_HASH_RESPONSE_EXAMPLE: Final = {
    "pk": 42,
    "detail_hash": IDEA_RESPONSE_EXAMPLE["detail_hash"],
}
IDEA_CREATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "default_group_idea": {
        "summary": "Create an idea in the default group",
        "description": "Omit group_pk to use the configured default group.",
        "value": {
            "title": "Capture release checklist",
            "body": "List the final checks before publishing the next release.",
            "tags": ["release", "todo"],
        },
    },
    "grouped_idea": {
        "summary": "Create an idea in a specific group",
        "value": {
            "title": "Compare SQLite FTS query strategies",
            "body": (
                "Review prefix matching, tag filters, and ranking behavior "
                "before settling on the next search implementation."
            ),
            "tags": ["sqlite", "search", "performance"],
            "group_pk": 3,
        },
    },
}
IDEA_UPDATE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "replace_idea": {
        "summary": "Replace an idea after reading it",
        "description": (
            "last_known_updated_at lets the server reject the update if the "
            "idea changed since it was read."
        ),
        "value": {
            "title": "Compare SQLite FTS query strategies",
            "body": (
                "Capture benchmark notes and choose the search query plan "
                "for the next release."
            ),
            "tags": ["sqlite", "search"],
            "group_pk": 3,
            "last_known_updated_at": 1763904000,
        },
    },
    "keep_existing_tags": {
        "summary": "Update text and keep existing tags",
        "description": "Omit tags to leave the current tag list unchanged.",
        "value": {
            "title": "Compare SQLite FTS query strategies",
            "body": (
                "Capture benchmark notes and choose the search query plan "
                "for the next release."
            ),
            "group_pk": 3,
        },
    },
}
IDEA_DELETE_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "delete_after_reading": {
        "summary": "Delete an idea after reading it",
        "description": (
            "last_known_updated_at lets the server reject the delete if the "
            "idea changed since it was read."
        ),
        "value": {
            "last_known_updated_at": 1763904000,
        },
    },
    "delete_without_freshness_check": {
        "summary": "Delete an idea without a freshness check",
        "value": {},
    },
}

SNAPSHOT_RESPONSE_EXAMPLE: Final = {
    "groups": GROUPS_RESPONSE_EXAMPLE,
    "tags": TAGS_RESPONSE_EXAMPLE,
    "ideas": IDEAS_RESPONSE_EXAMPLE,
}
SNAPSHOT_STATE_RESPONSE_EXAMPLE: Final = {
    "dataset_hash": (
        "0b7c4f48f1d0a77c2641f45d8ed5e72ef34852f4ff70e2f143149bc68423c27b"
    ),
}

TOKEN_RESPONSE_EXAMPLE: Final = {
    "access_token": (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJhcGktdXNlciIsImV4cCI6MTc2Mzk5MDQwMH0."
        "synthetic-signature"
    ),
    "token_type": "bearer",
}
TOKEN_REQUEST_OPENAPI_EXAMPLES: Final[OpenApiExamples] = {
    "password_login": {
        "summary": "Request a bearer token",
        "value": {
            "username": "api-user",
            "password": "correct horse battery staple",
        },
    },
}
HEALTH_RESPONSE_EXAMPLE: Final = {"status": "ok"}


def json_response_example(example: object) -> JsonResponseExample:
    """Return FastAPI OpenAPI metadata for one JSON response example."""
    return {
        "content": {
            "application/json": {
                "example": example,
            },
        },
    }
