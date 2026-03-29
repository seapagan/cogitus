"""FastAPI application package for Cogitus."""

import importlib
from typing import TYPE_CHECKING

__all__ = ["create_api_app"]

if TYPE_CHECKING:
    # Codacy's pylint pass cannot infer exports provided only via __getattr__.
    from cogitus.api.main import create_api_app


def __getattr__(name: str) -> object:
    """Lazily expose the app factory so the API remains optional."""
    if name == "create_api_app":
        return importlib.import_module("cogitus.api.main").create_api_app
    raise AttributeError(name)
