"""Persisted dataset hash used by remote cache sync."""

from __future__ import annotations

from sqliter.orm import BaseDBModel


class DatasetState(BaseDBModel):
    """Singleton row storing the current API-visible dataset hash."""

    dataset_hash: str = ""

    class Meta:
        """Metadata for the dataset state model."""

        table_name = "dataset_state"
