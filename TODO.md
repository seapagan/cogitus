# Todo

Ideas to add to Cogitus

## UI

- Allow key customization (using the `Textual` built-in functionality and the
  config file).
- continue navigation and keybinding polish.
- add contextual dynamic toolbar/actions by mode. [mostly implemented]
- add toggle and hotkey for the left tree to expand/collapse all. `space` does
  this for the individual nodes, but it would be good to have a toggle that does
  all (only to the group level, not the root node).
- add a tag management dialog with usage counts, rename/edit support, and
  explicit stale-tag pruning (selected/all stale with confirmation).
- clicking on any of the tags above the body window should open the search
  results as if `tag:<tag name>` was searched.
- revisit the custom footer status widgets and replace the current private
  `textual.widgets._footer.FooterKey` dependency with a public Textual API or
  an internal equivalent once that can be done without reintroducing the past
  footer layout/refresh regressions. Low priority.

## CLI

- add CLI commands to list, add and prune tags and groups

## Database Layer

- In the `db` module there are a few places where we still use raw SQL.
  investigate how we can update `sqliter-py` to add missing functionality -
  especially SQL `ALTER` and listing a helper to list indexes on fields/tables

## Tests

- refactor suitable UI/integration tests to be pilot-first: use Textual's
  `pilot` for tests that validate keyboard behavior, focus changes,
  footer/binding state, screen transitions, or other user-visible interaction
  flows; keep direct method/event calls only for unit-style helper and branch
  coverage where pilot would add noise without improving confidence.
- review `ty` type-checker findings in tests, especially whether intentionally
  invalid `SearchFilter` construction should use a clearer explicit escape hatch
  than `invalid_field: Any = "status"`.

## Search and Filtering

- upgrade dedicated search results from best-fragment rows to true
  occurrence-level navigation: let one match row map to one specific occurrence
  where practical, then scroll the right pane to that exact occurrence and add
  inline match highlighting there.
- optimize advanced search query execution to reduce multi-pass PK collection
  and re-fetch overhead as dataset size grows.

## Documentation

- None

## Export, Import, and Backup

- add export to assorted file-types both on the tags, group and idea level.
- save and load either entire database or individual ideas
- On creating an Idea, allow to use a local or remote file as the seed (ie get a
  todo from a github repo or local code)
- Allow to export an Idea to a remote file (this would be more difficult and
  need assorted auth additions)

## API

- reevaluate the remote API cache design once there is less planned work and
  technical debt: can we simplify from the current file-backed local cache to a
  memory-backed cache without losing the needed sync, worker-thread, startup,
  and cursor-state behavior?
- split API database startup initialization from per-request connection
  creation, then revisit changing synchronous API handlers from `async def` to
  `def` so FastAPI can safely use a threadpool with request-scoped `SqliterDB`
  / `IdeaService` instances.
- replace pre-edit full remote sync with a targeted single-idea refresh so
  editing one idea does not require pulling the whole remote snapshot first.
- remove plaintext secret storage from normal app settings: stop persisting the
  API JWT signing secret in TOML, and move the remote API password to a secret
  store or runtime-only prompt flow instead of keeping it as plain text in the
  normal config file.
- replace fragile API error-message substring matching with shared typed
  domain/API exceptions so HTTP 404/409/422 classification does not depend on
  repository and service error wording.

## Undo and History

- add full undo ability (basically with git-like functionality, but not using
  git - a journal that we can unwind?) Include edited, created and deleted
  ideas at first, more as the need arises. How would we store this?

## Profiles and Multi-Device

- add profiles, link ideas to a profile, optionally password protected.
- cloud database, allows reading/writing from multiple machines (can probably be
  suplanted by the API idea).

## Relationships and Idea Graph

- add explicit idea linking relationships.
- add relationship browsing primitives.
- add richer metadata and prioritization signals.
- add graph-oriented idea exploration views.
- add scoring heuristics (impact/effort/confidence).

## Data Layer and Performance

- evaluate optional SQLite write tuning (`PRAGMA synchronous=NORMAL`) with
  benchmark and risk assessment.
- make idea table writes and FTS index sync failure-tolerant. `create()`,
  `update()`, and `delete()` currently commit the canonical row change and then
  update `idea_search` separately, so an index write failure can leave search
  stale until rebuild. Investigate a proper fix: shared transaction support if
  `sqliter-py` can expose it cleanly, or a transactional outbox/on-commit
  reindex queue with retry/logging plus an explicit rebuild path.
- avoid unconditional FTS index rebuild on every `get_db()` startup; add an
  index validity/version check or other lightweight verification so rebuilds
  only happen when needed, while keeping an explicit/manual rebuild path.

## AI Assistance / MCP

- include an MCP server (using `FastAPI` and `tadata-org/fastapi_mcp`, though
  also look at `FastMCP`) so coding agents can read and write to the database.
- Write a project info or skills file (check how FastAPI does it using
  <https://agentskills.io>) so that Agents can understand how to use the server
  and even the CLI export (JSON prob best?) to store memory.
- explore optional AI-assisted idea expansion and prompt-to-structure
  workflows.
