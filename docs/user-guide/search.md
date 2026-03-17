# Search

## Current Search Behavior

Search supports ranked free-text matching plus inline structured operators.

- Free text matches idea title and body only.
- Results are ranked so stronger text matches appear before weaker ones.
- When search is active, the left pane switches to a dedicated search-results
  view.
- Structured-only searches such as `tag:python` or `group:backend` show
  matching ideas directly as selectable rows.
- Searches with free text show selectable match rows under each `Group / Title`
  heading.
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
   Accepting `tag:` or `group:` immediately opens matching value suggestions.
6. Press `Down` to move from the search input into the filtered result list.
7. Structured-only searches show one selectable idea row per result.
8. Searches with free text show `Group / Title` headings plus one or more
   match rows.
9. Use `Up` and `Down` in the result list to move between selectable rows.
10. Press `Up` on the first result to return focus to the search input.
11. Selecting a result row updates the right pane with that idea.
12. Press `Esc` to close autocomplete first, then `Esc` again to leave
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
- Plain word queries use prefix-style text matching on visible title/body text.
- Punctuation-heavy plain-text queries fall back to the broader legacy
  substring behavior when needed.
- `tag:` and `group:` act as filters; they no longer add repeated visible
  `Tag:` or `Group:` match rows.
- Plain free-text queries do not match tags or group names unless you use
  `tag:` or `group:` explicitly.
- When an active search returns no matches, the results pane shows
  `No results for "<query>"`.
- While the search-results pane is focused with active search, `Esc` first returns
  focus to the search input; a second `Esc` clears the search.
- While search is focused, `Tab` is reserved for autocomplete.
- The status bar shows search-specific hints while search is active, including
  when focus is in the results list.
- The right pane currently updates to the selected idea, but does not yet do
  exact occurrence-level scrolling or inline match highlighting.
