"""Reusable OpenAPI examples for the Cogitus API."""

from __future__ import annotations

from typing import Final

JsonResponseExample = dict[str, dict[str, dict[str, object]]]
OpenApiExamples = dict[str, dict[str, object]]
OpenApiResponse = dict[str, object]


def _detail(message: str) -> dict[str, str]:
    return {"detail": message}


def _string_too_short_error(field: str) -> dict[str, object]:
    return {
        "detail": [
            {
                "type": "string_too_short",
                "loc": ["body", field],
                "msg": "String should have at least 1 character",
                "input": "   ",
                "ctx": {"min_length": 1},
            },
        ],
    }


def _path_int_error(parameter: str) -> dict[str, object]:
    return {
        "detail": [
            {
                "type": "int_parsing",
                "loc": ["path", parameter],
                "msg": (
                    "Input should be a valid integer, unable to parse string "
                    "as an integer"
                ),
                "input": "abc",
            },
        ],
    }


def _query_limit_error() -> dict[str, object]:
    return {
        "detail": [
            {
                "type": "greater_than_equal",
                "loc": ["query", "limit"],
                "msg": "Input should be greater than or equal to 1",
                "input": "0",
                "ctx": {"ge": 1},
            },
        ],
    }


def _body_int_error(field: str) -> dict[str, object]:
    return {
        "detail": [
            {
                "type": "int_parsing",
                "loc": ["body", field],
                "msg": (
                    "Input should be a valid integer, unable to parse string "
                    "as an integer"
                ),
                "input": "abc",
            },
        ],
    }


def _body_ge_error(field: str) -> dict[str, object]:
    return {
        "detail": [
            {
                "type": "greater_than_equal",
                "loc": ["body", field],
                "msg": "Input should be greater than or equal to 1",
                "input": 0,
                "ctx": {"ge": 1},
            },
        ],
    }


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

