"""FastAPI application package for Cogitus."""

import importlib

__all__ = ["create_api_app"]


def __getattr__(name: str) -> object:
    """Lazily expose the app factory so the API remains optional."""
    if name == "create_api_app":
        return importlib.import_module("cogitus.api.main").create_api_app
    raise AttributeError(name)
