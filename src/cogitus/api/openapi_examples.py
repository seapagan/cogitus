"""Reusable OpenAPI response examples for the Cogitus API."""

from __future__ import annotations

from typing import Final

JsonResponseExample = dict[str, dict[str, dict[str, object]]]

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
