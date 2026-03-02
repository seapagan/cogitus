"""SQLite FTS5-backed search backend."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqliter import SqliterDB

_SNIPPET_START = "[["
_SNIPPET_END = "]]"
_FTS_TOKEN_RE = re.compile(r"\w+")
_REBUILD_SQL = """
    INSERT INTO idea_search (
        rowid,
        idea_pk,
        title,
        body,
        group_name,
        tag_names
    )
    SELECT
        ideas.pk,
        ideas.pk,
        ideas.title,
        ideas.body,
        COALESCE(groups.name, ''),
        COALESCE((
            SELECT GROUP_CONCAT(tag_name, ' ')
            FROM (
                SELECT tags.name AS tag_name
                FROM ideas_tags
                INNER JOIN tags
                    ON tags.pk = ideas_tags.tags_pk
                WHERE ideas_tags.ideas_pk = ideas.pk
                ORDER BY tags.name
            )
        ), '')
    FROM ideas
    LEFT JOIN groups ON groups.pk = ideas.group_id;
"""
_UPSERT_SQL = """
    INSERT INTO idea_search (
        rowid,
        idea_pk,
        title,
        body,
        group_name,
        tag_names
    )
    SELECT
        ideas.pk,
        ideas.pk,
        ideas.title,
        ideas.body,
        COALESCE(groups.name, ''),
        COALESCE((
            SELECT GROUP_CONCAT(tag_name, ' ')
            FROM (
                SELECT tags.name AS tag_name
                FROM ideas_tags
                INNER JOIN tags
                    ON tags.pk = ideas_tags.tags_pk
                WHERE ideas_tags.ideas_pk = ideas.pk
                ORDER BY tags.name
            )
        ), '')
    FROM ideas
    LEFT JOIN groups ON groups.pk = ideas.group_id
    WHERE ideas.pk = ?;
"""
_SEARCH_SQL = f"""
    SELECT
        idea_pk,
        bm25(idea_search) AS score,
        snippet(
            idea_search,
            2,
            '{_SNIPPET_START}',
            '{_SNIPPET_END}',
            '...',
            12
        ) AS body_snippet,
        snippet(
            idea_search,
            1,
            '{_SNIPPET_START}',
            '{_SNIPPET_END}',
            '...',
            8
        ) AS title_snippet
        ,
        snippet(
            idea_search,
            3,
            '{_SNIPPET_START}',
            '{_SNIPPET_END}',
            '...',
            8
        ) AS group_snippet,
        snippet(
            idea_search,
            4,
            '{_SNIPPET_START}',
            '{_SNIPPET_END}',
            '...',
            8
        ) AS tag_snippet
    FROM idea_search
    WHERE idea_search MATCH ?
    ORDER BY score, rowid;
"""  # noqa: S608


@dataclass(frozen=True)
class FtsSearchMatch:
    """One ranked text-search match from the FTS index."""

    idea_pk: int
    score: float
    body_snippet: str
    title_snippet: str
    group_snippet: str
    tag_snippet: str


def ensure_search_tables(db: SqliterDB) -> None:
    """Ensure the FTS search virtual table exists."""
    db.connect().execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS idea_search
        USING fts5(
            idea_pk UNINDEXED,
            title,
            body,
            group_name,
            tag_names
        );
        """
    )


class FtsSearchBackend:
    """Provide FTS5 indexing and ranked text search for ideas."""

    def __init__(self, db: SqliterDB) -> None:
        """Initialize with the database connection."""
        self._db = db

    def rebuild(self) -> None:
        """Rebuild the search index from the relational source tables."""
        with self._db.connect() as conn:
            conn.execute("DELETE FROM idea_search;")
            conn.execute(_REBUILD_SQL)
            conn.commit()

    def upsert_idea(self, idea_pk: int) -> None:
        """Insert or refresh one idea document in the search index."""
        with self._db.connect() as conn:
            conn.execute(
                "DELETE FROM idea_search WHERE rowid = ?;",
                (idea_pk,),
            )
            conn.execute(_UPSERT_SQL, (idea_pk,))
            conn.commit()

    def delete_idea(self, idea_pk: int) -> None:
        """Remove one idea document from the search index."""
        with self._db.connect() as conn:
            conn.execute(
                "DELETE FROM idea_search WHERE rowid = ?;",
                (idea_pk,),
            )
            conn.commit()

    def search_text(
        self,
        query_text: str,
    ) -> list[FtsSearchMatch] | None:
        """Search idea text with FTS5, returning ranked primary keys."""
        fts_query = _build_fts_query(query_text)
        if fts_query is None:
            return None

        rows = self._db.connect().execute(_SEARCH_SQL, (fts_query,)).fetchall()
        return [
            FtsSearchMatch(
                idea_pk=int(row[0]),
                score=float(row[1]),
                body_snippet=str(row[2]),
                title_snippet=str(row[3]),
                group_snippet=str(row[4]),
                tag_snippet=str(row[5]),
            )
            for row in rows
        ]


def _build_fts_query(query_text: str) -> str | None:
    """Compile plain text into a safe FTS5 prefix query."""
    stripped = query_text.strip()
    if not stripped:
        return None

    tokens = _FTS_TOKEN_RE.findall(stripped.lower())
    if not tokens:
        return None
    return " AND ".join(f'"{token}"*' for token in tokens)


def _choose_snippet(
    *,
    body_snippet: str,
    title_snippet: str,
) -> str | None:
    """Choose the best snippet candidate from FTS output."""
    if _contains_highlight(body_snippet):
        return _clean_snippet(body_snippet)
    if _contains_highlight(title_snippet):
        return _clean_snippet(title_snippet)
    if body_snippet.strip():
        return _clean_snippet(body_snippet)
    if title_snippet.strip():
        return _clean_snippet(title_snippet)
    return None


def _contains_highlight(snippet: str) -> bool:
    """Return whether the snippet contains an explicit match marker."""
    return _SNIPPET_START in snippet and _SNIPPET_END in snippet


def _clean_snippet(snippet: str) -> str:
    """Normalize snippet text for compact single-line UI rendering."""
    cleaned = snippet.replace(_SNIPPET_START, "").replace(_SNIPPET_END, "")
    return " ".join(cleaned.split())
