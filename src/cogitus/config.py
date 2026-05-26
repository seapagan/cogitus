"""Application settings stored in an XDG config file."""

from __future__ import annotations

from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
DEFAULT_MCP_AUTH_TOKEN_EXPIRE_DAYS = 90
DEFAULT_THEME = "textual-dark"
DEFAULT_TIMEZONE = ""
DEFAULT_DATE_FORMAT = ""
VALID_DATE_FORMATS: tuple[str, ...] = ("", "iso", "mdy", "dmy")


class AppSettings(TOMLSettings):
    """Cogitus app settings."""

    # 0 means "no last-selected idea yet".
    last_viewed_idea_pk: int = 0
    theme: str = DEFAULT_THEME
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
    mcp_auth_jwt_secret: str = ""
    mcp_auth_token_expire_days: int = DEFAULT_MCP_AUTH_TOKEN_EXPIRE_DAYS
    timezone: str = DEFAULT_TIMEZONE
    date_format: str = DEFAULT_DATE_FORMAT
    save_idea_scroll_pos: bool = True

    def save(self) -> None:
        """Save settings without changing the persisted MCP auth secret."""
        self.mcp_auth_jwt_secret = self._saved_mcp_auth_jwt_secret()
        super().save()

    def save_mcp_auth_jwt_secret(self, secret: str) -> None:
        """Persist only the MCP auth secret and update this instance."""
        disk_settings = self._loaded_disk_settings()
        disk_settings.mcp_auth_jwt_secret = secret
        TOMLSettings.save(disk_settings)
        self.mcp_auth_jwt_secret = secret

    def _saved_mcp_auth_jwt_secret(self) -> str:
        """Return any existing persisted MCP auth secret."""
        try:
            saved_settings = self._loaded_disk_settings()
        except (OSError, ValueError):
            return ""
        return saved_settings.mcp_auth_jwt_secret.strip()

    def _loaded_disk_settings(self) -> AppSettings:
        """Return a settings instance loaded from the current config file."""
        return type(self)(
            self.app_name,
            settings_file_name=self.settings_file_name,
            settings_path=self.settings_folder,
            auto_create=False,
            use_section_header=self.use_section_header,
            allow_missing_file=True,
            strict_get=self.strict_get,
            schema_version=self.schema_version,
        )


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


def normalize_mcp_auth_token_expire_days(days: int) -> int:
    """Normalize MCP token lifetime with safe default."""
    if days > 0:
        return days
    return DEFAULT_MCP_AUTH_TOKEN_EXPIRE_DAYS


def normalize_timezone(tz_str: str) -> str:
    """Normalize configured timezone override with safe default."""
    return tz_str.strip()


def normalize_date_format(fmt: str) -> str:
    """Normalize configured date format with safe default."""
    normalized = fmt.strip().lower()
    if normalized in VALID_DATE_FORMATS:
        return normalized
    return DEFAULT_DATE_FORMAT


def is_valid_timezone(tz_str: str) -> bool:
    """Return whether the string is a valid IANA timezone name."""
    stripped = tz_str.strip()
    if not stripped:
        return True
    try:
        ZoneInfo(stripped)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def is_valid_date_format(fmt: str) -> bool:
    """Return whether the string is a recognized date format value."""
    return fmt.strip().lower() in VALID_DATE_FORMATS


def get_settings() -> AppSettings:
    """Return singleton app settings instance."""
    return AppSettings.get_instance(
        "cogitus",
        settings_file_name="config.toml",
        xdg_config=True,
    )
