# Search

## Current Search Behavior

Search supports free text plus inline structured operators.

- Free text still matches title/body/tag text.
- `tag:<name>` filters by exact tag name.
- `group:<name>` filters by exact group name.
- Free text and structured filters are combined with an implicit `and`.
- Multiple structured filters default to `and`.
- You can use explicit `and` / `or` between structured filters.

## Usage

1. Press `/` to focus search.
2. Type your query text and optional operators.
3. Use `Tab` to open/cycle autocomplete suggestions.
4. Use `Shift+Tab`, `Up`, or `Down` to move between suggestions.
5. Press `Enter` to accept the highlighted suggestion.
6. Matching ideas remain in the tree.
7. Press `Esc` to close autocomplete first, then `Esc` again to leave
   search focus.

## Examples

- `python`
- `tag:python`
- `group:backend and tag:python`
- `tag:python or tag:typescript`
- `python tag:api`

## Notes

- Search is case-insensitive in typical SQLite configurations.
- Invalid operator fragments like `tag:` are treated as plain text.
- `and` / `or` between structured filters are evaluated left-to-right.
- Search does not support parentheses or `not` yet.
- While search is focused, `Tab` is reserved for autocomplete.
