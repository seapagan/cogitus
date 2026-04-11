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


class DataBackendMode(str, Enum):
    """Supported data backends for the TUI."""

    LOCAL = "local"
    API = "api"


VALID_DATA_BACKEND_MODES: tuple[str, ...] = tuple(
    mode.value for mode in DataBackendMode
)
DEFAULT_DATA_BACKEND_MODE = DataBackendMode.LOCAL
DEFAULT_API_AUTH_JWT_ALGORITHM = "HS256"
DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES = 30


class AppSettings(TOMLSettings):
    """Cogitus app settings."""

    # 0 means "no last-selected idea yet".
    last_viewed_idea_pk: int = 0
    theme: str = "textual-dark"
    edit_body_cursor_mode: str = DEFAULT_EDIT_BODY_CURSOR_MODE.value
    new_idea_group_mode: str = DEFAULT_NEW_IDEA_GROUP_MODE.value
    default_group_name: str = DEFAULT_GROUP_NAME
    data_backend_mode: str = DEFAULT_DATA_BACKEND_MODE.value
    remote_api_base_url: str = ""
    remote_api_username: str = ""
    remote_api_password: str = ""
    prompt_after_clone: bool = True
    api_auth_username: str = ""
    api_auth_password_hash: str = ""
    api_auth_jwt_secret: str = ""
    api_auth_jwt_algorithm: str = DEFAULT_API_AUTH_JWT_ALGORITHM
    api_auth_token_expire_minutes: int = DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES


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


def normalize_data_backend_mode(mode: str) -> DataBackendMode:
    """Normalize persisted backend mode to enum with safe default."""
    if mode in VALID_DATA_BACKEND_MODES:
        return DataBackendMode(mode)
    return DEFAULT_DATA_BACKEND_MODE


def normalize_default_group_name(name: str) -> str:
    """Normalize configured default group name with safe fallback."""
    normalized = name.strip().lower()
    if normalized:
        return normalized
    return DEFAULT_GROUP_NAME


def normalize_api_auth_username(username: str) -> str:
    """Normalize configured API auth username."""
    return username.strip()


def normalize_remote_api_base_url(url: str) -> str:
    """Normalize configured remote API base URL."""
    return url.strip().rstrip("/")


def normalize_api_auth_jwt_algorithm(algorithm: str) -> str:
    """Normalize configured JWT algorithm with safe default."""
    normalized = algorithm.strip()
    if normalized:
        return normalized
    return DEFAULT_API_AUTH_JWT_ALGORITHM


def normalize_api_auth_token_expire_minutes(minutes: int) -> int:
    """Normalize API token lifetime with safe default."""
    if minutes > 0:
        return minutes
    return DEFAULT_API_AUTH_TOKEN_EXPIRE_MINUTES


def get_settings() -> AppSettings:
    """Return singleton app settings instance."""
    return AppSettings.get_instance(
        "cogitus",
        settings_file_name="config.toml",
        xdg_config=True,
    )
