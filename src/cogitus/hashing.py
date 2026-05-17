"""Stable content hashes for remote refresh decisions."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def idea_detail_hash(
    *,
    title: str,
    body: str,
    tag_names: Iterable[str],
    created_at: int,
    updated_at: int,
) -> str:
    """Return a stable hash for the rendered idea detail pane."""
    payload = {
        "body": body,
        "created_at": created_at,
        "tags": sorted(tag_names),
        "title": title,
        "updated_at": updated_at,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataset_hash(parts: Iterable[str]) -> str:
    """Return a stable hash for a set of API-visible dataset tokens."""
    encoded = json.dumps(
        sorted(parts),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
