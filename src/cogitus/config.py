"""Application settings stored in an XDG config file."""

from __future__ import annotations

from enum import Enum

from simple_toml_settings import TOMLSettings

from cogitus.constants import DEFAULT_GROUP_NAME


class EditBodyCursorMode(str, Enum):
    """Supported edit-body cursor initialization modes."""

    REMEMBER = "remember"
    START = "start"
    END = "end"


VALID_EDIT_BODY_CURSOR_MODES: tuple[str, ...] = tuple(
    mode.value for mode in EditBodyCursorMode
)
DEFAULT_EDIT_BODY_CURSOR_MODE = EditBodyCursorMode.REMEMBER


class NewIdeaGroupMode(str, Enum):
    """Supported group selection modes for the new idea form."""

    CONTEXTUAL = "contextual"
    DEFAULT_GROUP = "default_group"


VALID_NEW_IDEA_GROUP_MODES: tuple[str, ...] = tuple(
    mode.value for mode in NewIdeaGroupMode
)
DEFAULT_NEW_IDEA_GROUP_MODE = NewIdeaGroupMode.CONTEXTUAL


class AppSettings(TOMLSettings):
    """Cogitus app settings."""

    # 0 means "no last-selected idea yet".
    last_viewed_idea_pk: int = 0
    edit_body_cursor_mode: str = DEFAULT_EDIT_BODY_CURSOR_MODE.value
    new_idea_group_mode: str = DEFAULT_NEW_IDEA_GROUP_MODE.value
    default_group_name: str = DEFAULT_GROUP_NAME


def normalize_edit_body_cursor_mode(mode: str) -> EditBodyCursorMode:
    """Normalize persisted cursor mode string to enum with safe default."""
    if mode in VALID_EDIT_BODY_CURSOR_MODES:
        return EditBodyCursorMode(mode)
    return DEFAULT_EDIT_BODY_CURSOR_MODE


def normalize_new_idea_group_mode(
    mode: str,
) -> NewIdeaGroupMode:
    """Normalize persisted new-idea group mode to enum with safe default."""
    if mode in VALID_NEW_IDEA_GROUP_MODES:
        return NewIdeaGroupMode(mode)
    return DEFAULT_NEW_IDEA_GROUP_MODE


def normalize_default_group_name(name: str) -> str:
    """Normalize configured default group name with safe fallback."""
    normalized = name.strip().lower()
    if normalized:
        return normalized
    return DEFAULT_GROUP_NAME


def get_settings() -> AppSettings:
    """Return singleton app settings instance."""
    return AppSettings.get_instance(
        "cogitus",
        settings_file_name="config.toml",
        xdg_config=True,
    )