AUTH_TOKEN_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Authentication failed.",
    "content": {
        "application/json": {
            "example": _detail("Incorrect username or password"),
        },
    },
}
API_AUTH_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Bearer token is missing or invalid.",
    "content": {
        "application/json": {
            "examples": {
                "missing_token": {
                    "summary": "Call a protected endpoint without a token",
                    "value": _detail("Not authenticated"),
                },
                "invalid_token": {
                    "summary": (
                        "Call a protected endpoint with an invalid token"
                    ),
                    "value": _detail("Could not validate credentials"),
                },
            },
        },
    },
}
API_AUTH_NOT_CONFIGURED_RESPONSE: Final[OpenApiResponse] = {
    "description": "API authentication has not been configured.",
    "content": {
        "application/json": {
            "example": _detail("API authentication is not configured"),
        },
    },
}
TOKEN_FORM_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Token form validation failed.",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "username"],
                        "msg": "Field required",
                        "input": {"password": "correct horse battery staple"},
                    },
                ],
            },
        },
    },
}
IDEA_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea was not found.",
    "content": {
        "application/json": {
            "example": _detail("Idea 99999 not found"),
        },
    },
}
IDEA_GROUP_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Selected idea group was not found.",
    "content": {
        "application/json": {
            "example": _detail("Group with pk=99999 not found"),
        },
    },
}
IDEA_UPDATE_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea or selected idea group was not found.",
    "content": {
        "application/json": {
            "examples": {
                "missing_idea": {
                    "summary": "Update an idea that no longer exists",
                    "value": _detail("Idea 99999 not found"),
                },
                "missing_group": {
                    "summary": "Move an idea to a missing group",
                    "value": _detail("Group with pk=99999 not found"),
                },
            },
        },
    },
}
IDEA_CONFLICT_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea update or delete was rejected.",
    "content": {
        "application/json": {
            "example": _detail("Idea has been modified on the server"),
        },
    },
}
IDEA_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea create request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "blank_title": {
                    "summary": "Create an idea with a blank title",
                    "value": _string_too_short_error("title"),
                },
                "invalid_group_pk": {
                    "summary": "Create an idea with a non-numeric group key",
                    "value": _body_int_error("group_pk"),
                },
            },
        },
    },
}
IDEA_UPDATE_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea update request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_path": {
                    "summary": "Use a non-numeric idea primary key",
                    "value": _path_int_error("idea_pk"),
                },
                "blank_title": {
                    "summary": "Update an idea with a blank title",
                    "value": _string_too_short_error("title"),
                },
                "invalid_group_pk": {
                    "summary": "Move an idea with a non-numeric group key",
                    "value": _body_int_error("group_pk"),
                },
            },
        },
    },
}
IDEA_DELETE_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea delete request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_path": {
                    "summary": "Use a non-numeric idea primary key",
                    "value": _path_int_error("idea_pk"),
                },
                "invalid_timestamp": {
                    "summary": "Send a non-numeric freshness timestamp",
                    "value": _body_int_error("last_known_updated_at"),
                },
            },
        },
    },
}
IDEA_QUERY_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea query parameters are invalid.",
    "content": {
        "application/json": {
            "example": _query_limit_error(),
        },
    },
}
IDEA_PATH_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Idea path parameter is invalid.",
    "content": {
        "application/json": {
            "example": _path_int_error("idea_pk"),
        },
    },
}
GROUP_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group was not found.",
    "content": {
        "application/json": {
            "example": _detail("Group 99999 not found"),
        },
    },
}
GROUP_PARENT_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Parent group was not found.",
    "content": {
        "application/json": {
            "example": _detail("Parent group not found"),
        },
    },
}
GROUP_CONFLICT_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group operation conflicts with existing data.",
    "content": {
        "application/json": {
            "example": _detail('Group "backend" already exists'),
        },
    },
}
GROUP_CREATE_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group create request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "blank_name": {
                    "summary": "Create a group with a blank name",
                    "value": _string_too_short_error("name"),
                },
                "invalid_parent_pk": {
                    "summary": "Nest a group under an invalid parent key",
                    "value": _body_ge_error("parent_pk"),
                },
            },
        },
    },
}
GROUP_UPDATE_CONFLICT_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group rename conflicts with existing data.",
    "content": {
        "application/json": {
            "examples": {
                "duplicate_name": {
                    "summary": "Rename a group to an existing name",
                    "value": _detail('Group "backend" already exists'),
                },
                "default_group": {
                    "summary": "Rename the default group",
                    "value": _detail("Default group cannot be renamed"),
                },
            },
        },
    },
}
GROUP_UPDATE_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group update request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_path": {
                    "summary": "Use a non-numeric group primary key",
                    "value": _path_int_error("group_pk"),
                },
                "blank_name": {
                    "summary": "Rename a group to a blank name",
                    "value": _string_too_short_error("name"),
                },
            },
        },
    },
}
GROUP_PATH_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group path parameter is invalid.",
    "content": {
        "application/json": {
            "example": _path_int_error("group_pk"),
        },
    },
}
GROUP_DELETE_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group or target group was not found.",
    "content": {
        "application/json": {
            "examples": {
                "missing_group": {
                    "summary": "Delete a group that no longer exists",
                    "value": _detail("Group 99999 not found"),
                },
                "missing_target": {
                    "summary": "Move ideas to a missing target group",
                    "value": _detail("Target group not found"),
                },
            },
        },
    },
}
GROUP_DELETE_CONFLICT_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group delete conflicts with existing data.",
    "content": {
        "application/json": {
            "examples": {
                "default_group": {
                    "summary": "Delete the default group",
                    "value": _detail("Default group cannot be deleted"),
                },
                "child_groups": {
                    "summary": "Delete a group that has child groups",
                    "value": _detail(
                        "Group with child groups cannot be deleted"
                    ),
                },
                "same_target": {
                    "summary": "Move ideas into the group being deleted",
                    "value": _detail(
                        "Cannot move ideas into the same group being deleted"
                    ),
                },
            },
        },
    },
}
GROUP_DELETE_QUERY_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Group delete query parameters are invalid.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_path": {
                    "summary": "Use a non-numeric group primary key",
                    "value": _path_int_error("group_pk"),
                },
                "invalid_target": {
                    "summary": "Move ideas to an invalid target group key",
                    "value": {
                        "detail": [
                            {
                                "type": "greater_than_equal",
                                "loc": ["query", "move_to_group_pk"],
                                "msg": (
                                    "Input should be greater than or equal to 1"
                                ),
                                "input": "0",
                                "ctx": {"ge": 1},
                            },
                        ],
                    },
                },
            },
        },
    },
}
TAG_NOT_FOUND_RESPONSE: Final[OpenApiResponse] = {
    "description": "Tag was not found.",
    "content": {
        "application/json": {
            "example": _detail("Tag 99999 not found"),
        },
    },
}
TAG_CONFLICT_RESPONSE: Final[OpenApiResponse] = {
    "description": "Tag operation conflicts with existing data.",
    "content": {
        "application/json": {
            "example": _detail('Tag "python" already exists'),
        },
    },
}
TAG_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Tag request validation failed.",
    "content": {
        "application/json": {
            "example": _detail("Tag name cannot be empty"),
        },
    },
}
TAG_UPDATE_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Tag update request validation failed.",
    "content": {
        "application/json": {
            "examples": {
                "invalid_path": {
                    "summary": "Use a non-numeric tag primary key",
                    "value": _path_int_error("tag_pk"),
                },
                "blank_name": {
                    "summary": "Rename a tag to a blank name",
                    "value": _detail("Tag name cannot be empty"),
                },
            },
        },
    },
}
TAG_PATH_VALIDATION_ERROR_RESPONSE: Final[OpenApiResponse] = {
    "description": "Tag path parameter is invalid.",
    "content": {
        "application/json": {
            "example": _path_int_error("tag_pk"),
        },
    },
}


def json_response_example(example: object) -> JsonResponseExample:
    """Return FastAPI OpenAPI metadata for one JSON response example."""
    return {
        "content": {
            "application/json": {
                "example": example,
            },
        },
    }
