"""Backend implementations for local and remote Cogitus data access."""

from cogitus.backends.api_client import RemoteAPIClient
from cogitus.backends.protocols import IdeaBackend, SyncingIdeaBackend
from cogitus.backends.remote_backend import RemoteIdeaBackend
from cogitus.backends.types import BackendConfig, RemoteSyncResult

__all__ = [
    "BackendConfig",
    "IdeaBackend",
    "RemoteAPIClient",
    "RemoteIdeaBackend",
    "RemoteSyncResult",
    "SyncingIdeaBackend",
]
