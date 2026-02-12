# Search

## Current Search Behavior

Current search uses SQLite `LIKE` queries across idea title/body and related
tag names.

## Usage

1. Press `/` to focus search.
2. Type your query text.
3. Matching ideas remain in the tree.
4. Press `Esc` to leave search focus.

## Notes

- Search is case-insensitive in typical SQLite configurations.
- Current behavior is simple text matching, not FTS ranking/snippets yet.
