"""Application settings stored in an XDG config file."""

from __future__ import annotations

from simple_toml_settings import TOMLSettings


class AppSettings(TOMLSettings):
    """Cogitus app settings."""

    # 0 means "no last-selected idea yet".
    last_viewed_idea_pk: int = 0


def get_settings() -> AppSettings:
    """Return singleton app settings instance."""
    return AppSettings.get_instance(
        "cogitus",
        settings_file_name="config.toml",
        xdg_config=True,
    )
