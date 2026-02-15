"""Application settings stored in an XDG config file."""

from __future__ import annotations

from enum import Enum

from simple_toml_settings import TOMLSettings


class EditBodyCursorMode(str, Enum):
    """Supported edit-body cursor initialization modes."""

    REMEMBER = "remember"
    START = "start"
    END = "end"


VALID_EDIT_BODY_CURSOR_MODES: tuple[str, ...] = tuple(
    mode.value for mode in EditBodyCursorMode
)
DEFAULT_EDIT_BODY_CURSOR_MODE = EditBodyCursorMode.REMEMBER


class NewIdeaGroupPreselectMode(str, Enum):
    """Supported group preselection modes for the new idea form."""

    CONTEXTUAL = "contextual"
    DEFAULT_GROUP = "default_group"


VALID_NEW_IDEA_GROUP_PRESELECT_MODES: tuple[str, ...] = tuple(
    mode.value for mode in NewIdeaGroupPreselectMode
)
DEFAULT_NEW_IDEA_GROUP_PRESELECT_MODE = NewIdeaGroupPreselectMode.CONTEXTUAL


class AppSettings(TOMLSettings):
    """Cogitus app settings."""

    # 0 means "no last-selected idea yet".
    last_viewed_idea_pk: int = 0
    edit_body_cursor_mode: str = DEFAULT_EDIT_BODY_CURSOR_MODE.value
    new_idea_group_preselect_mode: str = (
        DEFAULT_NEW_IDEA_GROUP_PRESELECT_MODE.value
    )


def normalize_edit_body_cursor_mode(mode: str) -> EditBodyCursorMode:
    """Normalize persisted cursor mode string to enum with safe default."""
    if mode in VALID_EDIT_BODY_CURSOR_MODES:
        return EditBodyCursorMode(mode)
    return DEFAULT_EDIT_BODY_CURSOR_MODE


def normalize_new_idea_group_preselect_mode(
    mode: str,
) -> NewIdeaGroupPreselectMode:
    """Normalize persisted new-idea group mode to enum with safe default."""
    if mode in VALID_NEW_IDEA_GROUP_PRESELECT_MODES:
        return NewIdeaGroupPreselectMode(mode)
    return DEFAULT_NEW_IDEA_GROUP_PRESELECT_MODE


def get_settings() -> AppSettings:
    """Return singleton app settings instance."""
    return AppSettings.get_instance(
        "cogitus",
        settings_file_name="config.toml",
        xdg_config=True,
    )
