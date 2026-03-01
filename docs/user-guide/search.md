# Search

## Current Search Behavior

Search supports ranked free-text matching plus inline structured operators.

- Free text matches idea title, body, group name, and tag text.
- Results are ranked so stronger text matches appear before weaker ones.
- When search is active, matching rows show a compact inline snippet in the
  left pane.
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
6. Press `Down` to move from the search input into the filtered result list.
7. Use `Up` and `Down` in the result list to move between matching ideas.
8. Press `Up` on the first result to return focus to the search input.
9. Matching ideas remain in the tree, ordered by search relevance.
10. While search is active, each matching row may include a short snippet.
11. Press `Esc` to close autocomplete first, then `Esc` again to leave
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
- Plain word queries use prefix-style text matching.
- Punctuation-heavy plain-text queries fall back to the broader legacy
  substring behavior when needed.
- While the result tree is focused with active search, `Esc` first returns
  focus to the search input; a second `Esc` clears the search.
- While search is focused, `Tab` is reserved for autocomplete.
